from flask import Flask, request, jsonify
import os
import logging
import requests

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

app = Flask(__name__)

# ── Variáveis de ambiente ──────────────────────────────────────────────────
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
ZAPI_BASE_URL    = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}"

if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("🚨 ZAPI_INSTANCE_ID ou ZAPI_TOKEN não definidos!")
    raise RuntimeError("Verifique as env vars ZAPI_INSTANCE_ID e ZAPI_TOKEN")

# ── Helper de envio ────────────────────────────────────────────────────────
def send_whatsapp(phone: str, message: str):
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}
    url = f"{ZAPI_BASE_URL}/send-text"
    try:
        logging.info(f"📤 POST {url} → payload={payload}")
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API respondeu: {resp.text}")
        return True, resp.json()
    except requests.HTTPError as e:
        logging.error(f"❌ HTTPError: {e} — {resp.text}")
        return False, resp.text
    except Exception as e:
        logging.error(f"❌ Erro no send_whatsapp: {e}")
        return False, str(e)

# ── Health-check ──────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando!", 200

# ── Webhook ────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    logging.info(f"📦 Payload bruto: {data}")

    phone = None
    text  = None

    # v2: ReceivedCallback / RECEIVED
    if data.get("phone") and isinstance(data.get("text"), dict):
        phone = data["phone"]
        text  = data["text"].get("message")

    # v1: message aninhada
    elif isinstance(data.get("message"), dict):
        m = data["message"]
        phone = m.get("from") or m.get("phone")
        t = m.get("text")
        if isinstance(t, dict):
            text = t.get("body") or t.get("message")
        elif isinstance(t, str):
            text = t

    if not phone or not text:
        logging.warning("⚠️ Sem phone/text — ignorando")
        return jsonify(status="ignored"), 200

    logging.info(f"📞 De: {phone} | Msg: “{text}”")
    resposta = "Olá! Recebemos sua mensagem e logo retornaremos. 😊"

    ok, detail = send_whatsapp(phone, resposta)
    if ok:
        return jsonify(status="sent"), 200
    else:
        return jsonify(status="error", detail=detail), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🚀 Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
