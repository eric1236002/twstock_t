import httpx
import os
from dotenv import load_dotenv

load_dotenv()

proxy_username = os.getenv('PROXY_USERNAME')
proxy_password = os.getenv('PROXY_PASSWORD')
proxy_host = os.getenv('PROXY_HOST')
proxy_port = os.getenv('PROXY_PORT')

proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"

payload = {
    'id': "",
    'key': "",
    'step': "1",
    'co_id': "1101",
    'year': 113,
    'seamon': 5,
    'mtype': "B",
    'dtype': ""
}

try:
    with httpx.Client(proxy=proxy_url, timeout=15.0, verify=False) as client:
        print("Sending request...")
        response = client.post("https://doc.twse.com.tw/server-java/t57sb01", data=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.text)}")
        if response.status_code == 200:
            print("Preview:")
            print(response.text[:500])
except Exception as e:
    print(f"Error: {e}")
