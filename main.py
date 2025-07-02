import os
import json
import logging
import requests
import httpx
from flask import Flask, request, jsonify
from openai import OpenAI

# ─── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Carrega variáveis de ambiente Z-API / OpenAI
env = {
    'ZAPI_INSTANCE_ID':  os.getenv('ZAPI_INSTANCE_ID'),
    'ZAPI_TOKEN':        os.getenv('ZAPI_TOKEN'),
    'ZAPI_CLIENT_TOKEN': os.getenv('ZAPI_CLIENT_TOKEN'),
    'OPENAI_API_KEY':    os.getenv('OPENAI_API_KEY'),
    'ZAPI_GROUP_ID':     os.getenv('ZAPI_GROUP_ID'),
}

# Inicializa cliente OpenAI
httpx_client   = httpx.Client()
openai_client = OpenAI(api_key=env['OPENAI_API_KEY'], http_client=httpx_client)

# ─── PROMPT DINÂMICO ────────────────────────────────────────────────────────────

PROMPT_FILE = "system_prompt.txt"
MEM_FILE    = "memoria.json"

def load_prompt():
    try:
        return open(PROMPT_FILE, "r", encoding="utf-8").read()
    except FileNotFoundError:
        # se não existir, já cria com um prompt inicial
        prompt = (
            "Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza. "
            "Converse de forma natural, calorosa e descontraída, use emojis leves 😊. "
            "Identifique mentalmente o que falta pra fechar a venda (produto, quantidade, data, bairro, urgência). "
            "Pergunte suavemente o que faltar (“Só pra confirmar, qual data você quer?”). "
            "Quando tudo estiver pronto, comemore: “Show! Já reservei pra você! 🎉” "
            "e ao final da sua mensagem inclua uma linha começando com “GRUPO:” e um resumo curto da venda. "
            "Para qualquer outro assunto (até teorema), responda normalmente."
        )
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(prompt)
        return prompt

def save_prompt(novo):
    with open(PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(novo)

system_prompt = load_prompt()

def load_memoria():
    try:
        return json.load(open(MEM_FILE, "r", encoding="utf-8"))
    except:
        return {}

def save_memoria(mem):
    json.dump(mem, open(MEM_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ─── AUXILIARES Z-API ──────────────────────────────────────────────────────────

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
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar pra {phone}: {e}")

# ─── WEBHOOK ────────────────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get('phone')
    text  = (data.get('text') or {}).get('message', '').strip()
    is_group = data.get('isGroup', False)

    # ignora tuíte vazio, mensagem do próprio bot, etc.
    if not phone or not text or data.get('fromMe', False):
        return jsonify({'status': 'ignored'})

    logging.info("✉️ Webhook recebido:")
    logging.info(text)

    # ─── Atualização de prompt via grupo ─────────────────────────────
    if is_group and text.startswith("/atualiza_prompt "):
        novo = text[len("/atualiza_prompt "):].strip()
        save_prompt(novo)
        global system_prompt
        system_prompt = novo
        send_whatsapp_message(phone, "✅ Prompt atualizado com sucesso!")
        return jsonify({'status':'prompt_updated'})

    # ─── Chama o GPT ───────────────────────────────────────────────────
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user',   'content': text}
    ]
    try:
        resp  = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erro GPT: {e}")
        reply = "Desculpe, algo deu errado. 😢"

    # ─── Envia ao cliente ───────────────────────────────────────────────
    send_whatsapp_message(phone, reply)

    # ─── Se houver linha ‘GRUPO:’, dispara só ela ao grupo ────────────
    grp_id = env.get('ZAPI_GROUP_ID')
    if grp_id:
        for line in reply.splitlines():
            if line.strip().startswith("GRUPO:"):
                resumo = line.split("GRUPO:",1)[1].strip()
                send_whatsapp_message(grp_id, resumo)
                break

    # ─── Salva memória de conversa ────────────────────────────────────
    mem = load_memoria()
    mem.setdefault(phone, []).append({'in': text, 'out': reply})
    save_memoria(mem)

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def home():
    return "Bot está ativo! 🚀", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)))
