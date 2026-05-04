import time
import re
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
import openpyxl
from openpyxl import Workbook

options = webdriver.ChromeOptions() 
#prefs = {"profile.managed_default_content_settings.images": 2}
#options.add_experimental_option("prefs", prefs)
#options.add_argument('-headless')  # headless mode
driver = webdriver.Chrome(chrome_options=options)
driver.get('https://mops.twse.com.tw/mops/web/t05sr01_1')

import datetime
now_time = datetime.datetime.now()
yes_time = now_time + datetime.timedelta(days=-1)
yes_time_nyr = yes_time.strftime('%Y%m%d')

try:
    ele = WebDriverWait(driver, 10).until(
        ec.visibility_of_element_located((By.CLASS_NAME, 'noBorder'))
    )

except TimeoutException:
    print('超過時間還是找不到要找的東西')

driver.find_element_by_xpath("/html/body/center/table/tbody/tr/td/div[4]/table/tbody/tr/td/div/table/tbody/tr/td[3]/div/div[3]/div[3]/div/center/form/input[7]").click()
# 從回覆中找「增資」
gex1 = re.compile(r'增資')
gex2 = re.compile(r'公司債')

list = []          ## 空列表
for comment in driver.find_elements_by_tag_name("td"):
    list.append(comment.text)

# 用python建立一個Excel空白活頁簿
excel_file = Workbook()
# 建立一個工作中表
sheet = excel_file.active
sheet['A1'] = '日期'
sheet['B1'] = '代號'
sheet['C1'] = '公司'
sheet['D1'] = '內容'
#存日期
buffday1=" "
print('======================計算中======================增資')
for num in  range(len(driver.find_elements_by_tag_name("td"))):
    if(gex1.findall(list[num]) and num>12):
       sheet.append([list[num-4],list[num-2],list[num-1],list[num]])
       buffday1=list[num-4]
excel_file.save('C:/Users/user/Desktop/'+yes_time_nyr+'增資資料.xlsx')
print('檔案已存成: '+yes_time_nyr+'增資資料.xlsx')

# 用python建立一個Excel空白活頁簿
excel_file = Workbook()
# 建立一個工作中表
sheet = excel_file.active
sheet['A1'] = '日期'
sheet['B1'] = '代號'
sheet['C1'] = '公司'
sheet['D1'] = '內容'
#存日期
buffday2=' '
print('======================計算中======================可轉債')
for num in  range(len(driver.find_elements_by_tag_name("td"))):
    if(gex2.findall(list[num])):
      sheet.append([list[num-4],list[num-2],list[num-1],list[num]])
      buffday2=list[num-4]

excel_file.save('C:/Users/user/Desktop/'+yes_time_nyr+'公司債資料.xlsx')
print('檔案已存成: '+yes_time_nyr+'公司債.xlsx')
driver.quit()