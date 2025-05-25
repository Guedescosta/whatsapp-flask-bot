from flask import Flask, request, jsonify
import os
import requests
import logging
import openai

# === CONFIGURACOES ===
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ADMIN_GROUP = "41997083679"  # grupo ou numero para notificacoes (remetente eh 5541...)

openai.api_key = OPENAI_API_KEY

# === LOGS ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === FLASK ===
app = Flask(__name__)

# === UTILIDADES ===
def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {message}")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Erro ao enviar para {phone}: {e}")

def gerar_resposta_chatgpt(mensagem_usuario):
    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um atendente simpático e natural, focado em ajudar o cliente e fechar vendas."},
                {"role": "user", "content": mensagem_usuario}
            ]
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erro no ChatGPT: {e}")
        return "Desculpe, estou com dificuldades técnicas no momento. Pode repetir mais tarde?"

# === ROTA PRINCIPAL ===
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot online"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    logging.info("\n📩 Webhook recebido")
    logging.info(f"📦 Payload bruto: {data}")

    try:
        phone = data.get("phone")
        text_dict = data.get("text")
        text = text_dict.get("message") if isinstance(text_dict, dict) else None

        if not phone or not text:
            logging.warning("⚠️ Mensagem sem número ou texto válido.")
            return jsonify({"status": "ignored"}), 200

        if phone == ADMIN_GROUP:
            logging.info("🔁 Ignorando resposta ao grupo de notificações para evitar loop.")
            return jsonify({"status": "skipped"}), 200

        logging.info(f"📞 De: {phone} | 📝 Msg: '{text}'")

        resposta = gerar_resposta_chatgpt(text)
        send_whatsapp_message(phone, resposta)

        # Enviar notificação ao grupo com resumo
        aviso = f"📥 Nova mensagem de {phone}\nTexto: {text}\nResposta: {resposta}"
        send_whatsapp_message(ADMIN_GROUP, aviso)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.exception("Erro no webhook")
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
