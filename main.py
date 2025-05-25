import os
import logging
import requests
import openai
from flask import Flask, request, jsonify

# ─── Limpa variáveis de proxy que o openai-python pode puxar automaticamente ───
for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(proxy_var, None)

# ─── Carrega configurações da Z-API e OpenAI ─────────────────────────────────
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID", "")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN", "")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

if not all([ZAPI_INSTANCE_ID, ZAPI_TOKEN, ZAPI_CLIENT_TOKEN, OPENAI_API_KEY]):
    raise RuntimeError(
        "Variáveis de ambiente faltando: verifique ZAPI_INSTANCE_ID, ZAPI_TOKEN, "
        "ZAPI_CLIENT_TOKEN e OPENAI_API_KEY"
    )

openai.api_key = OPENAI_API_KEY

# ─── Configura Flask e logger ────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)

# ─── Controle de loop: armazena última mensagem por contato ─────────────────
ultimos_contatos: dict[str, str] = {}

def clean_phone(raw: str | None) -> str | None:
    """Extrai só dígitos e garante código +55 se faltar."""
    if not raw:
        return None
    digits = "".join(filter(str.isdigit, raw))
    if not digits:
        return None
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits

def send_whatsapp_message(phone: str, text: str) -> bool:
    """Envia texto via Z-API, retorna True se sucesso."""
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    payload = {
        "phone": phone,
        "message": text,
        "type": "text"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
        return True
    except requests.RequestException as e:
        body = getattr(e.response, "text", str(e))
        logging.error(f"❌ Falha ao enviar para {phone}: {e} — {body}")
        return False

@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot WhatsApp rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # extrai número e texto
    raw_phone = data.get("phone") or data.get("message", {}).get("from")
    phone = clean_phone(raw_phone)
    text_field = data.get("text") or data.get("message", {}).get("text")
    msg = ""
    if isinstance(text_field, dict):
        msg = text_field.get("body") or text_field.get("message", "")
    elif isinstance(text_field, str):
        msg = text_field
    msg = msg.strip()

    # filtros iniciais
    if data.get("fromMe", False):
        logging.info("👤 Mensagem própria—ignorada")
        return jsonify({"status": "ignored_self"})
    if not phone:
        logging.warning("⚠️ Telefone inválido—ignorado")
        return jsonify({"status": "ignored_invalid_phone"})
    if not msg:
        logging.warning("⚠️ Mensagem vazia—ignorada")
        return jsonify({"status": "ignored_no_text"})

    # evita loop: compara a primeira linha lowercase
    chave = msg.lower().split("\n", 1)[0]
    if ultimos_contatos.get(phone) == chave:
        logging.info("♻️ Mensagem duplicada—loop prevenido")
        return jsonify({"status": "loop_prevented"})
    ultimos_contatos[phone] = chave

    logging.info(f"📞 De: {phone} | 📝 Msg: {msg}")

    # ─── Gera resposta com GPT ──────────────────────────────────────────────
    try:
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Você é um atendente humano, educado e natural. "
                    "Responda como um vendedor experiente da BG Produtos de Limpeza, "
                    "falando como se fosse o próprio Thiago."
                )},
                {"role": "user", "content": msg}
            ]
        )
        resposta = completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # ─── Envia resposta ao cliente ──────────────────────────────────────────
    send_whatsapp_message(phone, resposta)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
