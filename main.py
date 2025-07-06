import os
import json
import logging
import requests
import httpx
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# CONFIGURAÇÃO
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")  # canal de vendas
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")

# arquivos de estado
STATE_FILE    = "states.json"
CUSTOMER_FILE = "customers.json"

# cliente OpenAI
httpx_client   = httpx.Client(timeout=10)
openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)

# load/save JSON
def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# memória persistente
tates = load_json(STATE_FILE)
customers = load_json(CUSTOMER_FILE)

# Z-API send helper
headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN}
def send_whatsapp(phone, text):
    url = (
        f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}"
        f"/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {"phone": phone, "message": text, "type": "text"}
    try:
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        logging.info(f"Sent to {phone}: {r.text}")
    except Exception as e:
        logging.error(f"Failed send to {phone}: {e}")

# catálogo estático
CATALOG = (
    "Promoção Kit 5x5L por R$135,00 (30 dias p/ pagar)!\n"
    "Produtos: Sabão, Amaciante, Água sanitária, Desinfetante, Alvejante, Detergente, Veja Multiuso."
)

# extrai slots
def parse_order(msg):
    prompt = (
        "Você é um vendedor: extraia item, qt, data, bairro e urgente. "
        "Se faltar, inclua 'faltando':[...] no JSON."\
        f"\nMensagem: '{msg}'"
    )
    res = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system","content":prompt}],
    )
    return json.loads(res.choices[0].message.content)

# perguntas por campo
def next_question(field):
    texts = {
        "item":    "Qual produto deseja?",
        "qt":      "Quantas unidades?",
        "data":    "Para qual data e hora?",
        "bairro":  "Qual bairro?",
        "address":"Endereço completo (Rua, número)?",
        "urgent":  "É urgente? (sim/não)",
    }
    return texts.get(field, "Pode detalhar? 🧐")

@app.route("/webhook", methods=["POST"])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get("phone")
    text  = (data.get("text") or {}).get("message",""").strip()
    if not phone or not text or data.get("fromMe"):
        return jsonify(status="ignored")

    logging.info("Webhook recebido: %s", data)

    state = states.get(phone, {})

    # 1) qualificação inicial
    if phone not in customers:
        send_whatsapp(phone, "Olá! Pra começar, qual é seu nome?")
        customers[phone] = None
        save_json(CUSTOMER_FILE, customers)
        states.pop(phone, None)
        return jsonify(status="ask_name")
    if customers[phone] is None:
        customers[phone] = text.title()
        save_json(CUSTOMER_FILE, customers)
        send_whatsapp(phone, f"Obrigado, {customers[phone]}! 😊 Posso ajudar com nosso Kit ou catálogo de produtos?")
        states.pop(phone, None)
        return jsonify(status="name_saved")

    # 2) pedido de catálogo/informação
    lower = text.lower()
    if any(k in lower for k in ["catálogo","promoção","quais produtos","lista"]):
        send_whatsapp(phone, CATALOG)
        return jsonify(status="sent_catalog")

    # 3) amostra no carro
    if "ver no carro" in lower or "no carro" in lower:
        send_whatsapp(phone, "Sem problema! Podemos levar amostras no carro. Qual seu endereço completo?")
        state = {"obs":"ver no carro","waiting":"address"}
        states[phone] = state
        save_json(STATE_FILE, states)
        return jsonify(status="ask_address")

    # 4) confirmação pendente
    if state.get("confirm_pending"):
        if lower.startswith("s"):
            summary = state.get("group_summary")
            if summary and ZAPI_GROUP_ID:
                send_whatsapp(ZAPI_GROUP_ID, summary)
            send_whatsapp(phone, "Venda confirmada! Em breve avisaremos para entrega.")
        else:
            send_whatsapp(phone, "Claro, o que deseja ajustar no pedido?")
        states.pop(phone)
        save_json(STATE_FILE, states)
        return jsonify(status="confirmation")

    # 5) coleta de dados gerais
    if not state or state.get("waiting"):
        key = state.get("waiting")
        if key:
            val = text if key!="urgent" else text.lower().startswith("s")
            state[key] = val
        else:
            # extrair slots do pedido
            parsed  = parse_order(text)
            slots   = {k:parsed[k] for k in ["item","qt","data","bairro"] if k in parsed}
            missing = parsed.get("faltando", [])
            state = {**slots, **{"urgent":parsed.get("urgent",False)}}
            if missing:
                key = missing[0]
            else:
                key = None
        # check missing/additional
        fields = ["item","qt","data","bairro","address"]
        if key or any(f not in state for f in fields if f!="address"):
            ask = key or next(f for f in ["item","qt","data","bairro"] if f not in state)
            state["waiting"] = ask
            states[phone] = state
            save_json(STATE_FILE, states)
            send_whatsapp(phone, next_question(ask))
            return jsonify(status="ask_slot")
        # next: address if not sample
        if state.get("obs")!="ver no carro" and not state.get("address"):
            state["waiting"] = "address"
            states[phone] = state
            save_json(STATE_FILE, states)
            send_whatsapp(phone, next_question("address"))
            return jsonify(status="ask_address")
    # 6) todos os dados coletados: confirmar venda
    name    = customers[phone]
    obs     = state.get("obs", f"Pedido {state['qt']}x {state['item']}")
    summary = (
        f"Dados da Cliente:\n"
        f"Nome: {name}\n"
        f"Whats: {phone}\n"
        f"Endereço: {state.get('address')} - {state.get('bairro')}\n"
        f"Data/Horário: {state.get('data')}\n"
        f"Obs: {obs}"
    )
    send_whatsapp(phone, f"Perfeito, {name}! Confirmo o agendamento e já aviso quando estivermos a caminho. 😊")
    # pendência de confirmar no grupo
    state = {"confirm_pending":True, "group_summary":summary}
    states[phone] = state
    save_json(STATE_FILE, states)
    return jsonify(status="ask_confirm")

@app.route("/", methods=["GET"])
def home():
    return "Bot rodando!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
