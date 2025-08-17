# src/tools/company_data_parser.py
# (Бывший full_cheko.py, адаптированный для использования в проекте)

import requests
from bs4 import BeautifulSoup
import logging
import re
from datetime import datetime
import os
import time
from urllib.parse import urljoin
import asyncio

from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# УДАЛИТЬ или закомментировать эти строки
# from selenium.webdriver.chrome.service import Service as ChromeService
# from webdriver_manager.chrome import ChromeDriverManager
# --- 1. ОБЩИЕ НАСТРОЙКИ ---
# Настройка логирования будет на уровне всего приложения, но оставим для отладки
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("webdriver_manager").setLevel(logging.WARNING)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
DEBUG_DIR = "debug_html"

# --- 2. УНИВЕРСАЛЬНЫЕ ФУНКЦИИ (ПОИСК И ЗАГРУЗКА) ---


def save_debug_html(html_content: str, inn: str):
    if not os.path.exists(DEBUG_DIR):
        os.makedirs(DEBUG_DIR)
    filename = os.path.join(
        DEBUG_DIR, f"checko_page_{inn}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        logging.info(f"HTML-код страницы сохранен для отладки в: {filename}")
    except IOError as e:
        logging.error(f"Не удалось сохранить HTML-файл: {e}")


def get_company_page_url(inn: str) -> str | None:
    if not inn.isdigit() or not (10 <= len(inn) <= 12):
        logging.error(f"ИНН '{inn}' некорректен.")
        return None
    search_url = f"https://checko.ru/search?query={inn}"
    logging.info(f"ПАРСЕР: Поиск страницы компании для ИНН {inn}...")
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        if "/company/" in response.url:
            logging.info(f"ПАРСЕР: Найдена страница: {response.url}")
            return response.url
        else:
            logging.error(f"ПАРСЕР: Не удалось найти страницу компании для ИНН {inn}.")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"ПАРСЕР: Критическая ошибка при поиске URL компании: {e}")
        return None


def get_full_page_html_with_selenium(url: str) -> str | None:
    logging.info("ПАРСЕР: Загрузка страницы с помощью Selenium...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = None
    try:
        # Используем кэшированный драйвер, чтобы не скачивать каждый раз
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "main.flex-shrink-0"))
        )
        time.sleep(1)  # Небольшая пауза для полной прогрузки
        logging.info("ПАРСЕР: Страница успешно загружена, HTML получен.")
        return driver.page_source
    except TimeoutException:
        logging.error(
            "ПАРСЕР: Не удалось дождаться загрузки ключевых элементов на странице."
        )
        return None
    except Exception as e:
        logging.error(f"ПАРСЕР: Непредвиденная ошибка при работе Selenium: {e}")
        return None
    finally:
        if driver:
            driver.quit()


# --- 3. ФУНКЦИИ-ПАРСЕРЫ ---


def parse_company_name(soup: BeautifulSoup) -> str:
    """
    Извлекает полное наименование компании, используя несколько методов.
    1. Ищет в заголовке H1 на странице.
    2. Если не найдено, ищет в HTML-теге <title> страницы.
    """
    # --- Попытка №1: Найти в главном заголовке H1 (как и раньше) ---
    main_content = soup.find("article", class_="rc") or soup

    title_tag = main_content.find("h1", class_="card-title")
    if title_tag:
        company_name = title_tag.get_text(strip=True)
        if company_name:
            return company_name

    # --- Попытка №2: Извлечь из тега <title> (надежный запасной вариант) ---
    title_tag_head = soup.find("title")
    if title_tag_head:
        # Текст в <title> обычно выглядит так: "ООО «АГРОФИРМА», ИНН 123 – ..."
        # Мы берем только часть до первой запятой.
        full_title = title_tag_head.get_text(strip=True)
        if "," in full_title:
            company_name = full_title.split(",")[0].strip()
            # Убираем лишние кавычки, если они есть
            company_name = company_name.strip("«»\"\"''")
            if company_name:
                return company_name

    # Если оба способа не сработали, возвращаем пустую строку
    return ""


def parse_general_info(main_content_soup: BeautifulSoup) -> dict:
    data = {}
    dir_header = main_content_soup.find(
        "div", class_="fw-700", string=re.compile(r"Генеральный директор|Руководитель")
    )
    if dir_header:
        dir_container = dir_header.find_parent("div", class_="flex-grow-1")
        if dir_container and dir_container.find("a", class_="link"):
            data["director"] = dir_container.find("a", class_="link").get_text(
                strip=True
            )

    emp_header = main_content_soup.find(
        "div",
        class_="fw-700",
        string=re.compile(r"Среднесписочная численность работников"),
    )
    if emp_header:
        next_div = emp_header.find_next_sibling("div")
        if next_div:
            data["employees"] = " ".join(next_div.get_text(strip=True).split())

    fin_header = main_content_soup.find(
        "div", class_="fw-700", string=re.compile(r"Финансовая отчетность за \d{4} год")
    )
    if fin_header:
        year_match = re.search(r"\d{4}", fin_header.get_text())
        year_str = f" (за {year_match.group(0)} год)" if year_match else ""
        revenue_link = fin_header.find_next_sibling("div").find("a", string="Выручка")
        if revenue_link:
            parent_div = revenue_link.parent
            full_text = parent_div.get_text(strip=True)
            match = re.search(r"(\d[.,\d\s]*(?:тыс|млн|млрд)\s+руб\.)", full_text)
            if match:
                data[f"revenue{year_str}"] = match.group(0)

    address_tag = main_content_soup.find("span", id="copy-address")
    if address_tag:
        data["address"] = address_tag.get_text(strip=True)
    return data


