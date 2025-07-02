from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
from openai import OpenAI

# ─── APP SETUP ────────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
env = {
    'ZAPI_INSTANCE_ID':  os.getenv('ZAPI_INSTANCE_ID'),
    'ZAPI_TOKEN':        os.getenv('ZAPI_TOKEN'),
    'ZAPI_CLIENT_TOKEN': os.getenv('ZAPI_CLIENT_TOKEN'),
    'OPENAI_API_KEY':    os.getenv('OPENAI_API_KEY'),
    'ZAPI_GROUP_ID':     os.getenv('ZAPI_GROUP_ID'),
}

# Inicializa cliente OpenAI via httpx
httpx_client   = httpx.Client(timeout=30.0)
openai_client  = OpenAI(api_key=env['OPENAI_API_KEY'], http_client=httpx_client)

# Prompt do sistema para o “Thiago-vendedor”
system_prompt = os.getenv('SYSTEM_PROMPT') or (
    "Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza. "
    "Em cada mensagem do cliente, identifique em pensamento os parâmetros: "
    "item, qt, data, bairro, urgente. Se faltar algum, pergunte de modo natural. "
    "Assim que tiver todos, confirme a venda e notifique o grupo. "
    "Para vendas concluídas, na ÚLTIMA linha da resposta, comece com 'GRUPO:' "
    "seguido do resumo que irá para o canal de vendas. Para qualquer outra pergunta, responda normalmente."
)

# ─── FUNÇÕES AUXILIARES ───────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str):
    """
    Envia um texto via Z-API para um número ou grupo.
    """
    url = (
        f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}"
        f"/token/{env['ZAPI_TOKEN']}/send-text"
    )
    headers = {
        'Content-Type':  'application/json',
        'Client-Token':  env['ZAPI_CLIENT_TOKEN'],
    }
    payload = {
        'phone':   phone,
        'message': message,
        'type':    'text'
    }
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

# ─── ROTAS ─────────────────────────────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get('phone')
    text  = (data.get('text') or {}).get('message', '').strip()

    # Ignora eventos sem número, sem texto ou mensagens enviadas por nós
    if not phone or not text or data.get('fromMe', False):
        return jsonify({'status': 'ignored'})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # Monta a conversa para o GPT
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
        logging.error(f"❌ Erro ao chamar GPT: {e}")
        reply = "Desculpe, algo deu errado ao processar sua mensagem."

    # Envia a resposta de volta ao cliente
    send_whatsapp_message(phone, reply)

    # Procura por linha iniciada em 'GRUPO:' e só então repassa ao canal de vendas
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

# ─── ENTRYPOINT ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
