from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
import json
import re
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

# cliente OpenAI sem proxies
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client()
)

# APScheduler para jobs em background
scheduler = BackgroundScheduler()

# ─── ARMAZENAMENTO SIMPLES EM JSON ──────────────────────────────────────────────
CLIENTES_FILE = "clientes.json"
ESTADOS_FILE  = "estados.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

clientes = load_json(CLIENTES_FILE)   # {"55419...": "Joana"}
estados  = load_json(ESTADOS_FILE)    # {"55419...": "aguardando_nome"}

# ─── UTILITÁRIAS ────────────────────────────────────────────────────────────────
def sanitize_name(raw: str) -> str:
    name = re.split(r"[\d–\-]", raw)[0].strip()
    return name if re.fullmatch(r"[A-Za-zÀ-ÿ ]+", name) else ""

# ─── ENVIO PELO Z-API ───────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, text: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": text, "type": "text"}
    headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

def send_group_message(text: str):
    if ZAPI_GROUP_ID:
        send_whatsapp_message(ZAPI_GROUP_ID, text)
    else:
        logging.warning("⚠️ ZAPI_GROUP_ID não configurado; não foi possível enviar ao grupo.")

# ─── JOBS DE AGENDAMENTO ────────────────────────────────────────────────────────
def enviar_motivacao():
    frase = "“Cada desafio superado no código é um passo a mais rumo ao seu objetivo: continue codando com confiança!”"
    send_group_message(frase)

# Agenda diária de motivação às 08:00 Brasília
scheduler.add_job(
    enviar_motivacao,
    trigger="cron",
    hour=8,
    minute=0,
    timezone="America/Sao_Paulo"
)

# ─── ROTAS ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data     = request.get_json()
    phone    = data.get("phone")
    raw_name = data.get("senderName", "")
    msg      = data.get("text", {}).get("message", "").strip()
    is_group = data.get("isGroup", False)

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    if not phone or not msg or data.get("fromMe", False):
        return jsonify({"status": "ignored"})

    # Prevenção de loop
    last = estados.get(f"{phone}_last_msg")
    if last == msg.lower():
        return jsonify({"status": "loop_prevented"})
    estados[f"{phone}_last_msg"] = msg.lower()

    # Fluxo de coleta de nome
    nome = clientes.get(phone)
    estado = estados.get(phone)

    if not nome and estado != "aguardando_nome":
        send_whatsapp_message(phone, "Olá! Pra começarmos, qual é o seu nome? 😊")
        estados[phone] = "aguardando_nome"
        save_json(ESTADOS_FILE, estados)
        return jsonify({"status": "asked_name"})

    if estado == "aguardando_nome":
        clean = sanitize_name(msg.title())
        if clean:
            clientes[phone] = clean
            save_json(CLIENTES_FILE, clientes)
            send_whatsapp_message(phone, f"Obrigado, {clean}! 😊 Agora podemos continuar.")
        else:
            send_whatsapp_message(phone,
                "Desculpe, não consegui entender. Pode me dizer seu nome de forma mais simples?")
            return jsonify({"status": "asked_name"})

        estados.pop(phone)
        save_json(ESTADOS_FILE, estados)
        return jsonify({"status": "name_saved"})

    # Atendimento normal
    saudacao = f"Olá, {clientes[phone]}! 😊"
    catalogo = (
        "Catálogo de produtos (5L): Lava roupas R$35, Amaciante R$35, "
        "Desinfetante R$30, Água sanitária R$25, Alvejante sem cloro R$30, "
        "Detergente R$30, Álcool perfumado R$40, Branquinho R$40; "
        "Kit 5 produtos R$145."
    )
    system_content = (
        f"{saudacao} Você é um atendente humano da BG Produtos de Limpeza. "
        "Fale como o Thiago: seja direto, simpático e profissional. "
        f"{catalogo}"
    )

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user",   "content": msg}
            ]
        )
        resposta = completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    if is_group:
        send_group_message(resposta)
    else:
        send_whatsapp_message(phone, resposta)

    # Salvar estados persistidos
    save_json(ESTADOS_FILE, estados)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    scheduler.start()
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    )
