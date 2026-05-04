import requests
from bs4 import BeautifulSoup
import random,time
import socket
hostname = socket.gethostname()
ip = socket.gethostbyname(hostname)
# with open('proxy_list.txt', 'r') as file:
#     proxy_ips = file.read().splitlines()
#     file.close()
with open('./上櫃代號/CODE.csv', 'r') as file:
    code = file.read().splitlines()
    file.close()
# code=['1584',
# '1586',
# '1591',
# '1593',
# '1595',
# '1599']
import datetime
now_time = datetime.datetime.now()
year = int(now_time.strftime('%Y'))-1911
month= int(now_time.strftime('%m'))
ans=[]
change=0
# proxy_ip = random.choice(proxy_ips)
# proxy_ips=validips
for i in code:
    change+=1
    if change>10:
        change=0
        time.sleep(60)
    # proxy_ip = random.choice(proxy_ips)
    payload={'id':	"",
            'key':	"",
            'step':	"1",
            'co_id':	i,
            'year':	year,
            'seamon':	month,
            'mtype':	"B",    
            'dtype':	""}
    print(f'使用IP：{ip}')
    print(f'代號：{i}')
    try:
        html=requests.post("https://doc.twse.com.tw/server-java/t57sb01?",data = payload)
        sp = BeautifulSoup(html.text,  "html.parser")
        num=sp.find_all('tr') 
        body=sp.find_all('body')
        # print(body)
        temp=[]
        for i in range(0,len(num)):
                temp.append(num[i].find_all('td'))
        for i in range(2,len(temp)):
            #     date=temp[i][9].text
                if temp[i][5].text=="各類公司債(稿本)" or temp[i][5].text=="增資發行(稿本)":
                    buffer=[]       
                    for j in range(0,len(temp[i])):
                        buffer.append(temp[i][j].text)
                    ans.append(buffer)
                    print(buffer)
    except:
        time.sleep(60*5)
        print("error")
final=[]
for i in ans:
    last=[i[0],i[5],i[9]]
    final.append(last)
import csv
with open('./'+ now_time.strftime('%m') + '月data.csv', 'wt', newline='') as student_file:
    writer = csv.writer(student_file)
    for i in final:
        writer.writerow(i)