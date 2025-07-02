import os
import json
import logging
import requests
import httpx
from flask import Flask, request, jsonify
from openai import OpenAI

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Variáveis de ambiente
ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")  # grupo de vendas

# Arquivo de memória
MEMORY_FILE = "memory.json"

# Inicializa cliente OpenAI
httpx_client = httpx.Client()
openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)

# Prompt de sistema ajustado
system_prompt = os.getenv("SYSTEM_PROMPT") or """
Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza.
Use linguagem natural, calorosa, destaque benefícios dos produtos, sugira upsells (ex.: "Gostaria de levar nosso kit com desconto?").
Em cada mensagem do cliente, identifique mentalmente: item, quantidade, data de entrega, bairro e urgência.
Se faltar alguma informação, pergunte de modo natural e focado.
Quando o cliente confirmar a compra, finalize com algo como "Perfeito, já providencio..." e NA ÚLTIMA LINHA inclua:
GRUPO: Venda de X unidades de ITEM para entrega DATA no bairro BAIRRO.
Para quaisquer dúvidas gerais, responda normalmente sem tocar nessa lógica.
"""

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_memory():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_memory(mem):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    payload = {"phone": phone, "message": message, "type": "text"}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

# ─── ROTAS ─────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True) or {}
    phone = data.get("phone")
    text  = (data.get("text") or {}).get("message","").strip()
    # ignora se for nossa própria mensagem ou sem número/texto
    if not phone or not text or data.get("fromMe", False):
        return jsonify({"status":"ignored"})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # carrega ou inicializa memória do cliente
    memory = load_memory()
    user = memory.get(phone, {})

    # primeira mensagem -> saudação e ativa flag
    if not user.get("started"):
        send_whatsapp_message(phone, "Olá! Como posso ajudar você hoje? 😊")
        user["started"] = True
        memory[phone] = user
        save_memory(memory)
        return jsonify({"status":"greeted"})

    # prepara e envia para o GPT
    messages = [
        {"role":"system", "content": system_prompt},
        {"role":"user",   "content": text}
    ]
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"❌ Erro no GPT: {e}")
        reply = "Desculpe, algo deu errado. Poderia repetir?"

    # envia resposta ao cliente
    send_whatsapp_message(phone, reply)

    # encaminha AO GRUPO apenas a linha que começa com "GRUPO:"
    if ZAPI_GROUP_ID:
        for line in reply.splitlines():
            if line.startswith("GRUPO:"):
                resumo = line[len("GRUPO:"):].strip()
                send_whatsapp_message(ZAPI_GROUP_ID, resumo)
                break

    return jsonify({"status":"ok"})

@app.route("/", methods=["GET"])
def home():
    return "Bot ativo!", 200

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
