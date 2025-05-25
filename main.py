import os
import logging
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─── CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE ────────────────────────
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID", "<sua_instance_id>")
ZAPI_TOKEN       = os.getenv("ZAPI_TOKEN",       "<seu_zapi_token>")
GRUPO_AVISOS     = os.getenv("GRUPO_AVISOS",     "<telefone_do_grupo>")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY",   "<sua_openai_api_key>")

# cliente OpenAI (versão >=1.0.0)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# para evitar loop de respostas repetidas
ultimos_contatos: dict[str,str] = {}

def send_whatsapp_message(phone: str, text: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {"phone": phone, "message": text}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Enviado para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Erro ao enviar para {phone}: {e}")

@app.route("/", methods=["GET"])
def home():
    return "Bot do WhatsApp está rodando!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # extrai telefone e mensagem
    phone = data.get("phone")
    text  = None
    if isinstance(data.get("text"), dict):
        text = data["text"].get("message")
    elif isinstance(data.get("message"), dict):
        text = data["message"].get("body") or data["message"].get("message")

    if not phone or not text:
        return jsonify({"status":"ignored"}), 200

    # ignora tudo que vier de você mesmo
    if data.get("fromMe", False):
        logging.info("👤 Mensagem de mim ignorada")
        return jsonify({"status":"ignored_self"}), 200

    # bloqueio de loop: só a primeira linha em lowercase
    text_pura = text.strip().lower().split("\n")[0]
    if ultimos_contatos.get(phone) == text_pura:
        logging.info("♻️ Loop detectado, ignorando")
        return jsonify({"status":"loop_prevented"}), 200

    ultimos_contatos[phone] = text_pura

    # ─── CHAMADA AO GPT ─────────────────────────────────────────────
    try:
        resp = openai_client.chat.completions.create(
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

    # envia resposta pro cliente
    send_whatsapp_message(phone, reply)

    # notifica no grupo de avisos
    aviso = f"📬 Nova mensagem de {phone}\n📝: {text}\n🤖: {reply}"
    send_whatsapp_message(GRUPO_AVISOS, aviso)

    return jsonify({"status":"ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
