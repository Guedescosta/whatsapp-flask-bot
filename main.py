from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

# Variáveis de ambiente
ZAPI_INSTANCE_ID = os.environ.get("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.environ.get("ZAPI_TOKEN")

# Verificação inicial
if not ZAPI_INSTANCE_ID or not ZAPI_TOKEN:
    raise EnvironmentError("⚠️ As variáveis ZAPI_INSTANCE_ID ou ZAPI_TOKEN não estão definidas.")

# Rota de teste (GET)
@app.route("/", methods=["GET"])
def home():
    return "✅ Bot do WhatsApp está rodando com sucesso!"

# Rota de recebimento do webhook (POST)
@app.route("/", methods=["POST"])
def webhook():
    print("📥 Webhook recebido!")

    try:
        data = request.get_json()
        print("📦 Dados brutos recebidos:", data)

        # Verificações básicas
        if not data:
            print("⚠️ Nenhum dado recebido no corpo da requisição.")
            return jsonify({"status": "no-data"}), 400

        message = data.get("message", {})
        phone = message.get("from")
        text = message.get("text", {}).get("body")

        if not phone or not text:
            print("⚠️ Telefone ou texto ausente na mensagem recebida.")
            return jsonify({"status": "ignored", "reason": "phone or text missing"}), 200

        print(f"📨 Mensagem recebida de {phone}: {text}")

        # Mensagem de resposta
        resposta = "Olá! Recebemos sua mensagem e em breve retornaremos. 😊"

        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        payload = {
            "phone": phone,
            "message": resposta
        }

        print("➡️ Enviando resposta para Z-API...")
        zapi_response = requests.post(url, json=payload)

        if zapi_response.status_code != 200:
            print(f"❌ Erro na resposta da Z-API: {zapi_response.status_code} - {zapi_response.text}")
            return jsonify({"status": "zapi-error", "detail": zapi_response.text}), 500

        print("✅ Resposta enviada com sucesso:", zapi_response.text)
        return jsonify({"status": "message-sent"}), 200

    except Exception as e:
        print("❗ Erro inesperado:", str(e))
        return jsonify({"status": "error", "detail": str(e)}), 500

# Executar localmente
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
