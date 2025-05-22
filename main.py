from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# VARIÁVEIS FIXAS (caso deseje, substitua por os.environ.get() para ambiente seguro)
ZAPI_INSTANCE_ID = "3DFAED34CAF760CDDF170A1EFCACDE10"
ZAPI_TOKEN = "97DAA07311ACEFFA36DF23AF"

@app.route('/', methods=['GET'])
def home():
    return '✅ Bot do WhatsApp está rodando!'

@app.route('/', methods=['POST'])
def receber_mensagem():
    dados = request.get_json()

    try:
        mensagem = dados['message']['text']['body']
        numero = dados['message']['from']
    except (KeyError, TypeError):
        return jsonify({'status': 'mensagem ignorada'}), 200

    resposta = gerar_resposta(mensagem)

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-messages"
    payload = {
        "messages": [{
            "to": numero,
            "type": "text",
            "text": {"body": resposta}
        }]
    }

    requests.post(url, json=payload)
    return jsonify({'status': 'mensagem enviada'}), 200

def gerar_resposta(texto):
    texto = texto.strip().lower()
    if texto == 'oi':
        return "Olá! 👋 Como posso te ajudar hoje?"
    return f"Você disse: {texto}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
