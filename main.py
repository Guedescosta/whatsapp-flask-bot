from flask import Flask, request, jsonify
import os
import logging
import requests

# --- Configurações iniciais ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
app = Flask(__name__)

# Variáveis de ambiente (definidas no Render)
ZAPI_INSTANCE_ID = os.getenv('ZAPI_INSTANCE_ID')
ZAPI_TOKEN = os.getenv('ZAPI_TOKEN')

# --- Funções auxiliares ---
def clean_and_format_phone(raw_phone: str) -> str | None:
    """
    Remove caracteres não numéricos e formata o telefone para o padrão E.164 (sem '+').
    Retorna None se inválido.
    Ex: '55 (41) 99999-8888' -> '5541999998888'
    """
    if not raw_phone:
        return None
    
    digits = ''.join(filter(str.isdigit, raw_phone))

    # Adicionar lógica para garantir o código do país (DDI), se necessário.
    # Ex: Se o webhook da Z-API enviar apenas DDD+Número (ex: '41999998888'),
    # você precisará adicionar o DDI do Brasil ('55').
    # Adapte esta lógica conforme o DDI do seu país e o formato que o Z-API envia.
    if len(digits) == 10:  # Ex: 4199998888 (DDD + 8 ou 9 dígitos)
        # Assumindo que o DDI seja '55' para o Brasil
        return '55' + digits
    elif len(digits) == 11 and digits.startswith('55'): # Já possui DDI
        return digits
    elif len(digits) == 11 and not digits.startswith('55'): # Ex: 41999998888 (DDD + 9 dígitos)
        # Assumindo que o DDI seja '55' para o Brasil
        return '55' + digits
    elif len(digits) == 12: # Ex: 5541999998888 (DDI + DDD + 9 dígitos)
        return digits
    else:
        # Se o formato não se encaixa nos padrões esperados, pode ser inválido
        logging.warning(f"⚠️ Phone number {raw_phone} resulted in {digits} after cleaning, which is not a standard length.")
        return None


