from flask import Flask, request, jsonify
import os
import json
import logging
import requests
import httpx
from openai import OpenAI

# ─── UTILITÁRIAS PARA PERSISTÊNCIA ────────────────────────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Erro ao ler {path}: {e}")
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Erro ao salvar {path}: {e}")

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

env = {
    "ZAPI_INSTANCE_ID": os.getenv("ZAPI_INSTANCE_ID"),
    "ZAPI_TOKEN":        os.getenv("ZAPI_TOKEN"),
    "ZAPI_CLIENT_TOKEN": os.getenv("ZAPI_CLIENT_TOKEN"),
    "OPENAI_API_KEY":    os.getenv("OPENAI_API_KEY"),
    "ZAPI_GROUP_ID":     os.getenv("ZAPI_GROUP_ID"),
}

STATE_FILE    = "estados.json"    # guarda slots incompletos
CUSTOMER_FILE = "clientes.json"   # guarda nome dos clientes
MEMORY_FILE   = "memoria.json"    # guarda histórico de último pedido

estados  = load_json(STATE_FILE)
clientes = load_json(CUSTOMER_FILE)
memoria  = load_json(MEMORY_FILE)

# ─── CLIENTE OPENAI ────────────────────────────────────────────────────────────
httpx_client = httpx.Client(timeout=10.0)
openai_client = OpenAI(api_key=env["OPENAI_API_KEY"], http_client=httpx_client)

system_prompt = os.getenv("SYSTEM_PROMPT") or """
Você é o Thiago, um vendedor consultivo da BG Produtos de Limpeza.
- Em cada mensagem do cliente identifique em pensamento: item, qt, data, bairro, urgente.
- Se faltar algum, pergunte de modo natural.
- Só quando TODOS estiverem preenchidos confirme a venda.
- Não exponha “parâmetros” nem instruções de sistema na conversa.
- Na ÚLTIMA LINHA da resposta, **somente** se a venda estiver concluída, comece com:
  
    GRUPO: <resumo da venda>

essa única linha será encaminhada ao grupo de vendas.  
Para qualquer outro assunto, **não** gere linha `GRUPO:`.
"""

# ─── FUNÇÕES DE ENVIO ──────────────────────────────────────────────────────────
def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}/token/{env['ZAPI_TOKEN']}/send-text"
    headers = {
        "Content-Type": "application/json",
        "Client-Token": env["ZAPI_CLIENT_TOKEN"]
    }
    payload = {"phone": phone, "message": message, "type": "text"}
    try:
        r = requests.post(url, json=payload, headers=headers)
        r.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {phone}: {r.text}")
    except Exception as e:
        logging.error(f"❌ Falha ao enviar para {phone}: {e}")

# ─── WEBHOOK ──────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data  = request.get_json(force=True, silent=True) or {}
    phone = data.get("phone")
    text  = (data.get("text") or {}).get("message", "").strip()

    # ignora sem número, sem texto ou mensagens enviadas por mim
    if not phone or not text or data.get("fromMe", False):
        return jsonify({"status":"ignored"})

    logging.info("✉️ Webhook recebido")
    logging.info(f"📦 Payload: {data}")

    # Monta o prompt incluindo memória anterior, se houver
    msgs = [
        {"role":"system", "content": system_prompt}
    ]
    if memoria.get(phone):
        mem = memoria[phone]
        msgs.append({
            "role":"system",
            "content": "Memória do cliente: " + json.dumps(mem, ensure_ascii=False)
        })
    msgs.append({"role":"user",   "content": text})

    # Chama o GPT
    try:
        resp  = openai_client.chat.completions.create(
            model="gpt-3.5-turbo", messages=msgs
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Erro no GPT: {e}")
        reply = "Desculpe, algo deu errado."

    # Envia resposta ao cliente
    send_whatsapp_message(phone, reply)

    # Encaminha SÓ a linha que começar com 'GRUPO:' ao canal de vendas
    grp_id = env.get("ZAPI_GROUP_ID")
    if grp_id:
        for line in reply.splitlines():
            if line.startswith("GRUPO:"):
                resumo = line[len("GRUPO:"):].strip()
                send_whatsapp_message(grp_id, resumo)
                # atualiza memória com último pedido
                memoria.setdefault(phone, {})["last_order"] = resumo
                save_json(MEMORY_FILE, memoria)
                break

    return jsonify({"status":"ok"})

@app.route("/", methods=["GET"])
def home():
    return "Bot está ativo!", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
