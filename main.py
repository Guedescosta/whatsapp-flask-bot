from flask import Flask, request, jsonify
import os, requests, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__)

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("Z-API credentials missing!")
    raise RuntimeError("Configure ZAPI_INSTANCE_ID e ZAPI_TOKEN")

def send_whatsapp(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True, resp.json()
    except Exception as e:
        logging.error(f"❌ Erro enviando a {phone}: {e}")
        return False, str(e)

@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando com sucesso!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status":"error","detail":"JSON inválido"}), 400

    logging.info(f"📦 Payload bruto: {data}")

    phone = text = None

    # 1) Qualquer payload com phone + text.message
    if "phone" in data and isinstance(data.get("text"), dict):
        phone = data["phone"]
        text  = data["text"]["message"]

    # 2) Caso legacy “RECEIVED”
    elif data.get("type") == "RECEIVED" and isinstance(data.get("text"), dict):
        phone = data.get("from")
        text  = data["text"]["message"]

    # 3) Caso aninhado em data["message"]
    elif "message" in data:
        m = data["message"]
        phone = m.get("from")
        t = m.get("text")
        text  = t["message"] if isinstance(t, dict) else t

    if not phone or not text:
        logging.warning("⚠️ Payload sem telefone/texto — ignorando.")
        return jsonify({"status":"ignored"}), 200

    logging.info(f"📞 De: {phone}  |  ✉️ Msg: {text}")

    resposta = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"
    ok, detail = send_whatsapp(phone, resposta)
    code = 200 if ok else 500
    return jsonify({"status": ok and "message sent" or "error", "detail": detail}), code

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🚀 Iniciando em 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
