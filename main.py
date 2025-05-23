from flask import Flask, request, jsonify
import os
import requests
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Variáveis de ambiente para Z-API
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

# --- Funções Auxiliares ---

# Mapeamento simples de intenções para respostas
respostas_pre_definidas = {
    "horario": "Nosso horário de funcionamento é de segunda a sexta, das 9h às 18h.",
    "endereco": "Estamos localizados na Rua Exemplo, 123, Centro. 📍",
    "contato": "Você pode nos ligar no (XX) XXXX-XXXX ou enviar um email para contato@exemplo.com.",
    "ola": "Olá! Como posso ajudar você hoje?",
    "padrao": "Olá! 👋 Recebemos sua mensagem e em breve retornaremos. Se precisar de ajuda imediata, por favor, ligue para (XX) XXXX-XXXX."
}

def get_resposta_bot(mensagem_usuario):
    """
    Função para gerar respostas dinâmicas baseadas na mensagem do usuário.
    Pode ser expandida com NLU mais avançado.
    """
    if not isinstance(mensagem_usuario, str):
        logging.warning(f"Mensagem de usuário não é string: {mensagem_usuario}")
        return respostas_pre_definidas["padrao"]

    mensagem_usuario_lower = mensagem_usuario.lower()

    if "horário" in mensagem_usuario_lower or "funcionamento" in mensagem_usuario_lower:
        return respostas_pre_definidas["horario"]
    elif "endereço" in mensagem_usuario_lower or "localização" in mensagem_usuario_lower:
        return respostas_pre_definidas["endereco"]
    elif "contato" in mensagem_usuario_lower or "telefone" in mensagem_usuario_lower or "email" in mensagem_usuario_lower:
        return respostas_pre_definidas["contato"]
    elif "olá" in mensagem_usuario_lower or "oi" in mensagem_usuario_lower or "bom dia" in mensagem_usuario_lower or "boa tarde" in mensagem_usuario_lower:
        return respostas_pre_definidas["ola"]
    else:
        return respostas_pre_definidas["padrao"]

def send_whatsapp_message(phone, message):
    """
    Função para enviar uma mensagem de texto via Z-API.
    """
    if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
        logging.error("Variáveis de ambiente ZAPI_INSTANCE_ID ou ZAPI_TOKEN não configuradas.")
        return False, "Erro de configuração da Z-API."

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": message
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        logging.info(f"📤 Tentando enviar mensagem para {phone} via Z-API...")
        response = requests.post(url, json=payload, headers=headers, timeout=10) # Adicionado timeout
        response.raise_for_status() # Lança um HTTPError para respostas de erro (4xx ou 5xx)
        logging.info(f"✅ Resposta da Z-API para {phone}: {response.text}")
        return True, response.json()
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"❌ Erro HTTP ao enviar mensagem para {phone}: {http_err} - {response.text}")
        return False, f"Erro HTTP: {http_err}. Detalhe: {response.text}"
    except requests.exceptions.ConnectionError as conn_err:
        logging.error(f"❌ Erro de conexão ao enviar mensagem para {phone}: {conn_err}")
        return False, f"Erro de conexão: {conn_err}"
    except requests.exceptions.Timeout as timeout_err:
        logging.error(f"❌ Timeout ao enviar mensagem para {phone}: {timeout_err}")
        return False, f"Timeout na requisição: {timeout_err}"
    except requests.exceptions.RequestException as req_err:
        logging.error(f"❌ Erro inesperado ao enviar mensagem para {phone}: {req_err}")
        return False, f"Erro na requisição Z-API: {req_err}"
    except Exception as e:
        logging.error(f"❌ Erro genérico ao enviar mensagem para {phone}: {e}")
        return False, f"Erro interno ao enviar mensagem: {e}"

# --- Rotas da Aplicação Flask ---

@app.route("/", methods=["GET"])
def home():
    """
    Rota de saúde/verificação simples.
    """
    logging.info("GET / - Rota home acessada.")
    return "✅ Bot do WhatsApp está rodando com sucesso!"

@app.route("/", methods=["POST"])
def webhook():
    """
    Rota principal para receber webhooks da Z-API.
    """
    logging.info("📩 Webhook recebido!")
    data = request.get_json(silent=True) # silent=True para não quebrar em JSON inválido

    if data is None:
        logging.warning("⚠️ Payload JSON inválido ou vazio.")
        return jsonify({"status": "error", "detail": "Payload JSON inválido ou vazio."}), 400

    logging.info(f"📦 Dados brutos recebidos: {data}")

    phone = None
    text = None

    try:
        # Lógica de parsing mais robusta para diferentes estruturas de webhook da Z-API
        # 1. Caso de mensagem de texto de entrada (tipo "RECEIVED")
        if data.get("type") == "RECEIVED" and "text" in data and isinstance(data["text"], dict) and "message" in data["text"]:
            phone = data.get("from")
            text = data["text"]["message"]
            logging.info(f"DEBUG: Payload tipo 'RECEIVED' processado. Telefone: {phone}, Texto: {text}")

        # 2. Caso de payload que contém a mensagem principal aninhada (ex: webhook de 'message' puro)
        elif "message" in data:
            message_content = data["message"]
            phone = message_content.get("from")
            text_field = message_content.get("text") # Pode ser dict ou string

            if isinstance(text_field, dict):
                text = text_field.get("message")
            elif isinstance(text_field, str):
                text = text_field
            logging.info(f"DEBUG: Payload com chave 'message' processado. Telefone: {phone}, Texto: {text}")

        # 3. Caso de payload que não se encaixa nos padrões esperados (ex: status, delivery)
        else:
            logging.info(f"⚠️ Payload não contém dados de mensagem de texto esperados. Tipo detectado: {data.get('type')}.")
            # Se for um status de entrega ou outro evento que não exige resposta, pode ignorar.
            # Aqui, estamos assumindo que só queremos responder a mensagens de texto.
            return jsonify({"status": "ignored", "reason": "Payload sem mensagem de texto esperada"}), 200

        # Verificação final se phone e text foram extraídos com sucesso
        if not phone or not text:
            logging.warning("⚠️ Telefone ou texto ausente na mensagem recebida após parsing.")
            return jsonify({"status": "no-action", "reason": "Telefone ou texto ausente"}), 200

        logging.info(f"📬 Mensagem de {phone}: {text}")

        # Gerar a resposta do bot
        resposta = get_resposta_bot(text)

        # Enviar a resposta via Z-API
        success, response_detail = send_whatsapp_message(phone, resposta)

        if success:
            return jsonify({"status": "message sent", "zapi_response": response_detail}), 200
        else:
            logging.error(f"❌ Falha ao enviar mensagem para {phone}: {response_detail}")
            return jsonify({"status": "error", "detail": f"Falha ao enviar mensagem: {response_detail}"}), 500

    except Exception as e:
        logging.exception("❌ Erro inesperado ao processar webhook.") # logging.exception loga o traceback completo
        # Tenta enviar uma mensagem de erro para o usuário se possível
        if phone:
            send_whatsapp_message(phone, "Desculpe, ocorreu um erro interno e não consegui processar sua solicitação. Por favor, tente novamente mais tarde.")
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    # Define a porta, usando a variável de ambiente PORT ou 10000 como padrão
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Iniciando a aplicação Flask na porta {port}")
    app.run(host="0.0.0.0", port=port)

