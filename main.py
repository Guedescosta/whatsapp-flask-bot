from flask import Flask, request, jsonify
import os, logging, requests, httpx, json
def start_bot():
    app = Flask(__name__)
    logging.basicConfig(level=logging.INFO)

    # ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────
    ZAPI_INSTANCE_ID  = os.getenv("ZAPI_INSTANCE_ID")
    ZAPI_TOKEN        = os.getenv("ZAPI_TOKEN")
    ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
    OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
    ZAPI_GROUP_ID     = os.getenv("ZAPI_GROUP_ID")  # ID do grupo “Vendas - IA”

    openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client())

    # APScheduler para motivação diária
    from apscheduler.schedulers.background import BackgroundScheduler
    from datetime import datetime, timedelta
    scheduler = BackgroundScheduler()
    scheduler.start()
    def enviar_motivacao():
        frase = "“Cada desafio superado no código é um passo a mais rumo ao seu objetivo: continue codando com confiança!”"
        if ZAPI_GROUP_ID:
            send_whatsapp_message(ZAPI_GROUP_ID, frase)
    scheduler.add_job(enviar_motivacao, trigger="cron", hour=8, minute=0, timezone="America/Sao_Paulo")

    # ─── ARMAZENAMENTO ───────────────────────────────────────────────────
    STATE_FILE    = "estados.json"
    CUSTOMER_FILE = "clientes.json"
    def load_json(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    def save_json(path, data):
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

    estados  = load_json(STATE_FILE)   # phone → state dict
    clientes = load_json(CUSTOMER_FILE) # phone → {nome, bairro_padrao}

    # ─── UTILITÁRIAS ────────────────────────────────────────────────────
    def send_whatsapp_message(phone, text):
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        headers = {"Content-Type":"application/json","Client-Token":ZAPI_CLIENT_TOKEN}
        try:
            r = requests.post(url, json={"phone":phone,"message":text,"type":"text"}, headers=headers)
            r.raise_for_status(); logging.info(f"✅ Mensagem enviada para {phone}: {r.text}")
        except Exception as e:
            logging.error(f"❌ Falha ao enviar para {phone}: {e}")
    def send_group_message(text):
        if ZAPI_GROUP_ID: send_whatsapp_message(ZAPI_GROUP_ID, text)

    # extrai slots com GPT
    def extrair_slots(msg):
        prompt = f"""
Você é um parser de pedidos. Retorne apenas JSON com:
- item (string), qt (int), data (string), bairro (string), urgente (bool), faltando (lista)
Frase: "{msg}"
"""
        res = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system","content":prompt}]
        )
        return json.loads(res.choices[0].message.content)

    def proxima_pergunta(chave):
        texts = {
            "item":   "Qual produto você gostaria de pedir?",
            "qt":     "Quantas unidades?",
            "data":   "Para qual data?",
            "bairro": "Em qual bairro?",
            "urgente":"Essa entrega é urgente? (sim/não)"
        }
        return texts.get(chave, "Pode me detalhar o pedido?")

    @app.route("/webhook", methods=["POST"])
    def webhook():
        data  = request.get_json()
        phone = data.get("phone")
        msg   = data.get("text",{}).get("message","").strip()
        if not phone or not msg or data.get("fromMe"): return jsonify({"status":"ignored"})
        logging.info(f"✉️ Webhook: {msg} from {phone}")

        # memória de entrega em andamento
        state = estados.get(phone, {})
        mem = state.get("pedido_confirmado")
        if mem and any(k in msg.lower() for k in ["entrega","amanhã","chega"]):
            system = (
                f"Você é Thiago da BG. O cliente já pediu {mem['qt']}x {mem['item']} "
                f"para {mem['data']} em {mem['bairro']}{' (URGENTE)' if mem['urgente'] else ''}. "
                "Responda naturalmente se e quando a entrega ocorrer." )
            comp = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"system","content":system},{"role":"user","content":msg}]
            )
            resp = comp.choices[0].message.content.strip()
            send_whatsapp_message(phone, resp)
            return jsonify({"status":"delivery_status"})

        # coleta nome e bairro padrão
        if phone not in clientes:
            send_whatsapp_message(phone, "Olá! Pra começarmos, qual é o seu nome?")
            clientes[phone] = {"nome":None,"bairro_padrao":None}
            save_json(CUSTOMER_FILE, clientes); estados.pop(phone,None)
            return jsonify({"status":"ask_name"})
        if clientes[phone]["nome"] is None:
            clientes[phone]["nome"] = msg.title()
            save_json(CUSTOMER_FILE, clientes)
            send_whatsapp_message(phone, f"Obrigado, {clientes[phone]['nome']}! 😊 Vamos ao pedido.")
            return jsonify({"status":"name_saved"})

        # slot-filling
        st = estados.get(phone, {})
        if st.get("esperando"):
            chave = st.pop("esperando")
            st[chave] = msg if chave!="urgente" else msg.lower() in ("sim","s")
            falt = [k for k in ["item","qt","data","bairro","urgente"] if k not in st or not st[k]]
            if falt:
                nxt = falt[0]; st["esperando"] = nxt; estados[phone]=st; save_json(STATE_FILE,estados)
                send_whatsapp_message(phone,proxima_pergunta(nxt)); return jsonify({"status":"ask_slot"})
            slots = st; estados.pop(phone)
        else:
            slots = extrair_slots(msg)
            falt = slots.pop("faltando",[])
            if falt:
                nxt = falt[0]; slots["esperando"] = nxt; estados[phone]=slots; save_json(STATE_FILE,estados)
                send_whatsapp_message(phone,proxima_pergunta(nxt)); return jsonify({"status":"ask_slot"})

        # confirmação de pedido
        nome = clientes[phone]["nome"]
        cli_msg = (f"✅ Pedido confirmado: {slots['qt']}x {slots['item']} para {slots['data']} em {slots['bairro']}"
                   +(" (URGENTE)" if slots['urgente'] else"")
                   +". Avisaremos quando estivermos a caminho.")
        send_whatsapp_message(phone,cli_msg)
        # notifica grupo
        estado = {**slots}
        estado['nome']=nome; estados[phone]={"pedido_confirmado":estado}; save_json(STATE_FILE,estados)
        grp = (f"📅 {nome} pediu {slots['qt']}x {slots['item']} em {slots['bairro']} para {slots['data']}"
               +(" (URGENTE)" if slots['urgente'] else""))
        send_group_message(grp)
        return jsonify({"status":"order_complete"})

    @app.route("/", methods=["GET"])
    def home(): return "Bot rodando!",200

    return app

if __name__ == "__main__":
    import sys
    from openai import OpenAI
    app = start_bot()
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT",5000)))
