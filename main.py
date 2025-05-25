import os
import logging
import requests
from flask import Flask, request, jsonify
import openai

# Configurações do ambiente
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")  # Se não for obrigatório, pode remover
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

oai_headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}"
}
openai.api_key = OPENAI_API_KEY

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": message,
        "type": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }
    if ZAPI_CLIENT_TOKEN:
        headers["Client-Token"] = ZAPI_CLIENT_TOKEN

    try:
        logging.info(f"📤 Enviando mensagem para {phone} → {message}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logging.info(f"✅ Enviado com sucesso: {response.text}")
    except requests.exceptions.HTTPError as err:
        logging.error(f"❌ Erro ao enviar mensagem: {err} - {response.text}")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"✉️ Webhook recebido")
    logging.info(f"📦 Payload bruto: {data}")

    phone = data.get("phone")
    message_data = data.get("text")
    text = message_data.get("message") if isinstance(message_data, dict) else None

    if not phone or not text:
        logging.warning("⚠️ Dados insuficientes, ignorando mensagem")
        return jsonify({"status": "ignored"})

    logging.info(f"📞 De: {phone} | 📘 Msg: '{text}'")

    # Integração com GPT
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um atendente educado, prestativo e natural. Responda como se fosse uma conversa humana."},
                {"role": "user", "content": text}
            ]
        )
        reply = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"❌ Erro no ChatGPT: {e}")
        reply = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    send_whatsapp_message(phone, reply)
    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True)
