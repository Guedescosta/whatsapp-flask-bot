from flask import Flask, request, jsonify
import os
import logging
import requests

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
app = Flask(__name__)

# ── Variáveis de ambiente ──────────────────────────────────────────────────
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("🚨 ZAPI_INSTANCE_ID ou ZAPI_TOKEN não definidos!")
    raise RuntimeError("Verifique as env vars ZAPI_INSTANCE_ID e ZAPI_TOKEN")

# ── Helper para limpar telefone ─────────────────────────────────────────────
def clean_phone(raw: str) -> str | None:
    if not raw: return None
    digits = ''.join(filter(str.isdigit, raw))
    # Se vier sem 55 na frente e tiver 10 ou 11 dígitos, adiciona
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    # Se precisar do +, descomente abaixo:
    # if not digits.startswith("+"):
    #     digits = "+" + digits
    return digits if digits else None

# ── Função de envio ────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str):
    url = (
        f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}"
        f"/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {
        "phone": phone,
        "message": message,
        "type": "text"              # exigido pela Z-API
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_TOKEN  # cabeçalho obrigatório
    }

    logging.info(f"📤 POST {url} → payload={payload}")
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API respondeu: {resp.text}")
        return True, resp.json()
    except requests.exceptions.HTTPError as e:
        logging.error(f"❌ Z-API HTTPError: {e} — {resp.text}")
        return False, resp.text
    except Exception as e:
        logging.error(f"❌ Erro no send_whatsapp_message: {e}")
        return False, str(e)

# ── Health-check ───────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando!", 200

# ── Webhook endpoint ───────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    logging.info(f"📦 Payload bruto: {data}")

    phone = None
    text  = None

    # 1) Caso ReceivedCallback / RECEIVED
    if data.get("phone") and isinstance(data.get("text"), dict):
        phone = clean_phone(data["phone"])
        text  = data["text"].get("message")

    # 2) Fallback aninhado em data['message']
    elif isinstance(data.get("message"), dict):
        msg = data["message"]
        phone = clean_phone(msg.get("from") or msg.get("phone"))
        t = msg.get("text")
        if isinstance(t, dict):
            text = t.get("body") or t.get("message")
        elif isinstance(t, str):
            text = t

    if not phone or not text:
        logging.warning(f"⚠️ Missing phone/text — phone={phone} text={text}")
        return jsonify(status="ignored"), 200

    logging.info(f"📞 De: {phone} | 📝 Msg: '{text}'")

    resposta = "Olá! Recebemos sua mensagem e logo retornaremos."
    success, detail = send_whatsapp_message(phone, resposta)
    if success:
        return jsonify(status="sent"), 200
    else:
        return jsonify(status="error", detail=detail), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🚀 Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
