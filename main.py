import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
import logging

# Inicializa Flask e log
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Variáveis de ambiente (configure no Render)
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializa o cliente OpenAI novo
client = OpenAI(api_key=OPENAI_API_KEY)

# Memória simples para evitar loop
ULTIMAS_MENSAGENS = {}

@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot do WhatsApp está rodando!"

@app.route("/", methods=["POST"])
def receber_mensagem():
    data = request.json
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload bruto: {data}")

    # Ignora mensagens enviadas por você mesmo
    if data.get("fromMe"):
        return jsonify({"status": "ignorado"}), 200

    telefone = data.get("phone")
    mensagem = data.get("text", {}).get("message", "")

    # Verifica se já respondeu a essa mensagem
    if ULTIMAS_MENSAGENS.get(telefone) == mensagem:
        return jsonify({"status": "loop evitado"}), 200

    ULTIMAS_MENSAGENS[telefone] = mensagem

    try:
        # Envia para o ChatGPT
        resposta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": mensagem}]
        )
        texto_resposta = resposta.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no ChatGPT: {e}")
        texto_resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # Envia a resposta via Z-API
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": telefone, "message": texto_resposta}
    response = requests.post(url, json=payload)

    logging.info(f"📤 Enviado para {telefone} → {texto_resposta}")
    logging.info(f"🧾 Resposta da Z-API: {response.text}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True)
