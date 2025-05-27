from flask import Flask, request, jsonify
import os
import logging
import requests
import httpx
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")      # sua instance_id da Z-API
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")            # seu token da Z-API
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")     # Client-Token da Z-API
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")        # sua chave da OpenAI

# cliente OpenAI sem proxies para evitar erro 'unexpected argument proxies'
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client()
)

# armazena última mensagem de cada contato para prevenir loops
ultimos_contatos = {}

# ─── ENVIO PELO Z-API ───────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, text: str):
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
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e} — {getattr(resp, 'text', '')}")

# ─── ROTAS ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    phone = data.get("phone")
    msg   = data.get("text", {}).get("message")
    if not phone or not msg:
        return jsonify({"status": "ignored"})

    # ignora mensagens enviadas por nós mesmos
    if data.get("fromMe", False):
        logging.info("👤 Mensagem própria—ignorada")
        return jsonify({"status": "ignored_self"})

    # filtra texto puro e previne loop de eco
    msg_pura = msg.strip().lower().split("\n")[0]
    if ultimos_contatos.get(phone) == msg_pura:
        logging.info("♻️ Mensagem repetida—loop evitado")
        return jsonify({"status": "loop_prevented"})
    ultimos_contatos[phone] = msg_pura

    # catálogo para prompt
    catalogo = (
        "Catálogo de produtos (5L): "
        "Lava roupas R$35, Amaciante R$35, Desinfetante R$30, Água sanitária R$25, "
        "Alvejante sem cloro R$30, Detergente R$30, Álcool perfumado R$40, Passa-fácil/Branquinho R$40; "
        "Kit 5 produtos R$145; "
        "Embalagens 1L: Álcool e Branquinho conforme preço de 5L proporcional."
    )

    # chamada ao GPT
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um atendente humano da BG Produtos de Limpeza. "
                        "Fale como o Thiago, seja direto e simpático. "
                        f"{catalogo}"
                    )
                },
                {"role": "user", "content": msg}
            ]
        )
        resposta = completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # envia resposta ao cliente
    send_whatsapp_message(phone, resposta)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    )
