from flask import Flask, request, jsonify
import os, logging, requests, json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import httpx
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())

# ─── DATABASE SIMPLES EM JSON ──────────────────────────────────────────────
CUSTOMER_FILE = "clientes.json"
STATE_FILE    = "estados.json"
CATALOGUE_FILE = "catalogo.json"

# Carrega ou inicializa dados
clientes = {}
estados  = {}
catalogue = {}

for path, var in [(CUSTOMER_FILE, clientes), (STATE_FILE, estados)]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            var.update(json.load(f))

if os.path.exists(CATALOGUE_FILE):
    with open(CATALOGUE_FILE, "r", encoding="utf-8") as f:
        catalogue = json.load(f)

# Salva JSON helper
def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── UTILITÁRIAS DE ENVIO ─────────────────────────────────────────────────
def send_whatsapp(phone, text):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN}
    payload = {"phone": phone, "message": text, "type": "text"}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada a {phone}")
    except Exception as e:
        logging.error(f"❌ Erro enviando a {phone}: {e}")

def notify_group(text):
    if ZAPI_GROUP_ID:
        send_whatsapp(ZAPI_GROUP_ID, text)

# ─── AGENDAMENTO DE MOTIVAÇÃO ─────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.start()

def send_motivation():
    text = "Cada desafio superado no código é um passo a mais rumo ao seu objetivo!"
    notify_group(text)

scheduler.add_job(send_motivation, trigger="cron", hour=8, minute=0, timezone="America/Sao_Paulo")

# ─── FLUXO PRINCIPAL ───────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    phone = data.get("phone")
    msg   = data.get("text", {}).get("message", "").strip()
    if not phone or not msg or data.get("fromMe", False):
        return jsonify({"status": "ignored"})

    # 1) Identificar novo cliente e perguntar nome
    if phone not in clientes:
        clientes[phone] = ""
        save(CUSTOMER_FILE, clientes)
        send_whatsapp(phone, "Olá! Pra começarmos, qual é o seu nome?")
        return jsonify({"status": "ask_name"})

    # 2) Gravar nome do cliente
    if clientes[phone] == "":
        nome = msg.title()
        clientes[phone] = nome
        save(CUSTOMER_FILE, clientes)
        estados.pop(phone, None)
        # Envia catálogo e inicia slot-filling
        cat_text = "Aqui está nosso catálogo de produtos de limpeza 5L:\n" + "\n".join([f"- {k}: R${v}" for k,v in catalogue.items()])
        send_whatsapp(phone, f"Obrigado, {nome}! 😊 {cat_text}")
        send_whatsapp(phone, "Qual produto você gostaria de pedir? Ex: Lava roupas, Branquinho…")
        estados[phone] = {}
        save(STATE_FILE, estados)
        return jsonify({"status": "greeted"})

    # 3) Slot-filling: item, qt, data, bairro, urgente
    state = estados.get(phone, {})
    slots = state.get("slots", {})
    # extrai natural if primeira vez
    if not slots:
        # GPT parser fallback ou regex simples
        words = msg.lower().split()
        for item in catalogue:
            if item.lower() in msg.lower():
                slots['item'] = item
                break
        import re
        m = re.search(r"(\d+)", msg)
        slots['qt'] = int(m.group(1)) if m else None
        slots['data'] = 'amanhã' if 'amanhã' in msg.lower() else None
        slots['bairro'] = None
        slots['urgente'] = 'urgente' in msg.lower() or 'sim' == msg.lower()
    # checa faltantes
    for key in ['item','qt','data','bairro','urgente']:
        if key not in slots or slots[key] in [None, '']:
            if key == 'item': question = 'Qual produto você gostaria de pedir?'
            elif key == 'qt': question = 'Quantas unidades você deseja?'
            elif key == 'data': question = 'Para qual data você quer a entrega?'
            elif key == 'bairro': question = 'Em qual bairro devo entregar?'
            else: question = 'Essa entrega é urgente? (sim/não)'
            estados[phone] = {'slots': slots}
            save(STATE_FILE, estados)
            send_whatsapp(phone, question)
            return jsonify({"status": f"ask_{key}"})
    
    # todos slots preenchidos -> confirmar
    nome = clientes[phone]
    urgent_tag = ' (URGENTE)' if slots['urgente'] else ''
    confirm_text = f"✅ Pedido confirmado: {slots['qt']}x {slots['item']} para {slots['data']} em {slots['bairro']}{urgent_tag}. Avisaremos quando estivermos a caminho."
    send_whatsapp(phone, confirm_text)
    # notificar grupo
    grp = f"📅 Entrega agendada: {nome} pediu {slots['qt']}x {slots['item']} em {slots['bairro']} para {slots['data']}{urgent_tag}."
    notify_group(grp)
    estados.pop(phone, None)
    save(STATE_FILE, estados)
    return jsonify({"status": "order_complete"})

@app.route("/", methods=["GET"])
def home():
    return "Bot rodando!", 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
