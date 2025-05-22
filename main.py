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
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"status": "ignored"}), 200

    message = data["message"]
    phone = message.get("from")
    text = message.get("text", {}).get("body")

    if not phone or not text:
        return jsonify({"status": "no-action"}), 200

    print(f"Mensagem recebida de {phone}: {text}")

    resposta = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": resposta
    }

    response = requests.post(url, json=payload)
    print("Resposta enviada:", response.text)

    return jsonify({"status": "message sent"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
