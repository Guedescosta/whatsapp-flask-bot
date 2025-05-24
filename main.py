from flask import Flask, request, jsonify import os import logging import requests

--- Configurações iniciais ---

logging.basicConfig( level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s' ) app = Flask(name)

Variáveis de ambiente (definidas no Render)

ZAPI_INSTANCE_ID = os.getenv('ZAPI_INSTANCE_ID') ZAPI_TOKEN = os.getenv('ZAPI_TOKEN')

--- Funções auxiliares ---

def clean_phone(raw_phone: str) -> str | None: """ Remove caracteres não numéricos e retorna None se inválido. """ if not raw_phone: return None digits = ''.join(filter(str.isdigit, raw_phone)) return digits if digits else None

def send_whatsapp_message(phone: str, message: str) -> tuple[bool, str]: """ Envia mensagem de texto via Z-API. Retorna (True, resposta_json) ou (False, detalhe_erro). """ if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN: logging.error("Z-API config missing: INSTANCE_ID or TOKEN") return False, "Configuration error"

url = (
    f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}"
    f"/token/{ZAPI_TOKEN}/send-text"
)
payload = {
    "phone": phone,
    "message": message
    # Se a API exigir, descomente: "type": "text"
}
headers = {"Content-Type": "application/json"}

try:
    logging.info(f"📤 Sending → {url} payload={payload}")
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    logging.info(f"✅ Z-API response: {response.text}")
    return True, response.text

except requests.exceptions.HTTPError as http_err:
    logging.error(f"❌ Z-API HTTPError: {http_err} - {response.text}")
    return False, f"HTTPError: {response.text}"
except requests.exceptions.RequestException as req_err:
    logging.error(f"❌ Z-API RequestException: {req_err}")
    return False, str(req_err)

--- Rotas Flask ---

@app.route('/', methods=['GET']) def home(): """Saúde: confirma que o bot está rodando.""" return "✅ Bot do WhatsApp rodando!"

@app.route('/webhook', methods=['POST']) def webhook(): """Recebe webhooks da Z-API e responde automaticamente.""" data = request.get_json(silent=True) logging.info(f"📩 Webhook received: {data}")

if not data:
    logging.warning("⚠️ Empty or invalid JSON payload")
    return jsonify(status="ignored", reason="invalid_json"), 200

# Extrai telefone e texto, suportando diferentes formatos de payload
phone = None
text = None

# Caso da Z-API: payload tipo ReceivedCallback ou RECEIVED
if data.get('phone') and isinstance(data.get('text'), dict):
    phone = clean_phone(data.get('phone'))
    text = data['text'].get('message')

# Fallback: payload aninhado em data['message']
elif 'message' in data:
    msg = data['message']
    phone = clean_phone(msg.get('from') or msg.get('phone'))
    txt = msg.get('text')
    if isinstance(txt, dict):
        text = txt.get('body') or txt.get('message')
    elif isinstance(txt, str):
        text = txt

if not phone or not text:
    logging.warning("⚠️ Missing phone or text, ignoring")
    return jsonify(status="ignored", reason="missing_phone_or_text"), 200

logging.info(f"📞 From: {phone} | 📝 Msg: {text}")

# Lógica de auto-resposta (simples)
txt_lower = text.lower()
if 'horário' in txt_lower or 'funcionamento' in txt_lower:
    reply = 'Nosso horário: seg-sex, 9h-18h.'
elif 'endereço' in txt_lower or 'localiza' in txt_lower:
    reply = 'Estamos na Rua Exemplo, 123, Centro.'
elif 'contato' in txt_lower or 'telefone' in txt_lower or 'email' in txt_lower:
    reply = 'Ligue (XX) XXXX-XXXX ou envie email para contato@exemplo.com.'
elif any(g in txt_lower for g in ['oi', 'olá', 'bom dia', 'boa tarde']):
    reply = 'Olá! Como posso ajudar hoje?'
else:
    reply = 'Olá! 👋 Recebemos sua mensagem e em breve retornaremos.'

# Envia resposta
success, detail = send_whatsapp_message(phone, reply)
if success:
    return jsonify(status="sent"), 200
else:
    logging.error(f"❌

