import httpx
from bs4 import BeautifulSoup
import datetime
import csv
import logging
import concurrent.futures
import time
from tenacity import retry, stop_after_attempt, wait_fixed
import colorlog
import os
from dotenv import load_dotenv
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env file
load_dotenv()

handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    log_colors={
        'DEBUG': 'blue',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
))
logger = colorlog.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Proxy details from environment variables
proxy_username = os.getenv('PROXY_USERNAME')
proxy_password = os.getenv('PROXY_PASSWORD')
proxy_host = os.getenv('PROXY_HOST')
proxy_port = os.getenv('PROXY_PORT')
target_url = 'https://ipv4.icanhazip.com'

# Proxy URL
proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"

# Load codes
with open('./上市代碼/CODE.csv', 'r') as file:
    codes = file.read().splitlines()

now_time = datetime.datetime.now()
year = int(now_time.strftime('%Y')) - 1911
month = int(now_time.strftime('%m')) -1
ans = []

def ip_check(client):
        response = client.get("https://httpbin.org/ip")
        return response.json()["origin"]
@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
def fetch_data(code):
    # Create a client with proxy support
    client = httpx.Client(proxy=proxy_url, verify=False)

    payload = {
        'id': "",
        'key': "",
        'step': "1",
        'co_id': code,
        'year': year,
        'seamon': month,
        'mtype': "B",
        'dtype': ""
    }

    try:
        # Show current IP
        # response = client.get("https://httpbin.org/ip")
        # logging.info(f'IP: {response.json()["origin"]}')
        logging.info(f'Code: {code}')

        response = client.post("https://doc.twse.com.tw/server-java/t57sb01", data=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors

        sp = BeautifulSoup(response.text, "html.parser")
        num = sp.find_all('tr')

        temp = []
        for row in num:
            temp.append(row.find_all('td'))

        for j in range(2, len(temp)):
            if temp[j][5].text in ["各類公司債(稿本)", "增資發行(稿本)"]:
                buffer = [td.text for td in temp[j]]
                ans.append(buffer)
                logging.info(buffer)

    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error occurred: {e}")
        logging.error(f"IP: {ip_check(client)}")
        client.close()
        raise  # Reraise exception to trigger retry
    except Exception as e:
        logging.error(f"An error occurred: {e}" )
        logging.error(f"IP: {ip_check(client)}")
        client.close()
        raise  # Reraise exception to trigger retry
    finally:
        client.close()

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    future_to_code = {executor.submit(fetch_data, code): code for code in codes}
    for future in concurrent.futures.as_completed(future_to_code):
        try:
            future.result()
        except Exception as e:
            logging.error(f"Error fetching data for code {future_to_code[future]}: {e}")

final = []
for item in ans:
    last = [item[0], item[5], item[9]]
    final.append(last)

output_file = f'./{now_time.strftime("%m")}月data.csv'
with open(output_file, 'wt', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(final)

logging.info(f"Data saved to {output_file}")
