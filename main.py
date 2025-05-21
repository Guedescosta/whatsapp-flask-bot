from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid data"}), 400

    message = data.get("message", {})
    sender = message.get("from")
    text = message.get("text", {}).get("body")

    if sender and text:
        print(f"Mensagem de {sender}: {text}")
        return jsonify({"response": f"Recebido com sucesso: {text}"}), 200
    return jsonify({"error": "Mensagem inválida"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)