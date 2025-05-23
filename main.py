from flask import Flask, request, jsonify
import os
import requests
import logging

# ─── Setup básico de logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s"
)

app = Flask(__name__)

# ─── Configuração da Z-API via ENV ─────────────────────────────────────────
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.environ.get("ZAPI_TOKEN")

# ─── Função de Parsing do Webhook ───────────────────────────────────────────
def parse_zapi_payload(data: dict):
    """
    Tenta extrair (phone, text) de diferentes formatos de payload da Z-API.
    Retorna (phone, text) ou (None, None) se não encontrar.
    """
    # 1) Quando vem dentro de "message": { "from":..., "text": { "body" } }
    if "message" in data and isinstance(data["message"], dict):
        msg = data["message"]
        phone = msg.get("from")
        txt = msg.get("text", {})
        if isinstance(txt, dict):
            return phone, txt.get("body") or txt.get("message")

    # 2) Quando o webhook envia no root: "text": { "message":... }
    if "text" in data and isinstance(data["text"], dict):
        phone = data.get("from") or data.get("phone")
        return phone, data["text"].get("body") or data["text"].get("message")

    # 3) Tipo ReceivedCallback (status='RECEIVED')
    t = data.get("type", "")
    if isinstance(t, str) and t.lower().startswith("received"):
        phone = data.get("from") or data.get("phone")
        txt = data.get("text", {})
        if isinstance(txt, dict):
            return phone, txt.get("message") or txt.get("body")

    # não reconheceu
    return None, None

# ─── Função de Envio para a Z-API ───────────────────────────────────────────
def send_to_zapi(phone: str, message: str):
    if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
        return False, "Z-API não configurada (env vars ausentes)"

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

# ─── Rota de Healthcheck ───────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def healthcheck():
    return "✅ Bot do WhatsApp está rodando!", 200

# ─── Rota de Webhook ────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido em /webhook")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("⚠️ JSON inválido ou vazio")
        return jsonify({"status": "error", "detail": "JSON inválido"}), 400

    logging.info(f"📦 Payload bruto: {data}")
    phone, text = parse_zapi_payload(data)
    if not phone or not text:
        logging.warning("⚠️ Payload sem telefone/texto conhecido → ignorando")
        return jsonify({"status": "ignored"}), 200

    logging.info(f"📞 De: {phone}  |  ✉️ Msg: {text}")

    # resposta estática (você pode criar lógica de intenções aqui)
    resposta = "Olá! Recebemos sua mensagem e logo retornaremos. 🙂"

    success, detail = send_to_zapi(phone, resposta)
    if success:
        logging.info(f"✅ Enviado para {phone}: {detail}")
        return jsonify({"status": "message sent"}), 200
    else:
        logging.error(f"❌ Falha ao enviar para {phone}: {detail}")
        return jsonify({"status": "error", "detail": detail}), 500

# ─── Entrada ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
