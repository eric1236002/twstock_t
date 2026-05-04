import httpx
import os
from dotenv import load_dotenv

load_dotenv()

proxy_username = os.getenv('PROXY_USERNAME')
proxy_password = os.getenv('PROXY_PASSWORD')
proxy_host = os.getenv('PROXY_HOST')
proxy_port = os.getenv('PROXY_PORT')

proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"

print(f"Testing proxy: {proxy_url}")

try:
    with httpx.Client(proxies={"http://": proxy_url, "https://": proxy_url}, timeout=10.0) as client:
        resp = client.get("https://httpbin.org/ip")
        print(f"Success! IP: {resp.json()['origin']}")
except Exception as e:
    print(f"Failed: {e}")
