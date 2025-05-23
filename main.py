from flask import Flask, request, jsonify
import os
import requests
import logging

# → Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s"
)

app = Flask(__name__)

# → Variáveis de ambiente para Z-API
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.environ.get("ZAPI_TOKEN")

def parse_webhook(data: dict):
    """
    Tenta extrair (phone, text) de diferentes formatos de payload Z-API.
    Retorna (phone, text) ou (None, None) se não encontrar.
    """
    # 1) Formato antigo com chave 'message'
    if "message" in data and isinstance(data["message"], dict):
        msg = data["message"]
        phone = msg.get("from")
        text_field = msg.get("text", {})
        if isinstance(text_field, dict):
            # pode vir em 'body' ou 'message'
            return phone, text_field.get("body") or text_field.get("message")
    # 2) Formato direto com 'text' no root
    if "text" in data and isinstance(data["text"], dict):
        phone = data.get("from")
        return phone, data["text"].get("body") or data["text"].get("message")
    # 3) Payload tipo RECEIVED (ReceivedCallback)
    if data.get("type") and data["type"].lower().startswith("received"):
        phone = data.get("from") or data.get("phone")
        text_field = data.get("text", {})
        if isinstance(text_field, dict):
            return phone, text_field.get("message") or text_field.get("body")
    # → não reconheceu
    return None, None

def send_whatsapp(phone: str, message: str):
    """Envia mensagem via Z-API e retorna (sucesso, detalhe)."""
    if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
        return False, "Configuração de Z-API ausente"

    url = (
        f"https://api.z-api.io/instances/"
        f"{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True, resp.json()
    except requests.exceptions.RequestException as e:
        return False, str(e)

@app.route("/", methods=["GET"])
def healthcheck():
    return "✅ Bot do WhatsApp está rodando com sucesso!", 200

@app.route("/", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("⚠️ Payload vazio ou JSON inválido")
        return jsonify({"status": "error", "detail": "JSON inválido"}), 400

    logging.info(f"📦 Payload bruto: {data}")
    phone, text = parse_webhook(data)
    if not phone or not text:
        logging.warning("⚠️ Estrutura de payload não reconhecida ou sem telefone/texto")
        return jsonify({"status": "ignored"}), 200

    logging.info(f"📞 Telefone: {phone}  |  ✉️ Texto: {text}")

    # → Aqui você pode melhorar: NLU, intenções, etc.
    resposta = "Olá! Recebemos sua mensagem e logo retornamos. 🙂"

    success, detail = send_whatsapp(phone, resposta)
    if success:
        logging.info(f"✅ Mensagem enviada: {detail}")
        return jsonify({"status": "message sent"}), 200
    else:
        logging.error(f"❌ Erro ao enviar: {detail}")
        return jsonify({"status": "error", "detail": detail}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
