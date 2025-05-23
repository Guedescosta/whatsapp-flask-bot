from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando! ✅"

@app.route("/", methods=["POST"])
def webhook():
    print("📥 Webhook recebido!")

    try:
        data = request.get_json()
        print("📦 Dados brutos recebidos:", data)

        message = None
        if "messages" in data and isinstance(data["messages"], list):
            message = data["messages"][0]
        elif "message" in data:
            message = data["message"]

        if not message:
            print("⚠️ Payload inválido (sem 'message')")
            return jsonify({"status": "ignored"}), 200

        phone = message.get("from")
        text = None

        # Trata texto como string ou dicionário
        if isinstance(message.get("text"), dict):
            text = message["text"].get("message") or message["text"].get("body")
        elif isinstance(message.get("text"), str):
            text = message["text"]

        print(f"📱 Telefone: {phone}")
        print(f"💬 Texto: {text}")

        if not phone or not text:
            print("⚠️ Telefone ou texto ausente na mensagem recebida.")
            return jsonify({"status": "no-action"}), 200

        print(f"✅ Mensagem recebida de {phone}: {text}")

        resposta = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"

        payload = {
            "phone": phone,
            "message": resposta
        }

        print("🚀 Enviando resposta para Z-API...")
        response = requests.post(url, json=payload)
        print("📤 Resposta da Z-API:", response.text)

        return jsonify({"status": "message sent"}), 200

    except Exception as e:
        print("❌ Erro inesperado:", str(e))
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
