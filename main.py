import os
import logging
import requests
from flask import Flask, request, jsonify
import openai

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO ────────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")  # ex: "3DFAED34CAF760CDDF170A1EFCACDE10"
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")        # ex: "97DAA07311ACEFFA36DF23AF"
GRUPO_AVISOS     = os.getenv("GRUPO_AVISOS")      # ex: "5541997083679"
openai.api_key   = os.getenv("OPENAI_API_KEY")    # carregado automaticamente pelo SDK

# ─── VARIÁVEL DE CONTROLE DE LOOP ─────────────────────────────────────────────
ultimos_contatos: dict[str, str] = {}

# ─── FUNÇÃO DE ENVIO VIA Z-API ────────────────────────────────────────────────
def send_whatsapp_message(phone: str, text: str) -> None:
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": text}
    resp = requests.post(url, json=payload, timeout=10)
    try:
        resp.raise_for_status()
        logging.info(f"✅ Enviado para {phone}: {resp.text}")
    except requests.HTTPError as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e} — {resp.text}")

# ─── ROTAS ───────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    phone = data.get("phone")
    msg   = data.get("text", {}).get("message")

    # validação básica
    if not phone or not msg or data.get("fromMe", False):
        return jsonify({"status": "ignored"}), 200

    # normaliza e previne loop
    chave = msg.strip().lower().split("\n")[0]
    if ultimos_contatos.get(phone) == chave:
        logging.info("♻️ Loop detectado, mensagem ignorada")
        return jsonify({"status": "loop_prevented"}), 200
    ultimos_contatos[phone] = chave

    # ─── CHAMADA AO GPT ───────────────────────────────────────────────────────
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                  "role": "system",
                  "content": (
                    "Você é um atendente humano, educado e natural. "
                    "Responda como um vendedor experiente da BG Produtos de Limpeza, "
                    "falando como se fosse o próprio Thiago."
                  )
                },
                {"role": "user", "content": msg}
            ]
        )
        resposta = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        resposta = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # ─── ENVIO AO CLIENTE E AO GRUPO ───────────────────────────────────────────
    send_whatsapp_message(phone, resposta)
    send_whatsapp_message(
        GRUPO_AVISOS,
        f"📬 Nova mensagem de {phone}\n📝: {msg}\n🤖: {resposta}"
    )

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    # em produção você roda via gunicorn, então o debug pode ficar False
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
