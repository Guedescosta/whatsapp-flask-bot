from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

# variáveis de ambiente que você deve ter configurado
INSTANCE_ID     = os.environ["ZAPI_INSTANCE_ID"]
INSTANCE_TOKEN  = os.environ["ZAPI_TOKEN"]
CLIENT_TOKEN    = os.environ["ZAPI_CLIENT_TOKEN"]

API_URL = (
    f"https://api.z-api.io/instances/"
    f"{INSTANCE_ID}/token/{INSTANCE_TOKEN}/send-text"
)

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando! ✅"

@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        app.logger.info("🔔 Webhook recebido: %s", data)

        # extrai telefone e texto de ambos os formatos possíveis
        phone = None
        text  = None

        if "phone" in data and "text" in data:
            phone = data["phone"]
            t = data["text"]
            # costuma vir { "message": "texto aqui" }
            if isinstance(t, dict):
                text = t.get("message") or t.get("body")
            else:
                text = str(t)

        elif "message" in data:
            msg = data["message"]
            phone = msg.get("from") or msg.get("phone")
            t = msg.get("text", {})
            if isinstance(t, dict):
                text = t.get("body") or t.get("message")
            else:
                text = str(t)

        else:
            app.logger.warning("❌ Payload não reconhecido, ignorando.")
            return jsonify({"status": "ignored"}), 200

        if not phone or not text:
            app.logger.warning("⚠️ Telefone ou texto ausente. phone=%s text=%s", phone, text)
            return jsonify({"status": "no-action"}), 200

        app.logger.info("📨 Mensagem de %s: %s", phone, text)

        # monta o payload de resposta
        resposta = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"
        payload = {"phone": phone, "message": resposta}

        # cabeçalhos obrigatórios
        headers = {
            "Client-Token": CLIENT_TOKEN,
            "Content-Type": "application/json"
        }

        app.logger.info("➡️ Enviando resposta: %s", payload)
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        app.logger.info("✅ Resposta da Z-API: %s", resp.json())

        return jsonify({"status": "message sent"}), 200

    except requests.HTTPError as e:
        app.logger.error("❌ Erro ao enviar resposta: %s", e)
        return jsonify({"status": "error", "detail": str(e)}), 500
    except Exception as e:
        app.logger.exception("❌ Erro inesperado no webhook:")
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
