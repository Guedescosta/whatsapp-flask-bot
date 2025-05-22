from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

# Tokens da Z-API (devem estar configurados nas variáveis de ambiente no Render)
INSTANCE_ID = os.getenv("INSTANCE_ID")
TOKEN = os.getenv("TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando! ✅"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    try:
        message = data['message']['text']['body']
        number = data['message']['from']

        resposta = f"Olá! Recebemos sua mensagem: \"{message}\""
        send_message(number, resposta)

    except Exception as e:
        print("Erro no webhook:", e)

    return jsonify({"status": "mensagem processada"}), 200

def send_message(phone, message):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    r = requests.post(url, json=payload, headers=headers)
    print("Resposta da Z-API:", r.text)

if __name__ == "__main__":
    app.run()
