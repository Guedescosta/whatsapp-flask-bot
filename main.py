from flask import Flask, request, jsonify
import os
import requests
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Variáveis de ambiente
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

# Respostas básicas automáticas
respostas_rapidas = {
    "horário": "Nosso horário de atendimento é de segunda a sexta, das 9h às 18h.",
    "endereço": "Estamos localizados na Rua Exemplo, 123 - Centro.",
    "contato": "Você pode entrar em contato pelo telefone (XX) XXXX-XXXX.",
    "olá": "Olá! Como posso te ajudar hoje?",
    "padrão": "Olá! 👋 Recebemos sua mensagem e em breve retornaremos. Obrigado!"
}

def interpretar_mensagem(texto):
    if not texto or not isinstance(texto, str):
        return respostas_rapidas["padrão"]
    
    texto = texto.lower()
    if "horário" in texto or "funcionamento" in texto:
        return respostas_rapidas["horário"]
    elif "endereço" in texto or "localização" in texto:
        return respostas_rapidas["endereço"]
    elif "contato" in texto or "telefone" in texto:
        return respostas_rapidas["contato"]
    elif "olá" in texto or "oi" in texto or "bom dia" in texto or "boa tarde" in texto:
        return respostas_rapidas["olá"]
    else:
        return respostas_rapidas["padrão"]

def enviar_resposta(phone, mensagem):
    if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
        logging.error("❌ Variáveis ZAPI não configuradas.")
        return False, "Erro de configuração."

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": mensagem}
    headers = {"Content-Type": "application/json"}

    try:
        resposta = requests.post(url, json=payload, headers=headers, timeout=10)
        resposta.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}. Resposta: {resposta.text}")
        return True, resposta.json()
    except Exception as e:
        logging.error(f"❌ Erro ao enviar mensagem: {e}")
        return False, str(e)

@app.route("/", methods=["GET"])
def status():
    return "✅ Bot do WhatsApp está rodando com sucesso!"

@app.route("/", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido!")
    dados = request.get_json(silent=True)

    if not dados:
        logging.warning("⚠️ Payload vazio ou inválido.")
        return jsonify({"status": "ignored", "detail": "Payload vazio"}), 200

    # Tenta extrair a mensagem corretamente
    try:
        # Situação 1: payload via chave 'message' como a Z-API envia normalmente
        if "message" in dados:
            mensagem = dados["message"]
            telefone = mensagem.get("from")
            texto = None

            if isinstance(mensagem.get("text"), dict):
                texto = mensagem["text"].get("message")
            elif isinstance(mensagem.get("text"), str):
                texto = mensagem["text"]

            logging.info(f"📞 De: {telefone} | 📝 Texto: {texto}")

            if not telefone or not texto:
                logging.warning("⚠️ Telefone ou texto ausente.")
                return jsonify({"status": "no-action"}), 200

            resposta = interpretar_mensagem(texto)
            sucesso, detalhe = enviar_resposta(telefone, resposta)

            if sucesso:
                return jsonify({"status": "sent", "detail": detalhe}), 200
            else:
                return jsonify({"status": "error", "detail": detalhe}), 500

        else:
            logging.warning("⚠️ Estrutura de payload não reconhecida.")
            return jsonify({"status": "ignored", "detail": "Estrutura desconhecida"}), 200

    except Exception as e:
        logging.exception("❌ Erro ao processar webhook")
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
