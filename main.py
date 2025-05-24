from flask import Flask, request, jsonify
import os
import requests
import logging

# 1) Configuração de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

app = Flask(__name__)

# 2) Apenas duas env vars
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("⚠️ As env vars ZAPI_INSTANCE_ID e ZAPI_TOKEN devem estar definidas!")
    # Em produção você pode querer abortar aqui.

# Aux — endpoint da Z-API
ZAPI_URL = (
    "https://api.z-api.io"
    f"/instances/{ZAPI_INSTANCE_ID}"
    f"/token/{ZAPI_TOKEN}"
    "/send-text"
)

def send_text(phone: str, message: str):
    """Envia a mensagem via Z-API e retorna (sucesso, detalhe)."""
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}
    logging.info(f"📤 POST→Z-API {ZAPI_URL}  payload={payload}")
    try:
        resp = requests.post(ZAPI_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API respondeu: {resp.text}")
        return True, resp.json()
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"❌ Z-API HTTPError: {http_err} — {resp.text}")
        return False, resp.text
    except Exception as e:
        logging.error(f"❌ Erro ao chamar Z-API: {e}")
        return False, str(e)

@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando!"

@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    logging.info(f"📦 Payload bruto: {data}")

    phone = None
    text  = None

    # 1) Caso “novo”: tudo no root, .get("text",{})["message"]
    if data and "phone" in data and isinstance(data.get("text"), dict):
        phone = data.get("phone")
        text  = data["text"].get("message")

    # 2) Caso “antigo”: mensagem aninhada
    elif data and isinstance(data.get("message"), dict):
        msg = data["message"]
        phone = msg.get("from") or msg.get("phone")
        # nLU: pode vir como body ou como message
        txt = msg.get("text")
        if isinstance(txt, dict):
            text = txt.get("body") or txt.get("message")
        elif isinstance(txt, str):
            text = txt

    if not phone or not text:
        logging.warning("⚠️ Payload sem telefone/texto — ignorando")
        return jsonify({"status": "ignored"}), 200

    logging.info(f"📞 De: {phone}  |  📝 Msg: “{text}”")

    # Resposta simples
    resposta = "Olá! Recebemos sua mensagem e logo retornaremos. 😊"

    success, detail = send_text(phone, resposta)
    if success:
        return jsonify({"status": "message sent"}), 200
    else:
        return jsonify({"status": "error", "detail": detail}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"🚀 Iniciando Flask na porta {port}")
    app.run(host="0.0.0.0", port=port)
