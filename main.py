from flask import Flask, request, jsonify
import os, logging, requests, json, httpx
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")

openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())

# ─── TEMPLATES PARAMETRIZADOS ───────────────────────────────────────────────
TEMPLATES = {
    "ask_name":            "Olá! Pra começarmos, qual é o seu nome?",
    "greet_after_name":    "Obrigado, {nome}! 😊 Vamos ao seu pedido.",
    "ask_slot":            "{pergunta}",
    "confirm_order":       "✅ Pedido confirmado: {qt}x {item} para {data} em {bairro}{urgente}. Avisaremos quando estivermos a caminho.",
    "group_notification":  "📅 {nome} pediu {qt}x {item} em {bairro} para {data}{urgente}.",
    "delivery_fallback":   "Claro, {nome}, estarei aí por volta de {hora_prevista}. Precisa de mais alguma coisa?",
    "catalogue":           "{catalogo_text}"  # texto gerado dinamicamente
}

# ─── CATÁLOGO (mini-BD) ─────────────────────────────────────────────────────
CATALOGUE_FILE = "catalogo.json"
def load_catalogue():
    try:
        with open(CATALOGUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
catalogue = load_catalogue()

def get_catalogue_text():
    lines = [f"- {item}: R${price}" for item, price in catalogue.items()]
    return "Aqui está nosso catálogo de produtos de limpeza de 5L:\n" + "\n".join(lines)

# ─── ARMAZENAMENTO DE ESTADO ────────────────────────────────────────────────
STATE_FILE    = "estados.json"
CUSTOMER_FILE = "clientes.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

estados  = load_json(STATE_FILE)
clientes = load_json(CUSTOMER_FILE)

# ─── UTILITÁRIAS ───────────────────────────────────────────────────────────
def render(key, **params):
    text = TEMPLATES[key]
    return text.format(**params)

def send_whatsapp_message(phone, text):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN}
    try:
        r = requests.post(url, json={"phone":phone, "message":text, "type":"text"}, headers=headers)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {r.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

def send_group_message(text):
    if ZAPI_GROUP_ID:
        send_whatsapp_message(ZAPI_GROUP_ID, text)

# ─── AGENDAMENTO ────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.start()

def enviar_motivacao():
    frase = "Cada desafio superado no código é um passo a mais rumo ao seu objetivo: continue codando com confiança!"
    send_group_message(frase)

scheduler.add_job(enviar_motivacao, trigger="cron", hour=8, minute=0, timezone="America/Sao_Paulo")

# ─── PARSER DE SLOTS ───────────────────────────────────────────────────────
import re

def extrair_slots(msg):
    # quick regex fallback for item, qt e data
    qt_match = re.search(r"(\d+)", msg)
    item = next((i for i in catalogue if i.lower() in msg.lower()), None)
    data = "amanhã" if "amanhã" in msg.lower() else None
    return {
        "item": item,
        "qt": int(qt_match.group(1)) if qt_match else None,
        "data": data,
        "bairro": None,
        "urgente": "urgente" in msg.lower(),
        "faltando": [k for k,v in {
            "item": item,
            "qt": qt_match,
            "data": data
        }.items() if not v]
    }

# ─── PERGUNTAS POR SLOTS ──────────────────────────────────────────────────
SLOT_QUESTIONS = {
    "item":   "Qual produto você gostaria de pedir?",
    "qt":     "Quantas unidades?",
    "data":   "Para qual data você quer a entrega?",
    "bairro": "Em qual bairro?",
    "urgente":"Essa entrega é urgente? (sim/não)"
}

# ─── ROTAS ────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data  = request.get_json()
    phone = data.get("phone")
    msg   = data.get("text",{}).get("message","" ).strip()
    if not phone or not msg or data.get("fromMe"): return jsonify({"status":"ignored"})

    # fluxo de pergunta de nome
    if phone not in clientes or not clientes[phone].get("nome"):
        send_whatsapp_message(phone, render("ask_name"))
        clientes[phone] = {"nome":None, "pedido":{}}
        save_json(CUSTOMER_FILE, clientes)
        return jsonify({"status":"ask_name"})
    if clientes[phone]["nome"] is None:
        clientes[phone]["nome"] = msg.title()
        save_json(CUSTOMER_FILE, clientes)
        send_whatsapp_message(phone, render("greet_after_name", nome=clientes[phone]["nome"]))
        # enviar catálogo
        send_whatsapp_message(phone, render("catalogue", catalogo_text=get_catalogue_text()))
        return jsonify({"status":"name_saved"})

    # fallback de status de entrega
    last = estados.get(phone,{}).get("pedido_confirmado")
    if last and any(w in msg.lower() for w in ["amanhã","entrega","chega"]):
        hora = (datetime.now()+timedelta(hours=2)).strftime("%Hh%M")
        send_whatsapp_message(phone, render("delivery_fallback", nome=clientes[phone]["nome"], hora_prevista=hora))
        return jsonify({"status":"delivery_status"})

    # slot filling
    state = estados.get(phone,{})
    if state.get("esperando"):
        key = state.pop("esperando")
        state[key] = msg.lower() in ("sim","s") if key=="urgente" else msg
        missing = [k for k in STATE_KEYS if not state.get(k)]
        if missing:
            nxt = missing[0]; state["esperando"] = nxt
            estados[phone] = state; save_json(STATE_FILE, estados)
            send_whatsapp_message(phone, SLOT_QUESTIONS[nxt]); return jsonify({"status":"ask_slot"})
        slots = state; estados.pop(phone)
    else:
        slots = extrair_slots(msg)
        if slots.get("faltando"):
            nxt = slots["faltando"][0]; slots["esperando"]=nxt
            estados[phone] = slots; save_json(STATE_FILE, estados)
            send_whatsapp_message(phone, SLOT_QUESTIONS[nxt]); return jsonify({"status":"ask_slot"})

    # confirmar pedido
    nome = clientes[phone]["nome"]
    urgente_txt = " (URGENTE)" if slots["urgente"] else ""
    send_whatsapp_message(phone, render("confirm_order", **slots, urgente=urgente_txt))
    # notificar grupo
    estados[phone] = {"pedido_confirmado":slots}
    grp = render("group_notification", nome=nome, **slots, urgente=urgente_txt)
    send_group_message(grp)
    return jsonify({"status":"order_complete"})

@app.route("/", methods=["GET"])
def home(): return "Bot rodando!",200

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)), debug=True)
