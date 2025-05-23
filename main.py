from flask import Flask, request, jsonify
import os
import logging
import requests

# ——— Configuração de logging ———
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ——— App e variáveis de ambiente ———
app = Flask(__name__)
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
SEND_TEXT_URL    = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"

# ——— Health‐check ———
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando com sucesso!", 200

# ——— Webhook endpoint ———
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    if data is None:
        logging.warning("⚠️ JSON inválido ou vazio")
        return jsonify({"status": "invalid_json"}), 400

    logging.debug("📦 Payload bruto: %s", data)

    phone = None
    text  = None

    # 1) Caso “ReceivedCallback” da Z-API (payload “flat”)
    if isinstance(data.get("text"), dict) and data.get("phone"):
        phone = data["phone"]
        text  = data["text"].get("message")

    # 2) Caso wrapper em data["message"]
    elif isinstance(data.get("message"), dict):
        msg = data["message"]
        phone = msg.get("from")
        t = msg.get("text")
        if isinstance(t, dict):
            # varia entre 'body' ou 'message' dependendo da versão
            text = t.get("body") or t.get("message")
        else:
            text = t

    else:
        logging.warning("⚠️ Estrutura de payload não reconhecida — ignorando")
        return jsonify({"status": "ignored"}), 200

    # validação final
    if not phone or not text:
        logging.warning("⚠️ Falta telefone ou texto na mensagem — ignorando")
        return jsonify({"status": "ignored"}), 200

    logging.info("📲 Mensagem de %s: %r", phone, text)

    # resposta fixa (pode inserir NLP/intenções aqui)
    resposta = "Olá! 👋 Recebemos sua mensagem e em breve retornaremos."

    # envia a mensagem de volta
    try:
        resp = requests.post(
            SEND_TEXT_URL,
            json={"phone": phone, "message": resposta},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        logging.info("✅ Z-API respondeu: %s", resp.text)
        return jsonify({"status": "sent"}), 200

    except requests.exceptions.HTTPError as e:
        logging.error("❌ Z-API HTTPError: %s — %s", e, resp.text)
        return jsonify({"status": "error", "detail": resp.text}), 500
    except requests.exceptions.RequestException as e:
        logging.error("❌ Erro de requisição à Z-API: %s", e)
        return jsonify({"status": "error", "detail": str(e)}), 500

# ——— Inicialização ———
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info("🚀 Iniciando na porta %d", port)
    app.run(host="0.0.0.0", port=port)
