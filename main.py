from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Environment variables
env = {
    'ZAPI_INSTANCE_ID': os.getenv('ZAPI_INSTANCE_ID'),
    'ZAPI_TOKEN': os.getenv('ZAPI_TOKEN'),
    'ZAPI_CLIENT_TOKEN': os.getenv('ZAPI_CLIENT_TOKEN'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'ZAPI_GROUP_ID': os.getenv('ZAPI_GROUP_ID'),
}

# Initialize OpenAI client
openai_client = OpenAI(
    api_key=env['OPENAI_API_KEY'],
    http_client=httpx.Client()
)

# System prompt for Thiago-vendedor
system_prompt = os.getenv('SYSTEM_PROMPT') or (
    "Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza. "
    "Em cada mensagem do cliente, identifique em pensamento os parâmetros: item, qt, data, bairro, urgente. "
    "Se faltar algum, pergunte de modo natural. Assim que tiver todos, confirme a venda e notifique o grupo. "
    "Para qualquer outra pergunta, responda normalmente."
)

# Helper to send WhatsApp message via Z-API
def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}/token/{env['ZAPI_TOKEN']}/send-text"
    headers = {
        'Content-Type': 'application/json',
        'Client-Token': env['ZAPI_CLIENT_TOKEN']
    }
    payload = {'phone': phone, 'message': message, 'type': 'text'}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"Falha ao enviar para {phone}: {e}")

# Webhook endpoint
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    phone = data.get('phone')
    text = data.get('text', {}).get('message')
    if not phone or not text or data.get('fromMe'):
        return jsonify({'status': 'ignored'})

    # Compose chat completion
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': text}
    ]
    try:
        resp = openai_client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=messages
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erro GPT: {e}")
        reply = "Desculpe, algo deu errado."

    # Send user reply
    send_whatsapp_message(phone, reply)

    # If group ID defined, forward reply to group
    if env['ZAPI_GROUP_ID']:
        send_whatsapp_message(env['ZAPI_GROUP_ID'], reply)

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def home():
    return 'Bot está ativo', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
