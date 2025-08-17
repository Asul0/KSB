import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options

# --- Настройка ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
# --- Конец настройки ---


def check_inn_on_nalog_ru_selenium(inn: str) -> bool | None:
    """
    Проверяет ИНН на сайте ФНС по принципу "Если не успех, значит неудача".
    """
    if not inn.isdigit():
        logging.error("ИНН должен состоять только из цифр.")
        return None

    # --- НАСТРОЙКА "БЕЗГОЛОВОГО" РЕЖИМА ---
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    logging.info("Запускаю Chrome в 'безголовом' (фоновом) режиме.")

    try:
        driver.get("https://egrul.nalog.ru/index.html")
        logging.info("Успешно открыл страницу в фоне.")

        # --- ШАГ 1: Вводим ИНН ---
        search_box = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "query"))
        )
        search_box.send_keys(inn)
        logging.info(f"Ввел ИНН '{inn}' в поле поиска.")

        # --- ШАГ 2: Нажимаем кнопку "Найти" ---
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_button.click()
        logging.info("Нажал на кнопку 'Найти'.")

        # --- ШАГ 3: Ждем ТОЛЬКО УСПЕХА ---
        logging.info(
            "Жду появления признака УСПЕХА (<a class='op-excerpt'>) в течение 10 секунд..."
        )
        wait = WebDriverWait(driver, 10)

        # Пытаемся дождаться ТОЛЬКО элемента, который означает успех
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "op-excerpt")))

        # Если мы дошли до этой строки, значит, элемент успеха найден
        logging.info("РЕЗУЛЬТАТ: Успех! Найден элемент с результатами.")
        return True

    except TimeoutException:
        # Если за 10 секунд элемент успеха не появился, это и есть наш случай "не найдено"
        logging.warning("РЕЗУЛЬТАТ: Неудача! Элемент успеха не появился за 10 секунд.")
        return False
    except Exception as e:
        logging.error(f"Произошла непредвиденная критическая ошибка: {e}")
        return None
    finally:
        # --- ФИНАЛЬНЫЙ ШАГ: Обязательно закрываем браузер ---
        logging.info("Закрываю фоновый браузер.")
        if driver:
            driver.quit()


if __name__ == "__main__":
    try:
        input_inn = input("Введите ИНН для проверки на сайте ФНС: ").strip()
        is_found = check_inn_on_nalog_ru_selenium(input_inn)

        print("\n" + "=" * 40)
        print("          РЕЗУЛЬТАТ ПРОВЕРКИ")
        print("=" * 40)

        if is_found is True:
            print("✅ Проверка пройдена: ИНН найден в реестре ФНС.")
        elif is_found is False:
            print("❌ Проверка не пройдена: ИНН не найден в реестре ФНС.")
        else:
            print("⚠️ Не удалось выполнить проверку. Пожалуйста, проверьте лог ошибок.")

        print("\n" + "=" * 40)

    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем.")
