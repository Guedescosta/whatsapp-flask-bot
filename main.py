import os
import requests

ZAPI_INSTANCE_ID = os.getenv('ZAPI_INSTANCE_ID')
ZAPI_TOKEN = os.getenv('ZAPI_TOKEN')

def test_zapi():
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
    payload = {
        "phone": "5599999999999",  # Substitua por um número de teste válido
        "message": "Teste de mensagem via API"
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Resposta: {response.text}")
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao testar Z-API: {e}")

if __name__ == '__main__':
    test_zapi()
