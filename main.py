from flask import Flask, request, jsonify
import os
import requests
import logging
from time import sleep

# ——— Logging básico ———
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s"
)

app = Flask(__name__)

# ——— Variáveis de ambiente ———
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")

if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("ZAPI_INSTANCE_ID ou ZAPI_TOKEN não configurados!")
    # opcionalmente abortar aqui

# ——— Respostas simples ———
INTENCIONES = {
    "horario":  "⏰ Nosso horário é seg–sex, 9h–18h.",
    "endereco": "📍 Rua Exemplo, 123, Centro.",
    "contato":  "📞 (XX) XXXX-XXXX ou email@exemplo.com",
    "saudacao": "Olá! 👋 Como posso ajudar?",
    "padrao":   "Recebi sua mensagem e logo retornarei. 😊"
}

def get_resposta_bot(texto: str) -> str:
    t = texto.lower()
    if "horário" in t or "funcionamento" in t:
        return INTENCIONES["horario"]
    if "endereço" in t or "localização" in t:
        return INTENCIONES["endereco"]
    if "contato" in t or "telefone" in t or "email" in t:
        return INTENCIONES["contato"]
    if any(s in t for s in ("olá","oi","bom dia","boa tarde")):
        return INTENCIONES["saudacao"]
    return INTENCIONES["padrao"]

# ——— Envio com retry ———
def send_whatsapp(phone: str, message: str, retries: int = 2) -> bool:
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}

    for i in range(1, retries+1):
        try:
            logging.info(f"[{i}] Enviando para {phone} via Z-API…")
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            logging.info(f"✅ Enviado: {resp.text}")
            return True
        except Exception as e:
            logging.warning(f"Falha no envio (tentativa {i}): {e}")
            sleep(1)
    logging.error(f"❌ Não foi possível enviar para {phone}")
    return False

# ——— Rota de saúde ———
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot rodando!", 200

# ——— Webhook da Z-API ———
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("📩 Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("Payload JSON inválido ou vazio")
        return jsonify(status="error", detail="JSON inválido"), 400

    logging.debug(f"Payload: {data}")

    phone = None
    text  = None

    # caso padrão: data["message"]["text"]["body"]
    if isinstance(data.get("message"), dict):
        msg = data["message"]
        phone = msg.get("from")
        tfield = msg.get("text", {})
        if isinstance(tfield, dict):
            text = tfield.get("body") or tfield.get("message")

    # fallback: top-level type RECEIVED
    if not phone and data.get("type") == "RECEIVED":
        phone = data.get("from")
        tfield = data.get("text", {})
        if isinstance(tfield, dict):
            text = tfield.get("body") or tfield.get("message")

    if not phone or not text:
        logging.warning("Payload sem telefone/texto — ignorando")
        return jsonify(status="ignored"), 200

    logging.info(f"📬 Mensagem de {phone}: {text}")

    # gera resposta e envia
    resposta = get_resposta_bot(text)
    sucesso  = send_whatsapp(phone, resposta)
    if sucesso:
        return jsonify(status="message sent"), 200
    else:
        return jsonify(status="error", detail="falha no envio"), 500

# ——— Tratamento geral de erros ———
@app.errorhandler(Exception)
def on_error(e):
    logging.exception("Erro inesperado")
    return jsonify(status="error", detail="erro interno"), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logging.info(f"Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
