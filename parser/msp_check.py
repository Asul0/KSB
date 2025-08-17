# Файл: parsers/msp_check.py (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)

import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Настройки ---
RMSP_URL = "https://rmsp.nalog.ru/"
DEBUG_DIR = "debug_logs"

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def save_debug_html(page_source, inn):
    """Сохраняет HTML-код для анализа."""
    if not os.path.exists(DEBUG_DIR):
        os.makedirs(DEBUG_DIR)
    filename = os.path.join(DEBUG_DIR, f"debug_msp_{inn}.html")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(page_source)
        logging.info(f"HTML-ответ сохранен для анализа в файл: {filename}")
    except Exception as e:
        logging.error(f"Не удалось сохранить отладочный файл: {e}")


def get_msp_category(inn_to_check: str) -> str | None:
    """
    Проверяет ИНН в реестре МСП и ВОЗВРАЩАЕТ категорию субъекта или None.
    """
    if not inn_to_check or not inn_to_check.isdigit():
        logging.error("ОШИБКА ВВОДА: ИНН должен состоять только из цифр.")
        return None

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        logging.info(f"Проверяю ИНН {inn_to_check} в реестре МСП...")
        driver.get(RMSP_URL)

        query_input = driver.find_element(By.ID, "query")
        query_input.send_keys(inn_to_check)
        find_button = driver.find_element(By.XPATH, "//button[text()='Найти']")
        find_button.click()

        try:
            element = WebDriverWait(driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located(
                        (By.XPATH, "//tbody[@id='tblResultData']/tr")
                    ),
                    EC.visibility_of_element_located((By.ID, "pnlNoResult")),
                )
            )
            save_debug_html(driver.page_source, inn_to_check)

            if element.tag_name == "tr":
                logging.info(f"ИНН {inn_to_check} найден в реестре МСП.")
                tbody = element.find_element(By.XPATH, "./parent::tbody")
                columns = tbody.find_elements(By.TAG_NAME, "td")

                # Извлекаем категорию и приводим к нижнему регистру для унификации
                category_text = (
                    columns[1].text.strip().lower()
                )  # "Микропредприятие" -> "микропредприятие"

                # Возвращаем результат
                return category_text
            else:
                logging.warning(f"ИНН {inn_to_check} не найден в реестре МСП.")
                return None

        except TimeoutException:
            logging.error("Время ожидания ответа от rmsp.nalog.ru вышло.")
            save_debug_html(driver.page_source, inn_to_check)
            return None

    except Exception as e:
        logging.error(
            f"Критическая ошибка при работе с реестром МСП: {e}", exc_info=True
        )
        return None
    finally:
        if driver:
            driver.quit()


# Блок для самостоятельной проверки скрипта
if __name__ == "__main__":
    print("--- Утилита проверки ИНН в реестре МСП ---")
    test_inn = input("Введите ИНН для теста: ").strip()
    category = get_msp_category(test_inn)

    if category:
        print(f"\n✅ УСПЕХ: Компания найдена.")
        print(f"   Категория: {category.capitalize()}")
    else:
        print("\n❌ НЕУДАЧА: Компания не найдена в реестре МСП.")
