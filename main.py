import os
import logging
import requests
from flask import Flask, request, jsonify
import openai

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN")
GRUPO_AVISOS     = os.getenv("GRUPO_AVISOS")       # ex: "5541997083679"
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# ─── CONTROLE DE LOOP ───────────────────────────────────────────────────────────
ultimos_contatos: dict[str, str] = {}

# ─── FUNÇÕES AUXILIARES ────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str) -> None:
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": message}
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {message}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e} — {getattr(resp, 'text', '')}")

# ─── ROTAS ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    phone = data.get("phone")
    text  = (data.get("text") or {}).get("message")

    if not phone or not text:
        return jsonify({"status": "ignored"})

    # Ignora mensagens enviadas por este bot
    if data.get("fromMe", False):
        return jsonify({"status": "ignored_self"})

    # Normaliza e previne loop por duplicata exata
    chave = text.strip().lower().split("\n")[0]
    if ultimos_contatos.get(phone) == chave:
        logging.info("♻️ Mensagem repetida. Ignorando para evitar loop.")
        return jsonify({"status": "loop_prevented"})
    ultimos_contatos[phone] = chave

    # ─── INTEGRAÇÃO COM GPT ────────────────────────────────────────────────
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
                {"role": "user", "content": text}
            ]
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        reply = "Desculpe, estamos com instabilidade no atendimento. Tente novamente mais tarde."

    # ─── ENVIO DE MENSAGENS ────────────────────────────────────────────────
    # 1) Responde ao cliente
    send_whatsapp_message(phone, reply)
    # 2) Notifica o grupo de avisos
    send_whatsapp_message(
        GRUPO_AVISOS,
        f"📬 Nova mensagem de {phone}\n"
        f"📝: {text}\n"
        f"🤖: {reply}"
    )

    return jsonify({"status": "ok"})

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
