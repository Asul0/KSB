# parser/nt.py (Новая версия без Selenium, с логированием времени)
import os
import re
import sys
import requests
import io
import pdfplumber
import time
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Настраиваем логирование, которое будет использоваться другими модулями
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Подавляем предупреждения
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    pass

def get_sez_inns() -> set | None:
    """
    Скачивает PDF с реестром СЭЗ без Selenium и возвращает множество (set) ИНН.
    """
    log_prefix = "[Парсер СЭЗ]"
    total_start_time = time.time()
    
    BASE_URL = "https://xn--g1at0b.xn--p1aee.xn--p1ai/sez_credit/?"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    headers = {"User-Agent": USER_AGENT}
    
    try:
        # --- Этап 1: Получение ссылки на PDF ---
        logger.info(f"{log_prefix} Этап 1: Загрузка HTML страницы для поиска ссылки...")
        start_time = time.time()
        session = requests.Session()
        session.headers.update(headers)
        response_main = session.get(BASE_URL, timeout=30, verify=False)
        response_main.raise_for_status()
        logger.info(f"{log_prefix} HTML страница загружена за {time.time() - start_time:.2f} сек.")

        soup = BeautifulSoup(response_main.text, 'html.parser')
        pdf_link_element = soup.find('a', string=re.compile(r'Публикация единого реестра'))
        if not pdf_link_element:
            logger.error(f"{log_prefix} Ошибка: Не удалось найти ссылку на PDF на странице.")
            return None

        pdf_url = urljoin(BASE_URL, pdf_link_element.get("href"))
        logger.info(f"{log_prefix} Найдена ссылка на PDF: {pdf_url}")
        
        # --- Этап 2: Скачивание файла ---
        logger.info(f"{log_prefix} Этап 2: Скачивание PDF-файла...")
        start_time = time.time()
        download_headers = headers.copy()
        download_headers['Referer'] = BASE_URL
        response_pdf = session.get(pdf_url, headers=download_headers, timeout=180, verify=False)
        response_pdf.raise_for_status()
        pdf_file_in_memory = io.BytesIO(response_pdf.content)
        logger.info(f"{log_prefix} PDF-файл ({len(response_pdf.content) // 1024} КБ) скачан за {time.time() - start_time:.2f} сек.")

        # --- Этап 3: Извлечение ИНН ---
        logger.info(f"{log_prefix} Этап 3: Извлечение ИНН из PDF...")
        start_time = time.time()
        all_inns = set()
        inn_pattern = re.compile(r"^\d{10}$|^\d{12}$")

        with pdfplumber.open(pdf_file_in_memory) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if len(row) > 7 and row[7]: 
                            cleaned_inn = "".join(filter(str.isdigit, str(row[7])))
                            if inn_pattern.match(cleaned_inn):
                                all_inns.add(cleaned_inn)
        
        logger.info(f"{log_prefix} PDF проанализирован за {time.time() - start_time:.2f} сек. Найдено {len(all_inns)} уникальных ИНН.")
        
        logger.info(f"{log_prefix} Общее время работы парсера: {time.time() - total_start_time:.2f} сек.")
        return all_inns

    except requests.exceptions.RequestException as e:
        logger.error(f"{log_prefix} Произошла ошибка сети: {e}")
        return None
    except Exception as e:
        logger.error(f"{log_prefix} Произошла непредвиденная ошибка: {e}", exc_info=True)
        return None

# Блок для прямого запуска и теста
if __name__ == "__main__":
    inns = get_sez_inns()
    if inns:
        print("\n--- Результат (первые 20 ИНН) ---")
        for i, inn in enumerate(sorted(list(inns))):
            if i >= 402: break
            print(inn)