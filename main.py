from flask import Flask, request, jsonify
import os
import requests
import logging
from time import sleep

# ——— Configuração de logging ———
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)

# ——— Injeção do Flask ———
app = Flask(__name__)

# ——— Variáveis de ambiente obrigatórias ———
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")

if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("Variáveis ZAPI_INSTANCE_ID e/ou ZAPI_TOKEN não configuradas!")
    # Nota: Em produção talvez queiramos abortar a inicialização aqui.

# ——— Respostas estáticas / mapeamento de intenções ———
INTENCIONES = {
    "horario":    "⏰ Nosso horário de funcionamento é de seg–sex, 9h–18h.",
    "endereco":   "📍 Estamos na Rua Exemplo, 123, Centro — venha tomar um café!",
    "contato":    "📞 Fale conosco: (XX) XXXX-XXXX ou email contato@exemplo.com",
    "olá":        "Olá! 👋 Como posso ajudar hoje?",
    "default":    "Olá! Recebi sua mensagem e logo retornarei. 😊",
}

def get_resposta_bot(texto: str) -> str:
    texto = texto.lower()
    if any(k in texto for k in ("horário","funcionamento")):
        return INTENCIONES["horario"]
    if any(k in texto for k in ("endereço","localização")):
        return INTENCIONES["endereco"]
    if any(k in texto for k in ("contato","telefone","email")):
        return INTENCIONES["contato"]
    if any(k in texto for k in ("olá","oi","bom dia","boa tarde")):
        return INTENCIONES["olá"]
    return INTENCIONES["default"]

# ——— Função de envio à Z-API ———
def send_whatsapp(phone: str, message: str, retries: int = 2) -> bool:
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}
    for attempt in range(1, retries + 1):
        try:
            logging.info(f"Tentando enviar (tentativa {attempt}) para {phone}…")
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            logging.info(f"Mensagem enviada com sucesso: {resp.text}")
            return True
        except requests.exceptions.RequestException as e:
            logging.warning(f"Falha no envio (tentativa {attempt}): {e}")
            sleep(1)  # back-off simples
    logging.error(f"Não foi possível enviar mensagem para {phone} após {retries} tentativas.")
    return False

# ——— Health-check ———
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp rodando!", 200

# ——— Webhook endpoint ———
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("Payload vazio ou inválido.")
        return jsonify(status="error", detail="JSON inválido"), 400

    logging.debug(f"Payload bruto: {data}")

    # Tenta extrair telefone e texto de várias formas
    phone = None
    text  = None

    # caso tipo “RECEIVED” mais simples
    if data.get("type") == "RECEIVED" and isinstance(data.get("text"), dict):
        phone = data.get("from")
        text  = data["text"].get("message")

    # caso payload com chave "message"
    elif "message" in data and isinstance(data["message"], dict):
        msg = data["message"]
        phone = msg.get("from")
        txt = msg.get("text")
        if isinstance(txt, dict):
            text = txt.get("message")
        elif isinstance(txt, str):
            text = txt

    # caso não reconhecido
    if not phone or not text:
        logging.warning("Payload sem telefone/texto — ignorando.")
        return jsonify(status="ignored"), 200

    logging.info(f"📬 Mensagem de {phone}: {text}")

    # Gera resposta
    resposta = get_resposta_bot(text)
    # Envia
    ok = send_whatsapp(phone, resposta)
    if ok:
        return jsonify(status="message sent"), 200
    else:
        return jsonify(status="error", detail="Falha no envio"), 500

# ——— Error handler genérico ———
@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Erro inesperado:")
    return jsonify(status="error", detail="Erro interno"), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"Iniciando Flask na porta {port}")
    app.run(host="0.0.0.0", port=port)
