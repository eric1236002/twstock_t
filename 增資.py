#!/usr/bin/python
# -*- coding: big5 -*-
from bs4 import BeautifulSoup
import requests
import datetime
from abc import ABC, abstractmethod
import openpyxl
from openpyxl import Workbook
import csv
now_time = datetime.datetime.now()
yes_time = now_time + datetime.timedelta(days=-1)
yes_time_mon=yes_time.strftime('%m')
yes_time_day=yes_time.strftime('%d')
payload = {
            'step': '0',
            'newstuff': '1',
            'firstin': '1',
            'year': str(int(now_time.strftime('%Y')) -1911),
            'month': yes_time_mon,
            'day': yes_time_day
}
url = "https://mops.twse.com.tw/mops/web/t05st02"
res = requests.post(url,data = payload)
soup = BeautifulSoup(res.content, "html.parser")
itams1 = soup.find_all("tr", {'class': 'even'})
itams2 = soup.find_all("tr", {'class': 'odd'})
buf={'增資','公司債'}
i=1
def find(ABC):
# 用python建立一個Excel空白活頁簿
      excel_file = Workbook()
# 建立一個工作中表
      sheet = excel_file.active
      sheet['A1'] = '日期'
      sheet['B1'] = '代號'
      sheet['C1'] = '公司'
      sheet['D1'] = '標題'
      sheet['E1'] = '內容'
      temp=ABC
      content=""
      for itam in itams1:
            nums=itam.find_all("input", {"type": "hidden"})
            if(len(nums)==0):
                continue
            key=nums[12].get('value')#找內容
            if key.find(temp)>=0:
                day=nums[10].get('value')
                code=nums[9].get('value')
                name=nums[8].get('value')
                title =nums[12].get('value')
                detail = nums[16].get('value')
                content += f"代號:{code} \n公司:{name} \n標題:{title} \n\n"
                sheet.append([day,code,name,title,detail])
      for itam in itams2:
 
            nums=itam.find_all("input", {"type": "hidden"})
            if(len(nums)==0):
                continue
            key=nums[4].get('value')#找內容
            if key.find(temp)>=0:
                code=nums[1].get('value')
                name=nums[0].get('value')
                title =nums[4].get('value')
                detail = nums[8].get('value') 
                content += f"代號:{code} \n公司:{name} \n標題:{title} \n\n"
                sheet.append([day,code,name,title,detail])
      if content=='':
            content='無相關'+ABC+'資料'
            print(content)
      
#存日期
      print('======================計算中======================'+ABC)
      excel_file.save(  now_time.strftime('%Y')+yes_time_mon+yes_time_day+ABC+'資料.xlsx')
      print('檔案已存成: '+ now_time.strftime('%Y')+yes_time_mon+ yes_time_day+ABC+'資料.xlsx')
find('增資')
find('公司債')