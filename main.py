import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
import http.cookiejar
import lxml.html
import json

from airtable import Airtable
from dotenv import load_dotenv
import datetime
import time

load_dotenv()

def _fetch_detail(driver, order_id):
  driver.get(os.environ['DETAIL_URL'].format(order_id))
  html = lxml.html.fromstring(driver.page_source)
  data = json.loads(html.text_content())['data']
  detail = data['order']['evoucher']['pins'][0]
  return detail

def fetch_all_from_shopee(driver):
  page_size = 50 #maximum
  page_num = 1
  group_types = [22, 33]
  count = 0
  for group_type in group_types:
    while True:
      driver.get(os.environ['GROUP_URL'].format(page_size, page_num, group_type))
      html = lxml.html.fromstring(driver.page_source)
      data = json.loads(html.text_content())['data']
      # print('(', (page_num-1)*page_size, ' - ', page_num*page_size, ')', '/', data['total'])
      for item in data['list']:
        detail = _fetch_detail(driver, item['order_id'])
        if detail['is_returned'] == True:
          continue
        record = {
          'Name' : item['item_name'],
          'Img'  : [{ 'url': detail['url']}],
          'Code' : detail['code'],
          'Price' : item['final_price']/100000,
          'Created Date' : datetime.datetime.fromtimestamp(item['create_time']).date().isoformat(),
          'Expiry Date'  : datetime.datetime.strptime(item['evoucher']['pins'][0]['expiry_date'], '%Y%m%d').date().isoformat(),
          'Order ID' : item['order_id'],
          'Done' : detail['is_redeemed']
        }
        # print('add', record['Order ID'], record['Name'])
        # if detail.get('url', None) == None:
          # print(record)

        records[record['Order ID']] = record

      # print(count, len(data['list']));
      if count + len(data['list']) >= data['total'] :
        break
      else:
        count += len(data['list'])
        page_num += 1


records = {}
try:
  options = webdriver.ChromeOptions()
  # options.add_argument('--headless')
  options.add_argument("start-maximized")
  options.add_experimental_option("excludeSwitches", ["enable-automation"])
  options.add_experimental_option('useAutomationExtension', False)
  driver = webdriver.Chrome(options=options)
  driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
  driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
  driver.get("https://shopee.tw/buyer/login")

  cj = http.cookiejar.MozillaCookieJar('cookies.txt')
  cj.load()
  for cookie in cj:
    cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
    if cookie.expires:
        cookie_dict['expiry'] = cookie.expires
    if cookie.path_specified:
        cookie_dict['path'] = cookie.path
    driver.add_cookie(cookie_dict)

  input_text = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.NAME, "loginKey"))
  )
  input_text.send_keys(os.environ['PHONE'])
  input_text = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.NAME, "password"))
  )
  input_text.send_keys(os.environ['PASS'])
  button = WebDriverWait(driver, 10).until(
    # EC.presence_of_element_located((By.XPATH, '//*[@id="main"]/div/div[2]/div/div/form/div/div[2]/button'))
    EC.element_to_be_clickable((By.XPATH, '//*[@id="main"]/div/div[2]/div/div/form/div/div[2]/button'))
  )
  ActionChains(driver).move_to_element(button).click(button).perform()

  fetch_all_from_shopee(driver)

except Exception as e:
  logger.error('Failed to upload to ftp: '+ str(e))
finally:
  driver.quit()
# print(len(records), records.keys())


airtable = Airtable(os.environ['BASE_ID'], os.environ['TABLE_NAME'], os.environ['KEY'])
# print(airtable.get_all())

updates = []
for item in airtable.get_all():
  dup_one = records.get(item['fields']['Order ID'], None)
  if dup_one:

    if dup_one['Expiry Date'] != item['fields']['Expiry Date'] or \
       dup_one['Done'] != item['fields'].get('Done', False) or \
       dup_one['Code'] != item['fields']['Code']:
      # dup_one is newer than airtable record
      dup_one['id'] = item['id']
      updates.append(dup_one)

    del records[item['fields']['Order ID']]

if len(records) > 0:
  airtable.batch_insert(list(records.values()))
if len(updates) > 0:
  airtable.batch_update(updates, False)





