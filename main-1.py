from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

INSTANCE_ID = os.getenv("ZAPI_ID")
TOKEN = os.getenv("ZAPI_TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando com sucesso! ✅", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    try:
        sender = data["message"]["from"]
        msg = data["message"]["text"]["body"]

        print(f"Mensagem de {sender}: {msg}")

        resposta = f"Olá! Recebemos sua mensagem: \"{msg}\". Em breve entraremos em contato 😊"
        send_message(sender, resposta)

    except Exception as e:
        print("Erro ao processar mensagem:", e)

    return jsonify({"status": "recebido"}), 200

def send_message(phone, message):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    print("Resposta da Z-API:", response.text)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)