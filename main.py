from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
import json
from datetime import datetime, timedelta
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")  # ID do grupo “Vendas - IA”

openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())

# APScheduler
scheduler = BackgroundScheduler()
logging.info("🔄 Iniciando APScheduler...")
scheduler.start()

def enviar_motivacao():
    frase = "“Cada desafio superado no código é um passo a mais rumo ao seu objetivo: continue codando com confiança!”"
    if ZAPI_GROUP_ID:
        send_whatsapp_message(ZAPI_GROUP_ID, frase)

scheduler.add_job(enviar_motivacao, trigger="cron",
                  hour=8, minute=0, timezone="America/Sao_Paulo")
scheduler.add_job(enviar_motivacao, trigger="date",
                  run_date=datetime.now() + timedelta(minutes=1))

# ─── ARMAZENAMENTO ─────────────────────────────────────────────────────────────
STATE_FILE   = "estados.json"   # guarda slots e estados de usuário
CUSTOMER_FILE= "clientes.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

estados   = load_json(STATE_FILE)    # { phone: {slots..., "esperando": key} }
clientes  = load_json(CUSTOMER_FILE) # { phone: "Nome" }

# ─── UTILITÁRIAS ───────────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, text: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN}
    try:
        r = requests.post(url, json={"phone":phone,"message":text,"type":"text"}, headers=headers)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {r.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

def send_group_message(text: str):
    if ZAPI_GROUP_ID:
        send_whatsapp_message(ZAPI_GROUP_ID, text)

def extrair_slots(msg: str) -> dict:
    """
    Usa GPT para extrair item, qt, data, bairro, urgente e lista de faltando.
    """
    prompt = f"""
Você é um parser de pedidos. Retorne apenas JSON com:
- item (string)
- qt (inteiro)
- data (string)
- bairro (string)
- urgente (true/false)
- faltando: lista de chaves não detectadas
Exemplo de saída:
{{"item":"Lava roupas","qt":1,"data":"amanhã","bairro":"Centro","urgente":false,"faltando":[]}}
Frase do cliente: "{msg}"
"""
    res = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system","content":prompt}]
    )
    return json.loads(res.choices[0].message.content)

def proxima_pergunta(faltando_key: str) -> str:
    textos = {
        "item":    "Qual produto você gostaria de pedir? Ex: Lava roupas, Branquinho…",
        "qt":      "Quantas unidades você deseja?",
        "data":    "Para qual data você quer a entrega?",
        "bairro":  "Em qual bairro devo entregar?",
        "urgente": "Essa entrega é urgente? (sim/não)"
    }
    return textos.get(faltando_key, "Pode me dar mais detalhes?")

# ─── ROTAS ─────────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data  = request.get_json()
    phone = data.get("phone")
    msg   = data.get("text",{}).get("message","").strip()
    if not phone or not msg or data.get("fromMe",False):
        return jsonify({"status":"ignored"})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # coleta nome simples
    if phone not in clientes:
        send_whatsapp_message(phone, "Olá! Pra começarmos, qual é o seu nome?")
        clientes[phone] = None
        save_json(CUSTOMER_FILE, clientes)
        estados.pop(phone, None)
        return jsonify({"status":"ask_name"})
    if clientes[phone] is None:
        clientes[phone] = msg.title()
        save_json(CUSTOMER_FILE, clientes)
        send_whatsapp_message(phone, f"Obrigado, {clientes[phone]}! 😊 Agora vamos ao seu pedido.")
        estados.pop(phone, None)
        return jsonify({"status":"name_saved"})

    # checa se estamos esperando um slot específico
    user_state = estados.get(phone, {})
    esperando = user_state.get("esperando")
    if esperando:
        # atualiza o slot com a resposta livre
        val = msg.lower() in ("sim","s","urgente") if esperando=="urgente" else msg
        user_state[esperando] = val
        user_state.pop("esperando")
        # verifica o que ainda falta
        faltando = [k for k in ("item","qt","data","bairro","urgente")
                    if k not in user_state or user_state[k] in (None,"",False)]
        if faltando:
            prox = faltando[0]
            user_state["esperando"] = prox
            estados[phone] = user_state
            save_json(STATE_FILE, estados)
            send_whatsapp_message(phone, proxima_pergunta(prox))
            return jsonify({"status":"ask_slot"})
        # todos slots preenchidos
        slots = user_state
        estados.pop(phone)
    else:
        # primeira vez: extrai todos de uma vez
        slots = extrair_slots(msg)
        faltando = slots.pop("faltando", [])
        if faltando:
            prox = faltando[0]
            slots["esperando"] = prox
            estados[phone] = slots
            save_json(STATE_FILE, estados)
            send_whatsapp_message(phone, proxima_pergunta(prox))
            return jsonify({"status":"ask_slot"})

    # aqui, slots tem item, qt, data, bairro, urgente completos
    nome = clientes[phone]
    msg_cli = (
        f"✅ Pedido confirmado: {slots['qt']}x {slots['item']} para {slots['data']} em {slots['bairro']}"
        + (" (URGENTE)" if slots["urgente"] else "")
        + ".\nNo dia combinado, avisaremos quando estivermos a caminho do seu bairro."
    )
    send_whatsapp_message(phone, msg_cli)

    grp = (
        f"📅 Entrega agendada: {nome} pediu {slots['qt']}x {slots['item']} "
        f"em {slots['bairro']} para {slots['data']}"
        + (" (URGENTE)" if slots["urgente"] else "")
    )
    send_group_message(grp)

    return jsonify({"status":"order_complete"})

@app.route("/", methods=["GET"])
def home():
    return "Bot rodando!", 200

if __name__=="__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT",5000)))
