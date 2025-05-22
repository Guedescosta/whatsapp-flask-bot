from flask import Flask, request, jsonify import os import requests

app = Flask(name)

ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID") ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

@app.route("/", methods=["GET"]) def index(): return "Bot do WhatsApp está rodando! ✅"

@app.route("/", methods=["POST"]) def whatsapp_webhook(): data = request.get_json()

if not data:
    return jsonify({"error": "Nenhum dado recebido"}), 400

message = data.get("message", {})
sender = message.get("from")
text = message.get("text", {}).get("body")

if sender and text:
    resposta = f"Recebido: {text}"
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": sender,
        "message": resposta
    }
    headers = {"Content-Type": "application/json"}
    requests.post(url, json=payload, headers=headers)

return jsonify({"status": "Mensagem processada"})

if name == "main": port = int(os.environ.get("PORT", 5000)) app.run(host="0.0.0.0", port=port)