def send_whatsapp_message(phone: str, message: str) -> tuple[bool, str]:
    """
    Envia mensagem de texto via Z-API.
    Retorna (True, resposta_json) ou (False, detalhe_erro).
    """
    if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
        logging.error("Z-API config missing: INSTANCE_ID or TOKEN")
        return False, "Configuration error: Z-API credentials missing."

    # Validação final do telefone antes de enviar
    if not phone:
        logging.error("Attempted to send message with a null or empty phone number.")
        return False, "Validation error: Phone number is null or empty."
    
    url = (
        f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}"
        f"/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {
        "phone": phone,
        "message": message
    }
    headers = {"Content-Type": "application/json"}

    try:
        logging.info(f"📤 Sending to Z-API → URL: {url} | Payload: {payload}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status() # Lança HTTPError para respostas de erro (4xx, 5xx)
        logging.info(f"✅ Z-API response (2xx): {response.text}")
        return True, response.text

    except requests.exceptions.HTTPError as http_err:
        # Captura o erro da Z-API e sua mensagem de erro
        error_detail = response.text if response.text else str(http_err)
        logging.error(f"❌ Z-API HTTPError: {http_err} - Detail: {error_detail}")
        return False, f"HTTPError: {response.text}"
    except requests.exceptions.RequestException as req_err:
        # Erros de conexão, timeout, etc.
        logging.error(f"❌ Z-API RequestException: {req_err}")
        return False, str(req_err)
    except Exception as e:
        # Captura qualquer outra exceção inesperada
        logging.error(f"❌ An unexpected error occurred: {e}")
        return False, f"Unexpected error: {e}"

# --- Rotas Flask ---
@app.route('/', methods=['GET'])
def home():
    """Saúde: confirma que o bot está rodando."""
    return "✅ Bot do WhatsApp rodando!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe webhooks da Z-API e responde automaticamente."""
    data = request.get_json(silent=True)
    logging.info(f"📩 Webhook received raw data: {data}")

    if not data:
        logging.warning("⚠️ Empty or invalid JSON payload received.")
        return jsonify(status="ignored", reason="invalid_json"), 200

    phone = None
    text = None

    # --- Lógica de extração do telefone e texto mais robusta ---
    # Tentativa 1: Formato direto da Z-API para mensagens recebidas (common)
    if 'phone' in data and isinstance(data.get('text'), dict) and 'message' in data['text']:
        raw_phone = str(data.get('phone')) # Garante que é string
        text = data['text'].get('message')
        phone = clean_and_format_phone(raw_phone)
        logging.info(f"💡 Extracted from direct Z-API format. Raw phone: {raw_phone}, Cleaned phone: {phone}")

    # Tentativa 2: Formato aninhado em 'message' (outros tipos de webhook ou variações)
    elif 'message' in data:
        msg = data['message']
        raw_phone_from_msg = msg.get('from') or msg.get('phone')
        if raw_phone_from_msg:
            raw_phone_from_msg = str(raw_phone_from_msg) # Garante que é string
            phone = clean_and_format_phone(raw_phone_from_msg)
            logging.info(f"💡 Extracted from 'message' format. Raw phone: {raw_phone_from_msg}, Cleaned phone: {phone}")

        txt_content = msg.get('text')
        if isinstance(txt_content, dict):
            text = txt_content.get('body') or txt_content.get('message')
        elif isinstance(txt_content, str):
            text = txt_content

    # --- Validação final ---
    if not phone:
        logging.warning("⚠️ Could not extract a valid phone number from webhook. Ignoring message.")
        return jsonify(status="ignored", reason="could_not_extract_phone"), 200
    
    if not text:
        logging.warning(f"⚠️ Could not extract message text for phone {phone}. Ignoring.")
        return jsonify(status="ignored", reason="missing_text"), 200

    logging.info(f"📞 Message from: {phone} | 📝 Content: {text}")

    # Lógica de auto-resposta (simples)
    txt_lower = text.lower()
    if 'horário' in txt_lower or 'funcionamento' in txt_lower:
        reply = 'Nosso horário de atendimento é de segunda a sexta-feira, das 9h às 18h.'
    elif 'endereço' in txt_lower or 'localiza' in txt_lower:
        reply = 'Estamos localizados na Rua Exemplo, 123, Bairro Centro, na cidade de Araucária, Paraná.'
    elif 'contato' in txt_lower or 'telefone' in txt_lower or 'email' in txt_lower:
        reply = 'Você pode nos ligar no telefone (XX) XXXX-XXXX ou enviar um e-mail para contato@exemplo.com.'
    elif any(g in txt_lower for g in ['oi', 'olá', 'bom dia', 'boa tarde', 'boa noite', 'ei']):
        reply = 'Olá! Como posso ajudar você hoje?'
    else:
        reply = 'Olá! 👋 Recebemos sua mensagem e em breve um de nossos atendentes entrará em contato.'

    # Envia resposta
    logging.info(f"💬 Preparing to send reply to {phone}: '{reply}'")
    success, detail = send_whatsapp_message(phone, reply)
    
    if success:
        logging.info(f"✅ Reply sent successfully to {phone}.")
        return jsonify(status="sent"), 200
    else:
        logging.error(f"❌ Failed to send reply to {phone}. Detail: {detail}")
        return jsonify(status="error", detail=detail), 500

if __name__ == '__main__':
    # Define a porta, padrão para 10000 se a variável de ambiente PORT não estiver definida
    port = int(os.getenv('PORT', 10000))
    logging.info(f"🚀 Starting Flask app on host 0.0.0.0, port {port}")
    # Use threaded=True para permitir que o servidor Flask lide com múltiplas requisições (útil para webhooks)
    app.run(host='0.0.0.0', port=port, threaded=True)

