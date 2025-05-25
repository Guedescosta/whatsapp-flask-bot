from flask import Flask, request, jsonify
import logging
import requests
import openai
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Configurações (ajuste suas variáveis de ambiente)
ZAPI_INSTANCE_ID = "3DFAED34CAF760CDDF170A1EFCACDE10"
ZAPI_TOKEN = "97DAA07311ACEFFA36DF23AF"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Configurar a chave da OpenAI corretamente
openai.api_key = OPENAI_API_KEY

# Controle de loop para evitar respostas repetidas
ultimos_contatos = {}

def send_whatsapp_message(phone, text):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": text}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {response.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    phone = data.get("phone")
    msg = data.get("text", {}).get("message")

    if not phone or not msg:
        return jsonify({"status": "ignored"})

    # Ignora mensagens enviadas pelo próprio bot
    if data.get("fromMe", False):
        logging.info("👤 Mensagem própria—ignorada")
        return jsonify({"status": "ignored_self"})

    # Remove formatação e pega só o início da mensagem (simples)
    msg_pura = msg.strip().lower().split("\n")[0]

    # Previne loop (mensagem duplicada)
    if ultimos_contatos.get(phone) == msg_pura:
        logging.info("♻️ Mensagem repetida—ignorada para evitar loop")
        return jsonify({"status": "loop_prevented"})

    # Atualiza último contato
    ultimos_contatos[phone] = msg_pura

    # Gera resposta com GPT
    try:
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um atendente humano, educado e natural. Responda como um vendedor experiente da BG Produtos de Limpeza. Seja direto, mas simpático. Fale como se fosse o próprio Thiago."
                },
                {"role": "user", "content": msg}
            ]
        )
        resposta = completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # Envia a resposta ao cliente
    send_whatsapp_message(phone, resposta)

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True)
