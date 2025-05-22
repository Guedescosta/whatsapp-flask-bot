from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Bot do WhatsApp está rodando! ✅"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Recebido:", data)
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run()