def parse_okved_data(company_url: str) -> dict | None:
    logging.info("ПАРСЕР: Поиск и парсинг данных ОКВЭД...")
    try:
        response = requests.get(company_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        activity_link_tag = soup.find(
            "a", href=lambda href: href and "/activity" in href
        )
        if not activity_link_tag:
            logging.warning(
                "ПАРСЕР: Не найдена ссылка на страницу с видами деятельности."
            )
            return None

        okved_page_url = urljoin(company_url, activity_link_tag["href"])
        logging.info(f"ПАРСЕР: Страница с ОКВЭД найдена: {okved_page_url}")
        okved_response = requests.get(okved_page_url, headers=HEADERS, timeout=10)
        okved_response.raise_for_status()
        okved_soup = BeautifulSoup(okved_response.text, "lxml")
        table = okved_soup.find("table", class_="table-striped")
        if not table:
            logging.warning("ПАРСЕР: Не удалось найти таблицу с ОКВЭД.")
            return None

        result = {"main_okved": None, "additional_okved": []}
        for row in table.find("tbody").find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            okved_item = {
                "code": cells[0].get_text(strip=True),
                "name": cells[1].get_text(strip=True),
            }
            if cells[1].find(
                "span", attrs={"data-bs-title": "Основной вид деятельности"}
            ):
                result["main_okved"] = okved_item
            else:
                result["additional_okved"].append(okved_item)
        logging.info("ПАРСЕР: Данные по ОКВЭД успешно собраны.")
        return result
    except Exception as e:
        logging.error(f"ПАРСЕР: Ошибка при парсинге ОКВЭД: {e}")
        return None


def parse_founders_data(full_soup: BeautifulSoup) -> list[str]:
    logging.info("ПАРСЕР: Поиск и парсинг детальных данных об учредителях...")
    report_lines = []
    founders_block = full_soup.find("section", id="founders")

    if not founders_block or "Нет сведений об учредителях" in founders_block.text:
        logging.warning(
            "ПАРСЕР: Блок с детальной информацией об учредителях не найден или пуст."
        )
        return ["Сведения об учредителях не найдены."]

    elements = founders_block.find_all(["h4", "table"])
    if not elements:
        return [f"Блок 'Учредители' не содержит структурированных данных."]

    for element in elements:
        if element.name == "h4":
            report_lines.append(f"--- {element.get_text(strip=True)} ---")
        elif element.name == "table":
            body_rows = element.find("tbody").find_all("tr")
            for row in body_rows:
                cells_text = [
                    td.get_text(strip=True, separator=" ") for td in row.find_all("td")
                ]
                report_lines.append(" | ".join(cells_text))

    logging.info("ПАРСЕР: Детальные данные по учредителям успешно собраны.")
    return report_lines


# --- 4. ГЛАВНАЯ ФУНКЦИЯ-ОРКЕСТРАТОР ---


def _run_parsing_logic(inn: str) -> dict:
    """Синхронная функция, которая выполняет всю логику парсинга."""
    company_url = get_company_page_url(inn)
    if not company_url:
        return {"error": f"Не удалось найти компанию по ИНН {inn}."}

    full_html = get_full_page_html_with_selenium(company_url)
    if not full_html:
        return {"error": "Не удалось получить HTML-код страницы компании."}

    # Для отладки можно сохранять HTML
    # save_debug_html(full_html, inn)

    soup = BeautifulSoup(full_html, "lxml")
    main_content = soup.find("article", class_="rc")
    if not main_content:
        main_content = soup  # Fallback

    # Собираем все данные
    company_name = parse_company_name(soup)
    general_data = parse_general_info(main_content)
    okved_data = parse_okved_data(company_url)
    founders_lines = parse_founders_data(soup)

    # Формируем итоговый словарь
    return {
        "inn": inn,
        "company_url": company_url,
        "company_name": company_name or f"Компания с ИНН {inn}",
        "general_info": general_data,
        "okved_data": okved_data,
        "founders_data": founders_lines,
        "error": None,
    }


async def get_company_data_by_inn_async(inn: str) -> dict:
    """
    Асинхронный 'wrapper' для запуска блокирующего кода парсера в отдельном потоке.
    Это основная функция, которую нужно вызывать из других асинхронных частей приложения.
    """
    logging.info(f"Запуск асинхронной задачи парсинга для ИНН: {inn}")
    loop = asyncio.get_running_loop()
    # Запускаем синхронную блокирующую функцию в отдельном потоке, чтобы не блокировать event loop
    result_dict = await loop.run_in_executor(None, _run_parsing_logic, inn)
    return result_dict


# --- 5. БЛОК ДЛЯ САМОСТОЯТЕЛЬНОГО ЗАПУСКА И ТЕСТИРОВАНИЯ ---
if __name__ == "__main__":

    async def main():
        print("--- Тестовый запуск парсера данных о компаниях ---")
        try:
            input_inn = input("Введите ИНН организации для теста: ").strip()
            if input_inn:
                data = await get_company_data_by_inn_async(input_inn)
                # Красивый вывод результата для теста
                import json

                print("\n--- РЕЗУЛЬТАТ ПАРСИНГА (в формате JSON) ---")
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print("ИНН не был введен. Завершение работы.")
        except KeyboardInterrupt:
            print("\n\nПрограмма остановлена пользователем.")
        except Exception as e:
            logging.error(
                f"Произошла непредвиденная критическая ошибка: {e}", exc_info=True
            )

    asyncio.run(main())
