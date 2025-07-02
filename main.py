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
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")   # canal de vendas
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")

# arquivos de estado
STATE_FILE    = "states.json"
CUSTOMER_FILE = "customers.json"

# cliente OpenAI
httpx_client   = httpx.Client(timeout=10)
openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)

# carrega JSON ou retorna dict vazio
def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

# salva dict em JSON
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# memória em disco
states    = load_json(STATE_FILE)
customers = load_json(CUSTOMER_FILE)

# envia mensagem via Z-API
headers = {
    "Content-Type": "application/json",
    "Client-Token": ZAPI_CLIENT_TOKEN
}
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

# extrai slots iniciais
def parse_order(msg):
    prompt = (
        "Você é um vendedor: extraia item, qt, data, bairro e urgente de forma natural. "
        "Se faltar, retorne também faltando:[...] na lista.\n"
        f"Mensagem: '{msg}'"
    )
    res = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system","content":prompt}],
    )
    return json.loads(res.choices[0].message.content)

# texto para cada campo faltante
def next_question(field):
    texts = {
        "item":   "Qual produto você deseja?",
        "qt":     "Quantas unidades?",
        "data":   "Para qual data?",
        "bairro": "Qual bairro?",
        "urgente":"É urgente? (sim/não)",
    }
    return texts.get(field, "Pode detalhar?")

@app.route("/webhook", methods=["POST"])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get("phone")
    text  = (data.get("text") or {}).get("message","").strip()
    # ignora sem número/texto ou mensagem própria
    if not phone or not text or data.get("fromMe"):
        return jsonify(status="ignored")

    logging.info("Webhook recebido: %s", data)

    # passo 1: perguntar nome
    if phone not in customers:
        send_whatsapp(phone, "Olá! Pra começar, qual é seu nome?")
        customers[phone] = None
        save_json(CUSTOMER_FILE, customers)
        states.pop(phone, None)
        return jsonify(status="ask_name")

    # passo 2: registrar nome
    if customers[phone] is None:
        customers[phone] = text.title()
        save_json(CUSTOMER_FILE, customers)
        send_whatsapp(phone, f"Obrigado, {customers[phone]}! Vamos ao pedido.")
        states.pop(phone, None)
        return jsonify(status="name_saved")

    st = states.get(phone, {})

    # confirmação pendente
    if st.get("confirm_pending"):
        if text.lower().startswith("s"):
            summary = st.get("group_summary")
            if summary and ZAPI_GROUP_ID:
                send_whatsapp(ZAPI_GROUP_ID, summary)
            send_whatsapp(phone, "Venda confirmada! Obrigado 😊")
        else:
            send_whatsapp(phone, "Tudo bem, o que deseja ajustar?")
        states.pop(phone, None)
        save_json(STATE_FILE, states)
        return jsonify(status="confirmation")

    # coletar slots
    if not st:
        parsed  = parse_order(text)
        missing = parsed.get("faltando", [])
        slots   = {k: parsed[k] for k in ["item","qt","data","bairro","urgente"] if k in parsed}
        if missing:
            key = missing[0]
            slots["waiting"] = key
            states[phone] = slots
            save_json(STATE_FILE, states)
            send_whatsapp(phone, next_question(key))
            return jsonify(status="ask_slot")
        st = slots

    # responder pergunta de slot faltante
    elif st.get("waiting"):
        key = st.pop("waiting")
        val = text if key!="urgente" else text.lower().startswith("s")
        st[key] = val
        miss = [k for k in ["item","qt","data","bairro","urgente"] if k not in st or not st[k]]
        if miss:
            nxt = miss[0]
            st["waiting"] = nxt
            states[phone] = st
            save_json(STATE_FILE, states)
            send_whatsapp(phone, next_question(nxt))
            return jsonify(status="ask_slot")
    else:
        # erro de fluxo, reiniciar
        states.pop(phone, None)
        save_json(STATE_FILE, states)
        send_whatsapp(phone, "Desculpe, vamos recomeçar. Qual produto deseja?")
        return jsonify(status="reset")

    # todos os dados prontos: confirmar com o cliente
    customer = customers[phone]
    summary  = f"Venda de {st['qt']}x {st['item']} para {st['data']} em {st['bairro']}"
    if st.get("urgente"):
        summary += " (URGENTE)"
    msg_cli = f"Perfeito, {customer}! Confirma? {summary}\nResponda: sim/não"

    # marca confirmação pendente
    states[phone] = {"confirm_pending": True, "group_summary": summary}
    save_json(STATE_FILE, states)
    send_whatsapp(phone, msg_cli)
    return jsonify(status="ask_confirm")

@app.route("/", methods=["GET"])
def home():
    return "Bot rodando!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
