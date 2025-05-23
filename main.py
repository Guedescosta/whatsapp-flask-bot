import os
import logging
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ————— Configurações de Logging —————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ————— Variáveis de ambiente —————
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logger.error("Variáveis de ambiente ZAPI_INSTANCE_ID e/ou ZAPI_TOKEN não definidas!")
ZAPI_BASE_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

# ————— Rotas —————
@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando! ✅", 200

@app.route("/", methods=["POST"])
def webhook():
    logger.info("🔔 Webhook recebido")
    data = request.get_json(silent=True, force=True)
    if not data:
        logger.warning("⚠️ Nenhum JSON no payload")
        return jsonify({"status":"ignored","reason":"no_json"}), 200

    logger.info("📦 Payload bruto: %s", data)

    # — Normalização de formatos diferentes da Z-API —
    phone = None
    text  = None

    # Formato 1: {"message": {...}}
    if "message" in data:
        msg = data["message"]
        phone = msg.get("from") or msg.get("phone")
        text  = msg.get("text", {}).get("body")

    # Formato 2: payload top-level com "text": {"message": ...}
    elif "text" in data:
        phone = data.get("phone")
        text  = data.get("text", {}).get("message")

    else:
        logger.warning("⚠️ Payload sem 'message' ou 'text' — ignorando")
        return jsonify({"status":"ignored","reason":"no_message_key"}), 200

    if not phone or not text:
        logger.warning("⚠️ Falta phone ou texto — phone=%s, text=%s", phone, text)
        return jsonify({"status":"no_action","reason":"missing_phone_or_text"}), 200

    logger.info("📨 Mensagem de %s: %s", phone, text)

    # — Preparando resposta —
    reply_text = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"
    endpoint   = f"{ZAPI_BASE_URL}/send-text"
    payload    = {"phone": phone, "message": reply_text}

    try:
        r = requests.post(endpoint, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("✅ Resposta Z-API: %s", r.json())
    except Exception as e:
        logger.error("❌ Erro ao enviar resposta: %s", e)
        return jsonify({"status":"error", "detail": str(e)}), 500

    return jsonify({"status":"message_sent"}), 200

# ————— Execução local —————
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
