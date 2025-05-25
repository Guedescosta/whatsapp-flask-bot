import os
import logging
import requests
from flask import Flask, request, jsonify
import openai

# Configurações
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")  # Se sua instância exige
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GRUPO_AVISOS = "5541997083679"  # grupo "Vendas - IA"

# Inicialização
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
openai.api_key = OPENAI_API_KEY

# Lista para controle de loop (último número que recebeu msg)
ultimos_contatos = {}

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
        logging.info(f"📤 Enviando para {phone} → {message}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logging.info(f"✅ Enviado: {response.text}")
    except requests.exceptions.RequestException as err:
        logging.error(f"❌ Erro ao enviar mensagem: {err} - {getattr(err.response, 'text', '')}")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp com GPT está rodando!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    phone = data.get("phone")
    message_data = data.get("text")
    text = message_data.get("message") if isinstance(message_data, dict) else None

    if not phone or not text:
        logging.warning("⚠️ Ignorado - sem telefone ou texto")
        return jsonify({"status": "ignored"})

    # Evitar loop: só responde se o número for novo ou texto diferente
    if ultimos_contatos.get(phone) == text:
        logging.info("♻️ Mensagem repetida ignorada para evitar loop")
        return jsonify({"status": "ignored", "reason": "loop_prevention"})

    ultimos_contatos[phone] = text

    logging.info(f"📞 De: {phone} | 📝 Msg: '{text}'")

    try:
        resposta = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um atendente educado, natural e prestativo. Responda como se fosse uma conversa humana e não um robô."},
                {"role": "user", "content": text}
            ]
        )
        reply = resposta.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        reply = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # Envia resposta para o cliente
    send_whatsapp_message(phone, reply)

    # Envia notificação para o grupo
    grupo_msg = f"📬 Nova mensagem de {phone}\n📝: {text}\n🤖: {reply}"
    send_whatsapp_message(GRUPO_AVISOS, grupo_msg)

    return jsonify({"status": "success"})

if __name__ == "__main__":
    app.run(debug=True)
