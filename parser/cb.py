# Файл: parsers/cb.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import requests
import logging
import re
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from requests.exceptions import RequestException

# --- Настройки ---
CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/keyrate/"
TABLE_HEADERS = ["Дата", "Ставка"]

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# ... (функции find_key_rate_table, parse_rate_from_table, validate_data остаются БЕЗ ИЗМЕНЕНИЙ) ...
def find_key_rate_table(soup):
    all_tables = soup.find_all("table")
    logging.info(
        f"Найдено {len(all_tables)} таблиц на странице. Начинаю поиск нужной..."
    )
    for table in all_tables:
        headers = [th.text.strip() for th in table.find_all("th")]
        if all(expected_header in headers for expected_header in TABLE_HEADERS):
            logging.info("Найдена целевая таблица с заголовками 'Дата' и 'Ставка'.")
            return table
    logging.error(
        "Не удалось найти на странице таблицу с заголовками 'Дата' и 'Ставка'. Структура сайта могла измениться."
    )
    return None


def parse_rate_from_table(table):
    data_rows = table.find_all("tr")
    if not data_rows:
        logging.error("В найденной таблице нет строк (тегов <tr>).")
        return None, None
    for row in data_rows:
        columns = row.find_all("td")
        if len(columns) >= 2:
            date_str = columns[0].text.strip()
            rate_str = columns[1].text.strip()
            logging.info(
                f"Обнаружены сырые данные: Дата='{date_str}', Ставка='{rate_str}'"
            )
            return date_str, rate_str
    logging.error("Не удалось найти строку с ячейками данных (<td>) в таблице.")
    return None, None


def validate_data(date_str, rate_str):
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    rate_pattern = re.compile(r"^\d{1,2},\d{2}$")
    if (
        date_str
        and rate_str
        and date_pattern.match(date_str)
        and rate_pattern.match(rate_str)
    ):
        logging.info("Данные прошли валидацию. Формат корректный.")
        return True
    logging.warning(
        f"Данные не прошли валидацию! Дата: '{date_str}', Ставка: '{rate_str}'. Возможно, формат данных на сайте изменился."
    )
    return False


def get_cbr_key_rate():
    """
    Основная функция для получения актуальной ключевой ставки.
    Теперь возвращает (ставка, дата) или (None, None) в случае ошибки.
    """
    try:
        ua = UserAgent()
        headers = {"User-Agent": ua.random}
        logging.info(
            f"Отправка запроса на {CBR_KEY_RATE_URL} с User-Agent: {headers['User-Agent']}"
        )
        response = requests.get(CBR_KEY_RATE_URL, headers=headers, timeout=10)
        response.raise_for_status()

        logging.info("Страница успешно загружена. Начинаю парсинг HTML.")
        soup = BeautifulSoup(response.content, "html.parser")

        key_rate_table = find_key_rate_table(soup)
        if not key_rate_table:
            return None, None

        date, rate = parse_rate_from_table(key_rate_table)
        if not date or not rate:
            return None, None

        if not validate_data(date, rate):
            # Даже если валидация не пройдена, мы все равно вернем данные,
            # но предупредим в логах.
            logging.warning(
                "Формат данных может быть некорректным, но мы их возвращаем."
            )

        # ГЛАВНОЕ ИЗМЕНЕНИЕ: Возвращаем результат для использования в других скриптах
        return rate, date

    except RequestException as e:
        logging.error(f"Ошибка сети или HTTP-запроса: {e}")
        return None, None
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка: {e}", exc_info=True)
        return None, None


# Этот блок теперь используется только для прямой проверки скрипта.
# Логика печати вынесена сюда.
if __name__ == "__main__":
    rate_result, date_result = get_cbr_key_rate()

    if rate_result and date_result:
        print("\n--- Актуальная ключевая ставка Банка России ---")
        print(f"  С даты: {date_result}")
        print(f"  Ставка: {rate_result}%")
        print("-------------------------------------------------")
    else:
        print("\nОШИБКА: Не удалось получить ключевую ставку.")
