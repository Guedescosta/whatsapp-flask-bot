import os import json import logging import requests import httpx from flask import Flask, request, jsonify from datetime import datetime, timedelta from openai import OpenAI

app = Flask(name) logging.basicConfig(level=logging.INFO)

─── CONFIG ─────────────────────────────────────────────────────────────────

ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID") ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN") ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN") ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")  # Vendas - IA OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")

OpenAI client

httpx_client = httpx.Client(timeout=10) openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)

State persistence files

STATE_FILE   = "states.json"     # conversational slots & flags per user CUSTOMER_FILE= "customers.json"  # map phone -> name

load/save utilities

def load_json(path): try: with open(path, encoding='utf-8') as f: return json.load(f) except: return {}

def save_json(path, data): with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

in-memory but saved on each change

states   = load_json(STATE_FILE) customers= load_json(CUSTOMER_FILE)

Send via Z-API

headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN} def send_whatsapp(phone, text): url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text" payload = {"phone": phone, "message": text, "type": "text"} try: r = requests.post(url, json=payload, headers=headers) r.raise_for_status() logging.info(f"Sent to {phone}: {r.text}") except Exception as e: logging.error(f"Failed send to {phone}: {e}")

Extract slots with GPT

def parse_order(msg): prompt = ( "Você é um vendedor: extraia item, qt, data, bairro e urgente de forma natural. " "Se faltar, retorne também faltando:[...] na lista."
f"\nMensagem: '{msg}'" ) res = openai_client.chat.completions.create( model="gpt-3.5-turbo", messages=[{"role":"system","content":prompt}], ) return json.loads(res.choices[0].message.content)

Questions per field

def next_question(field): texts = { "item":    "Qual produto você deseja?", "qt":      "Quantas unidades?", "data":    "Para qual data?", "bairro":  "Qual bairro?", "urgente": "É urgente? (sim/não)", } return texts.get(field, "Pode detalhar? 🚚")

Webhook@app.route("/webhook", methods=["POST"])

def webhook(): data = request.get_json(force=True, silent=True) or {} phone = data.get("phone") text  = (data.get("text") or {}).get("message",""").strip() if not phone or not text or data.get("fromMe"): return jsonify(status="ignored")

# greet & ask name
if phone not in customers:
    send_whatsapp(phone, "Olá! Pra começar, qual é seu nome?")
    customers[phone] = None
    save_json(CUSTOMER_FILE, customers)
    states.pop(phone, None)
    return jsonify(status="ask_name")
if customers[phone] is None:
    customers[phone] = text.title()
    save_json(CUSTOMER_FILE, customers)
    send_whatsapp(phone, f"Obrigado, {customers[phone]}! 😊 Vamos ao pedido.")
    states.pop(phone, None)
    return jsonify(status="name_saved")

st = states.get(phone, {})

# state: waiting confirmation? (double-check)
if st.get("confirm_pending"):
    if text.lower().startswith("s"):
        # send group notification
        summary = st.get("group_summary")
        if summary and ZAPI_GROUP_ID:
            send_whatsapp(ZAPI_GROUP_ID, summary)
        send_whatsapp(phone, "Venda confirmada e anotada! Obrigado 😊")
    else:
        send_whatsapp(phone, "Tudo bem, me diga o que quer ajustar no pedido.")
    states.pop(phone, None)
    save_json(STATE_FILE, states)
    return jsonify(status="confirmation")

# collect slots
if not st:
    # initial parse
    parsed = parse_order(text)
    missing = parsed.get("faltando", [])
    slots = {k:parsed[k] for k in ["item","qt","data","bairro","urgente"] if k in parsed}
    if missing:
        f = missing[0]
        slots["waiting"] = f
        states[phone] = slots
        save_json(STATE_FILE, states)
        send_whatsapp(phone, next_question(f))
        return jsonify(status="ask_slot")
    st = slots
elif st.get("waiting"):
    key = st.pop("waiting")
    val = text if key!="urgente" else text.lower().startswith("s")
    st[key] = val
    # check again
    miss = [k for k in ["item","qt","data","bairro","urgente"] if k not in st or st[k] in (None,"")]
    if miss:
        nxt = miss[0]
        st["waiting"] = nxt
        states[phone] = st
        save_json(STATE_FILE, states)
        send_whatsapp(phone, next_question(nxt))
        return jsonify(status="ask_slot")
else:
    # unexpected: restart
    states.pop(phone, None)
    save_json(STATE_FILE, states)
    send_whatsapp(phone, "Desculpe, vamos recomeçar. Qual produto deseja?")
    return jsonify(status="reset")

# all slots present: double-check summary to user
customer = customers[phone]
summary = (
    f"Venda de {st['qt']}x {st['item']} para {st['data']} em {st['bairro']} "
    + ("(URGENTE)" if st['urgente'] else "")
)
msg_cli = (f"Perfeito, {customer}! Confirma? {summary}\nResponda: sim/não")
# store pending confirmation
states[phone] = {"confirm_pending":True, "group_summary": summary}
save_json(STATE_FILE, states)
send_whatsapp(phone, msg_cli)
return jsonify(status="ask_confirm")

@app.route("/", methods=["GET"]) def home(): return "Bot rodando", 200

if name=="main": app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))

