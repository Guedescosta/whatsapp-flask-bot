from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando com sucesso!"

@app.route("/", methods=["POST"])
def webhook():
    print("📩 Webhook recebido!")

    try:
        data = request.get_json()
        print("📦 Dados brutos recebidos:", data)

        # Verifica se a chave 'message' existe corretamente
        if not data or "message" not in data or "text" not in data["message"]:
            print("⚠️ Payload inválido (sem 'message')")
            return jsonify({"status": "ignored"}), 200

        message = data["message"]
        phone = message.get("from")
        text = message["text"].get("message")  # Aqui é 'message' dentro de 'text', como confirmado no JSON da Z-API

        print("📞 Telefone:", phone)
        print("✉️ Texto:", text)

        if not phone or not text:
            print("⚠️ Telefone ou texto ausente na mensagem recebida.")
            return jsonify({"status": "no-action"}), 200

        print(f"📬 Mensagem de {phone}: {text}")

        resposta = "Olá! 👋 Recebemos sua mensagem e em breve retornaremos."

        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        payload = {
            "phone": phone,
            "message": resposta
        }
        headers = {
            "Content-Type": "application/json"
        }

        print("📤 Enviando resposta via Z-API...")
        response = requests.post(url, json=payload, headers=headers)
        print("✅ Resposta da Z-API:", response.text)

        return jsonify({"status": "message sent"}), 200

    except Exception as e:
        print("❌ Erro ao processar webhook:", str(e))
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
