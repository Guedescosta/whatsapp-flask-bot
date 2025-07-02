from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── ENVIRONMENT ──────────────────────────────────────────────────────────────
env = {
    'ZAPI_INSTANCE_ID':  os.getenv('ZAPI_INSTANCE_ID'),
    'ZAPI_TOKEN':        os.getenv('ZAPI_TOKEN'),
    'ZAPI_CLIENT_TOKEN': os.getenv('ZAPI_CLIENT_TOKEN'),
    'OPENAI_API_KEY':    os.getenv('OPENAI_API_KEY'),
    'ZAPI_GROUP_ID':     os.getenv('ZAPI_GROUP_ID'),
}

# ─── OPENAI CLIENT ────────────────────────────────────────────────────────────
openai_client = OpenAI(
    api_key=env['OPENAI_API_KEY'],
    http_client=httpx.Client()
)

# ─── SISTEMA ─────────────────────────────────────────────────────────────────
system_prompt = os.getenv('SYSTEM_PROMPT') or (
    "Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza. "
    "Em cada mensagem do cliente, identifique em pensamento os parâmetros: "
    "item, qt, data, bairro, urgente. Se faltar algum, pergunte de modo natural. "
    "Assim que tiver todos, confirme a venda e notifique o grupo. "
    "Quando confirmar a venda, inclua ao final UMA ÚNICA LINHA começando com “GRUPO: ” "
    "seguida do resumo sucinto (ex: “GRUPO: Maria – 2x Lava Roupas para amanhã no Centro (URGENTE)”). "
    "Para qualquer outra pergunta, responda normalmente."
)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str):
    url = (
        f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}"
        f"/token/{env['ZAPI_TOKEN']}/send-text"
    )
    headers = {
        'Content-Type': 'application/json',
        'Client-Token': env['ZAPI_CLIENT_TOKEN']
    }
    payload = {'phone': phone, 'message': message, 'type': 'text'}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

def split_group_summary(full_reply: str):
    """
    Se existir uma linha que comece com "GRUPO:", devolve (user_text, group_text).
    Caso contrário, devolve (full_reply, None).
    """
    lines = full_reply.splitlines()
    user_lines = []
    group_line = None
    for ln in lines:
        if ln.startswith("GRUPO:"):
            group_line = ln[len("GRUPO:"):].strip()
        else:
            user_lines.append(ln)
    return ("\n".join(user_lines).strip(), group_line)

# ─── WEBHOOK ──────────────────────────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json() or {}
    phone = data.get('phone')
    text  = data.get('text', {}).get('message')
    if not phone or not text or data.get('fromMe'):
        return jsonify({'status': 'ignored'})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # Chat completion
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user',   'content': text}
    ]
    try:
        resp = openai_client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=messages
        )
        full_reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro GPT: {e}")
        full_reply = "Desculpe, algo deu errado."

    # Separa o que vai pro cliente e o que vai pro grupo
    user_text, group_summary = split_group_summary(full_reply)

    # 1) Envia ao cliente
    send_whatsapp_message(phone, user_text)

    # 2) Envia ao grupo somente o resumo da venda
    if env['ZAPI_GROUP_ID'] and group_summary:
        send_whatsapp_message(env['ZAPI_GROUP_ID'], group_summary)

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def home():
    return 'Bot está ativo', 200

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000))
    )
