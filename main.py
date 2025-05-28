from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
import json
import re
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

# cliente OpenAI sem proxies
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client()
)

# APScheduler para jobs em background
scheduler = BackgroundScheduler()
logging.info("🔄 Iniciando APScheduler...")
scheduler.start()

# ─── ARMAZENAMENTO SIMPLES EM JSON ──────────────────────────────────────────────
CLIENTES_FILE = "clientes.json"
ESTADOS_FILE  = "estados.json"
PEDIDOS_FILE  = "pedidos.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

clientes = load_json(CLIENTES_FILE)   # { phone: nome }
estados  = load_json(ESTADOS_FILE)    # { phone: estado_atual }
pedidos  = load_json(PEDIDOS_FILE)    # { phone: pedido_em_andamento }

# ─── UTILITÁRIAS ───────────────────────────────────────────────────────────────
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

# Cron diário de motivação às 08:00 (Brasília)
scheduler.add_job(
    enviar_motivacao,
    trigger="cron",
    hour=8,
    minute=0,
    timezone="America/Sao_Paulo"
)

# Job de teste único para daqui a 1 minuto
scheduler.add_job(
    enviar_motivacao,
    trigger="date",
    run_date=datetime.now() + timedelta(minutes=1)
)

# ─── FLUXO DE PEDIDOS ───────────────────────────────────────────────────────────
def tratar_fluxo_pedido(phone, msg):
    estado = estados.get(phone)
    pedido = pedidos.get(phone, {})

    # 1) Detecta pedido inicial: "quero X Item"
    if estado is None and msg.lower().startswith("quero"):
        parts = msg.lower().split()
        qt = int(next((w for w in parts if w.isdigit()), 1))
        # identifica o item entre palavras-chave
        for key in ["branquinho", "lava roupas", "amaciante", "desinfetante", "água sanitária", "alvejante", "detergente", "álcool perfumado", "kit"]:
            if key in msg.lower():
                item = key.title()
                break
        else:
            item = "Produto"
        pedidos[phone] = {"item": item, "qt": qt}
        estados[phone] = "aguardando_data"
        save_json(PEDIDOS_FILE, pedidos)
        save_json(ESTADOS_FILE, estados)
        return (
            "asked_date",
            f"Ok, {qt} {item}. Para qual data você deseja a entrega?",
            None
        )

    # 2) Pergunta data
    if estado == "aguardando_data":
        pedidos[phone]["data"] = msg
        estados[phone] = "aguardando_bairro"
        save_json(PEDIDOS_FILE, pedidos)
        save_json(ESTADOS_FILE, estados)
        return (
            "asked_bairro",
            f"Perfeito. Em qual bairro devo entregar no dia {msg}?",
            None
        )

    # 3) Pergunta bairro
    if estado == "aguardando_bairro":
        pedidos[phone]["bairro"] = msg
        estados[phone] = "aguardando_urgencia"
        save_json(PEDIDOS_FILE, pedidos)
        save_json(ESTADOS_FILE, estados)
        return (
            "asked_urgencia",
            "Ótimo! Essa entrega é urgente? (sim/não)",
            None
        )

    # 4) Pergunta urgência e finaliza
    if estado == "aguardando_urgencia":
        urg = msg.lower() in ("sim", "s", "urgente")
        pedidos[phone]["urgente"] = urg
        p = pedidos.pop(phone)
        estados.pop(phone, None)
        save_json(PEDIDOS_FILE, pedidos)
        save_json(ESTADOS_FILE, estados)

        nome_cli = clientes.get(phone, phone)
        texto_cli = (
            f"✅ Pedido confirmado:\n"
            f"- {p['qt']}x {p['item']}\n"
            f"- Data: {p['data']}\n"
            f"- Bairro: {p['bairro']}\n"
            f"- Urgente: {'Sim' if p['urgente'] else 'Não'}"
        )
        texto_grp = (
            f"📅 Entrega agendada:\n"
            f"{nome_cli} pediu {p['qt']}x {p['item']} em {p['bairro']} "
            f"para {p['data']}{' (URGENTE)' if urg else ''}."
        )
        return ("order_confirmed", texto_cli, texto_grp)

    return None

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

    # validações iniciais
    if not phone or not msg or data.get("fromMe", False):
        return jsonify({"status": "ignored"})

    # prevenção de loop
    last = estados.get(f"{phone}_last_msg")
    if last == msg.lower():
        return jsonify({"status": "loop_prevented"})
    estados[f"{phone}_last_msg"] = msg.lower()

    # fluxo de coleta de nome
    nome = clientes.get(phone)
    estado_nome = estados.get(phone)
    if not nome and estado_nome != "aguardando_nome":
        send_whatsapp_message(phone, "Olá! Pra começarmos, qual é o seu nome? 😊")
        estados[phone] = "aguardando_nome"
        save_json(ESTADOS_FILE, estados)
        return jsonify({"status": "asked_name"})
    if estado_nome == "aguardando_nome":
        clean = sanitize_name(msg.title())
        if clean:
            clientes[phone] = clean
            save_json(CLIENTES_FILE, clientes)
            send_whatsapp_message(phone, f"Obrigado, {clean}! 😊 Agora podemos continuar.")
        else:
            send_whatsapp_message(
                phone,
                "Desculpe, não consegui entender. Pode me dizer seu nome de forma mais simples?"
            )
            return jsonify({"status": "asked_name"})
        estados.pop(phone, None)
        save_json(ESTADOS_FILE, estados)
        return jsonify({"status": "name_saved"})

    # fluxo de pedido
    fluxo = tratar_fluxo_pedido(phone, msg)
    if fluxo:
        status, resp_cli, resp_grp = fluxo
        send_whatsapp_message(phone, resp_cli)
        if resp_grp:
            send_group_message(resp_grp)
        return jsonify({"status": status})

    # atendimento normal com GPT
    saudacao = f"Olá, {clientes.get(phone, '')}! 😊"
    catalogo = (
        "Catálogo de produtos (5L): Lava roupas R$35, Amaciante R$35, "
        "Desinfetante R$30, Água sanitária R$25, Alvejante sem cloro R$30, "
        "Detergente R$30, Álcool perfumado R$40, Branquinho R$40; Kit 5 produtos R$145."
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

    save_json(ESTADOS_FILE, estados)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    )
