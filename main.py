from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
env = {
    'ZAPI_INSTANCE_ID': os.getenv('ZAPI_INSTANCE_ID'),
    'ZAPI_TOKEN':        os.getenv('ZAPI_TOKEN'),
    'ZAPI_CLIENT_TOKEN': os.getenv('ZAPI_CLIENT_TOKEN'),
    'OPENAI_API_KEY':    os.getenv('OPENAI_API_KEY'),
    'ZAPI_GROUP_ID':     os.getenv('ZAPI_GROUP_ID'),
}

# Inicializa cliente OpenAI
httpx_client   = httpx.Client()
openai_client = OpenAI(api_key=env['OPENAI_API_KEY'], http_client=httpx_client)

# Prompt do sistema (vendedor consultivo)
system_prompt = os.getenv('SYSTEM_PROMPT') or (
    "Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza.\n"
    "Em cada interação, identifique mentalmente: item, qt (quantidade), data, bairro e urgente.\n"
    "Se faltar algum destes, pergunte de forma natural sem parecer robô.\n"
    "Assim que todos estiverem definidos, confirme a venda para o cliente e, "
    "na ÚLTIMA linha da resposta, comece com 'GRUPO:' seguido de um breve resumo para o canal de vendas.\n"
    "Para tudo que não for fechamento de pedido, responda de forma consultiva e fluida."
)

# ─── FUNÇÃO AUXILIAR PARA ENVIO ────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str):
    """Envia texto via Z-API para número ou grupo."""
    url = (
        f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}"
        f"/token/{env['ZAPI_TOKEN']}/send-text"
    )
    headers = {
        'Content-Type': 'application/json',
        'Client-Token':  env['ZAPI_CLIENT_TOKEN']
    }
    payload = {'phone': phone, 'message': message, 'type': 'text'}
    try:
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {r.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

# ─── WEBHOOK ──────────────────────────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get('phone')
    text  = (data.get('text') or {}).get('message', '').strip()

    # Ignora mensagens sem número, sem texto ou enviadas por nós mesmos
    if not phone or not text or data.get('fromMe', False):
        return jsonify({'status': 'ignored'})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # Gera resposta pelo GPT
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user',   'content': text}
    ]
    try:
        resp  = openai_client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=messages
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erro GPT: {e}")
        reply = "Desculpe, algo deu errado."

    # Envia ao cliente
    send_whatsapp_message(phone, reply)

    # Dispara somente a linha começada com 'GRUPO:' para o canal de vendas
    grp_id = env.get('ZAPI_GROUP_ID')
    if grp_id:
        for line in reply.splitlines():
            if line.startswith('GRUPO:'):
                resumo = line[len('GRUPO:'):].strip()
                send_whatsapp_message(grp_id, resumo)
                break

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def home():
    return 'Bot está ativo', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
