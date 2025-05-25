import os
import logging
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

# ─── Remove quaisquer proxies herdados do ambiente ────────────────────────
for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(var, None)

# ─── Configurações de ambiente ────────────────────────────────────────────
ZAPI_INSTANCE_ID   = os.getenv("ZAPI_INSTANCE_ID", "")
ZAPI_TOKEN         = os.getenv("ZAPI_TOKEN", "")
ZAPI_CLIENT_TOKEN  = os.getenv("ZAPI_CLIENT_TOKEN", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
GRUPO_AVISOS       = os.getenv("GRUPO_AVISOS", "")  # ex: "5541997083679"

if not all([ZAPI_INSTANCE_ID, ZAPI_TOKEN, ZAPI_CLIENT_TOKEN, OPENAI_API_KEY, GRUPO_AVISOS]):
    raise RuntimeError("Faltam variáveis de ambiente: verifique ZAPI_INSTANCE_ID, ZAPI_TOKEN, ZAPI_CLIENT_TOKEN, OPENAI_API_KEY e GRUPO_AVISOS")

# ─── Inicializa Flask e Logger ───────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)

# ─── Instancia o cliente OpenAI ──────────────────────────────────────────
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ─── Controle de loop de resposta ────────────────────────────────────────
ultimos_contatos: dict[str, str] = {}

def clean_phone(raw: str) -> str | None:
    """Remove tudo que não for dígito e retorna None se ficar vazio."""
    digits = "".join(filter(str.isdigit, raw or ""))
    if not digits:
        return None
    # garante código do Brasil se faltar (opcional)
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits

def send_whatsapp_message(phone: str, text: str) -> bool:
    """Envia texto via Z-API, retorna True se sucesso."""
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": phone,
        "message": text,
        "type": "text"
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Z-API enviado para {phone}: {resp.text}")
        return True
    except requests.exceptions.RequestException as e:
        txt = getattr(e.response, "text", str(e))
        logging.error(f"❌ Falha ao enviar para {phone}: {e} — {txt}")
        return False

@app.route("/", methods=["GET"])
def home():
    return "🤖 Bot WhatsApp rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # extrai telefone e mensagem
    raw_phone = data.get("phone") or data.get("message", {}).get("from")
    phone = clean_phone(raw_phone)
    msg = None
    text_field = data.get("text") or data.get("message", {}).get("text")
    if isinstance(text_field, dict):
        msg = text_field.get("body") or text_field.get("message")
    elif isinstance(text_field, str):
        msg = text_field
    msg = (msg or "").strip()

    # validações iniciais
    if data.get("fromMe", False):
        logging.info("👤 Mensagem própria. Ignorada.")
        return jsonify({"status": "ignored_self"})
    if not phone:
        logging.warning("⚠️ Telefone inválido. Ignorando.")
        return jsonify({"status": "ignored_invalid_phone"})
    if not msg:
        logging.warning("⚠️ Mensagem vazia. Ignorando.")
        return jsonify({"status": "ignored_no_text"})

    # evita loop: compara primeira linha lowercase
    chave = msg.lower().split("\n", 1)[0]
    if ultimos_contatos.get(phone) == chave:
        logging.info("♻️ Mensagem duplicada. Loop prevenido.")
        return jsonify({"status": "loop_prevented"})
    ultimos_contatos[phone] = chave

    logging.info(f"📞 De: {phone} | 📝 Msg: {msg}")

    # ─── Gera resposta com GPT ────────────────────────────────────────────
    try:
        resp = openai_client.chat.completions.create(
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
        resposta = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # ─── Envia ao cliente e ao grupo de avisos ───────────────────────────
    send_whatsapp_message(phone, resposta)
    send_whatsapp_message(
        GRUPO_AVISOS,
        f"📬 Nova mensagem de {phone}\n📝: {msg}\n🤖: {resposta}"
    )

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # escuta na porta padrão 5000 com debug desativado em produção
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
