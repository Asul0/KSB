import io
import os
import sys
import requests
import traceback
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pdfplumber

# Подавляем только предупреждения о небезопасном SSL-соединении
try:
    from urllib3.exceptions import InsecureRequestWarning

    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    pass


def get_subsidy_limits() -> dict | None:
    """
    Загружает с сайта Минсельхоза РФ PDF, извлекает данные
    и возвращает их в виде структурированного словаря.
    """
    BASE_URL = "https://mcx.gov.ru/activity/state-support/measures/preferential-credit/info-plan-lgotnogo-kreditovaniya-tekushchiy-ostatok-subsidii-perechen-odobrennykh-zayavok-maksimalnyy-raz/"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"

    pdf_url = None
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    # ... (остальные опции без изменений) ...
    driver = webdriver.Chrome(options=chrome_options)
    try:
        # Этап 1: Получение ссылки (без изменений)
        driver.get(BASE_URL)
        link_xpath = "//a[contains(text(), 'Остаток субсидий по состоянию на')]"
        pdf_link_element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, link_xpath)))
        pdf_url = pdf_link_element.get_attribute("href")
    except Exception as e:
        print(f"Критическая ошибка на этапе работы браузера: {e}", file=sys.stderr)
        return None
    finally:
        if driver: driver.quit()

    if not pdf_url: return None

    # Этап 2: Скачивание PDF (без изменений)
    try:
        headers = {"User-Agent": USER_AGENT, "Referer": BASE_URL}
        response = requests.get(pdf_url, timeout=60, headers=headers, verify=False)
        response.raise_for_status()
        pdf_file_in_memory = io.BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        print(f"Критическая ошибка скачивания: {e}", file=sys.stderr)
        return None

    # Этап 3: Извлечение данных (без изменений в логике, только в выводе)
    try:
        limits_data = {}
        with pdfplumber.open(pdf_file_in_memory) as pdf:
            master_headers = []
            for page in pdf.pages:
                table = page.extract_table()
                if table and table[0]:
                    master_headers = [h.replace("\n", " ").strip() for h in table[0]]
                    break
            if not master_headers: return None
            activity_headers = master_headers[1:]
            for page in pdf.pages:
                table = page.extract_table()
                if not table: continue
                rows = table[1:]
                for row in rows:
                    if not row or not row[0]: continue
                    region_name = row[0].replace("\n", " ").strip()
                    if not region_name: continue
                    if region_name not in limits_data:
                        limits_data[region_name] = {activity: 0.0 for activity in activity_headers}
                    for i in range(1, len(master_headers)):
                        activity_name = master_headers[i]
                        if i < len(row) and row[i]:
                            try:
                                limit_value = float(row[i].replace(" ", "").replace(",", "."))
                                limits_data[region_name][activity_name] = limit_value
                            except (ValueError, TypeError): pass
        
        # <<< ГЛАВНОЕ ИЗМЕНЕНИЕ: ВОЗВРАЩАЕМ СЛОВАРЬ >>>
        return limits_data

    except Exception as e:
        print(f"Критическая ошибка при обработке PDF: {e}", file=sys.stderr)
        return None

# <<< БЛОК ДЛЯ ТЕСТИРОВАНИЯ ТЕПЕРЬ ИСПОЛЬЗУЕТ JSON >>>
if __name__ == "__main__":
    print("Запускаю парсер лимитов МСХ...")
    all_limits_data = get_subsidy_limits()
    if all_limits_data:
        print("\n--- ИТОГОВЫЕ ДАННЫЕ ПО ЛИМИТАМ (в формате JSON) ---")
        # Выводим в формате JSON, который идеально подходит для передачи в LLM
        print(json.dumps(all_limits_data, ensure_ascii=False, indent=2))
    else:
        print("Не удалось получить данные о лимитах.")

