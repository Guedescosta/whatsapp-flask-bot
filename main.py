from flask import Flask, request, jsonify
import os
import logging
import requests

# ─── Configuração de logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ─── Instância Flask ───────────────────────────────────────────────────────
app = Flask(__name__)

# ─── Variáveis de ambiente ─────────────────────────────────────────────────
ZAPI_INSTANCE_ID   = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN         = os.environ.get("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN  = os.environ.get("ZAPI_CLIENT_TOKEN")

if not all([ZAPI_INSTANCE_ID, ZAPI_TOKEN, ZAPI_CLIENT_TOKEN]):
    logging.error("❌ Faltam variáveis de ambiente Z-API (INSTANCE_ID, TOKEN ou CLIENT_TOKEN).")

# ─── Funções auxiliares ────────────────────────────────────────────────────
def clean_phone(raw: str) -> str | None:
    """Remove tudo que não for dígito e garante código de país Brasil (55)."""
    if not raw:
        return None
    digits = "".join(filter(str.isdigit, raw))
    # força prefixo brasileiro se faltar
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits if digits else None

def send_whatsapp_message(phone: str, message: str) -> tuple[bool, dict | str]:
    """Envia mensagem via Z-API, incluindo Client-Token no header."""
    url = (
        f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}"
        f"/token/{ZAPI_TOKEN}/send-text"
    )
    payload = {
        "phone": phone,
        "message": message
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }

    logging.info(f"📤 POST→{url} payload={payload}")
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API respondeu: {resp.text}")
        return True, resp.json()
    except requests.exceptions.HTTPError as e:
        logging.error(f"❌ Z-API HTTPError: {e} — {resp.text}")
        return False, resp.text
    except Exception as e:
        logging.error(f"❌ Erro na requisição Z-API: {e}")
        return False, str(e)

def get_resposta_bot(text: str) -> str:
    """Gera resposta simples baseada em palavras-chave."""
    t = text.lower()
    if any(k in t for k in ("horário", "funcionamento")):
        return "Nosso horário de funcionamento é de seg-sex das 9h às 18h."
    if any(k in t for k in ("endereço", "localização")):
        return "Nosso endereço: Rua Exemplo, 123, Centro."
    if any(k in t for k in ("contato", "telefone", "email")):
        return "📞 (XX) XXXX-XXXX  ✉️ contato@exemplo.com"
    if any(k in t for k in ("oi", "olá", "bom dia", "boa tarde")):
        return "Olá! 👋 Como posso ajudar?"
    return "Olá! Recebemos sua mensagem e logo retornaremos. 😊"

# ─── Rotas ─────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp rodando!"

@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("✉️ Webhook recebido")
    data = request.get_json(silent=True)
    if not data:
        logging.warning("⚠️ Payload JSON inválido ou vazio")
        return jsonify({"status": "ignored", "detail": "invalid JSON"}), 400

    logging.info(f"📦 Payload bruto: {data}")

    # Extrai texto e número
    phone_raw = data.get("phone") or data.get("message", {}).get("from")
    text_field = data.get("text") or data.get("message", {}).get("text")

    phone = clean_phone(phone_raw)
    text = None
    if isinstance(text_field, dict):
        # Z-API usa chave "message" para texto
        text = text_field.get("message") or text_field.get("body")
    elif isinstance(text_field, str):
        text = text_field

    if not phone or not text:
        logging.warning(f"⚠️ Ignorando: phone={phone!r}, text={text!r}")
        return jsonify({"status": "ignored", "reason": "missing phone or text"}), 200

    logging.info(f"📞 From: {phone} | 📝 Msg: “{text}”")

    # Gera e envia resposta
    resposta = get_resposta_bot(text)
    ok, detail = send_whatsapp_message(phone, resposta)
    if ok:
        return jsonify({"status": "sent", "detail": detail}), 200
    else:
        return jsonify({"status": "error", "detail": detail}), 500

# ─── Execução ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Iniciando app na porta {port}")
    app.run(host="0.0.0.0", port=port)
