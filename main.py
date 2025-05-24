from flask import Flask, request, jsonify
import os
import requests
import logging

# ————— Configuração de logging —————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = Flask(__name__)

# ————— Variáveis de ambiente —————
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.environ.get("ZAPI_TOKEN")

if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    logging.critical("⚠️ Variáveis ZAPI_INSTANCE_ID ou ZAPI_TOKEN ausentes!")
    raise RuntimeError("Falta configurar ZAPI_INSTANCE_ID ou ZAPI_TOKEN")

# ————— Função de envio —————
def send_text(phone: str, message: str):
    url = (
        f"https://api.z-api.io/instances/"
        f"{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {"phone": phone, "message": message}
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API respondeu: {resp.text}")
        return True, resp.json()
    except requests.HTTPError as e:
        logging.error(f"❌ HTTPError: {e} — {resp.text}")
        return False, resp.text
    except Exception as e:
        logging.error(f"❌ Erro no envio: {e}")
        return False, str(e)

# ————— Rota GET (health check) —————
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp rodando!"

# ————— Rota POST (webhook) —————
@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("⚠️ Payload inválido ou vazio")
        return jsonify({"status": "ignored"}), 200

    logging.info(f"📦 Payload bruto: {data}")

    # Extrai telefone e texto de forma genérica
    phone = None
    text  = None

    # Caso tipo RECEIVEDCallback (vindo direto do Z-API)
    if data.get("type") == "ReceivedCallback" and isinstance(data.get("text"), dict):
        phone = data.get("phone")
        text  = data["text"].get("message")

    # Caso aninhado dentro de data["message"]
    elif isinstance(data.get("message"), dict):
        msg = data["message"]
        phone = msg.get("from") or msg.get("phone")
        txt_field = msg.get("text")
        if isinstance(txt_field, dict):
            text = txt_field.get("message")
        elif isinstance(txt_field, str):
            text = txt_field

    # Se falhar, ignora
    if not phone or not text:
        logging.warning("⚠️ Sem telefone ou texto — ignorando")
        return jsonify({"status": "ignored"}), 200

    logging.info(f"📞 De: {phone}  |  📝 Msg: “{text}”")

    # Resposta padrão (aqui você pode chamar funções de NLU ou mapeamentos)
    resposta = "Olá! Recebemos sua mensagem e logo retornaremos. 😊"

    # Envia de volta
    ok, detail = send_text(phone, resposta)
    if ok:
        return jsonify({"status": "message sent"}), 200
    else:
        return jsonify({"status": "error", "detail": detail}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Iniciando na porta {port}")
    app.run(host="0.0.0.0", port=port)
