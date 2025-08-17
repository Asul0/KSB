import logging
import asyncio
import json
import time
import os
from urllib.parse import urljoin

# --- ИМПОРТЫ ДЛЯ SELENIUM ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 1. НАСТРОЙКИ ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("webdriver_manager").setLevel(logging.WARNING)

# Константы
RIA_SEARCH_URL = "https://sn.ria.ru/search/?query=%D0%BF%D1%80%D0%BE%D0%B3%D0%BD%D0%BE%D0%B7+%D1%83%D1%80%D0%BE%D0%B6%D0%B0%D1%8F+2025"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
# Сколько новостей мы хотим собрать
NEWS_LIMIT = 3

# --- 2. УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ЗАГРУЗКИ ---


def get_html_with_selenium(url: str, wait_for_selector: str) -> str | None:
    """
    УНИВЕРСАЛЬНАЯ ФУНКЦИЯ: Загружает страницу и "умно" ждет появления
    конкретного элемента, указанного в wait_for_selector.
    """
    logging.info(f"Загрузка страницы {url} с помощью Selenium...")
    logging.info(f"Будем ждать появления элемента: '{wait_for_selector}'")

    options = webdriver.ChromeOptions()
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)

    # Режим без UI (headless) - можно включить после отладки
    options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        driver.get(url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
        )
        time.sleep(2)  # Страховочная пауза

        logging.info("Ключевой элемент найден. Получаем HTML-код.")
        return driver.page_source

    except TimeoutException:
        logging.error(f"Тайм-аут: не удалось дождаться элемента '{wait_for_selector}'.")
        if driver:
            filename = f"debug_timeout_ria_{url.split('/')[-1]}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.info(f"HTML-код проблемной страницы сохранен в '{filename}'")
        return None
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при работе Selenium: {e}", exc_info=True)
        return None
    finally:
        if driver:
            driver.quit()


# --- 3. ФУНКЦИИ-ПАРСЕРЫ ДЛЯ РИА НОВОСТИ ---


def find_ria_news_links() -> list[dict] | None:
    """
    Шаг 1: Находит заголовки и ссылки на первые 3 "чистые" новости на странице поиска.
    """
    logging.info(f"ШАГ 1: Поиск новостей на странице {RIA_SEARCH_URL}...")

    wait_selector = "div.list"  # Ждем появления контейнера со списком
    html_content = get_html_with_selenium(RIA_SEARCH_URL, wait_selector)

    if not html_content:
        return None

    try:
        soup = BeautifulSoup(html_content, "lxml")

        news_list = []
        all_items = soup.select("div.list > div.list-item")

        for item in all_items:
            # Проверяем, не авторская ли это колонка
            if item.find("div", class_="list-item__author"):
                logging.info("Пропущена авторская колонка.")
                continue

            link_tag = item.find("a", class_="list-item__title")
            if link_tag and link_tag.has_attr("href"):
                news_list.append(
                    {"title": link_tag.get_text(strip=True), "url": link_tag["href"]}
                )

            # Если мы уже набрали нужное количество новостей, выходим из цикла
            if len(news_list) >= NEWS_LIMIT:
                break

        if not news_list:
            logging.error("ШАГ 1 НЕУДАЧА: Не найдено ни одной подходящей новости.")
            return None

        logging.info(
            f"ШАГ 1 УСПЕХ: Найдено {len(news_list)} новостей для дальнейшей обработки."
        )
        return news_list

    except Exception as e:
        logging.error(
            f"ШАГ 1 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при парсинге страницы поиска. {e}"
        )
        return None


def fetch_ria_article_text(url: str) -> str:
    """
    Шаг 2: Извлекает полный текст со страницы статьи, следуя структуре article_block.
    """
    logging.info(f"ШАГ 2: Извлечение текста со страницы {url}...")

    # Ждем появления главного контейнера статьи
    wait_selector = "div.layout-article__main"
    html_content = get_html_with_selenium(url, wait_selector)

    if not html_content:
        return "Не удалось загрузить страницу статьи."

    try:
        soup = BeautifulSoup(html_content, "lxml")

        # 1. Находим главный контейнер статьи
        main_content = soup.select_one(wait_selector)
        if not main_content:
            logging.warning(
                f"Не найден главный контейнер '{wait_selector}' на странице {url}"
            )
            return "Главный контейнер статьи не найден."

        # 2. Внутри него ищем только блоки с текстом
        text_blocks = main_content.select('div.article_block[data-type="text"]')

        if not text_blocks:
            logging.warning(
                f"Не найдены текстовые блоки 'article_block[data-type=\"text\"]' на странице {url}"
            )
            # Попробуем старый метод как запасной вариант
            text_divs = main_content.find_all("div", class_="article__text")
            if not text_divs:
                return "Текстовые блоки на странице не найдены."
            full_text = " ".join([div.get_text(strip=True) for div in text_divs])
            return full_text

        # 3. Собираем текст из этих блоков
        all_paragraphs = []
        for block in text_blocks:
            # Внутри каждого блока может быть один или несколько div'ов с текстом
            text_divs = block.find_all("div", class_="article__text")
            for div in text_divs:
                all_paragraphs.append(div.get_text(strip=True))

        full_text = " ".join(all_paragraphs)
        logging.info(f"Текст статьи {url} успешно извлечен.")
        return full_text

    except Exception as e:
        logging.error(
            f"ШАГ 2 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при парсинге статьи {url}. {e}"
        )
        return f"Ошибка парсинга статьи: {e}"


# --- 4. ГЛАВНАЯ ФУНКЦИЯ-ОРКЕСТРАТОР ---


async def get_ria_news_async() -> dict:
    """
    Основная асинхронная функция, которая запускает и координирует весь процесс.
    """
    start_time = time.time()
    logging.info("--- ЗАПУСК ПАРСЕРА РИА НОВОСТИ ---")

    loop = asyncio.get_running_loop()

    # Шаг 1: Получаем список новостей (блокирующая операция, выполняем в отдельном потоке)
    news_links = await loop.run_in_executor(None, find_ria_news_links)

    if not news_links:
        return {"status": "failure", "error": "Не удалось найти ссылки на новости."}

    # Шаг 2: Параллельно загружаем полные тексты
    logging.info(f"ШАГ 3: Загрузка полных текстов для {len(news_links)} статей...")

    tasks = [
        loop.run_in_executor(None, fetch_ria_article_text, item["url"])
        for item in news_links
    ]
    full_texts = await asyncio.gather(*tasks)

    # Собираем финальный результат
    final_data = []
    for i, item in enumerate(news_links):
        final_data.append(
            {
                "title": item["title"],
                "full_article_url": item["url"],
                "full_text": full_texts[i],
            }
        )

    end_time = time.time()
    logging.info(
        f"--- ПАРСИНГ РИА НОВОСТИ УСПЕШНО ЗАВЕРШЕН (за {end_time - start_time:.2f} сек) ---"
    )

    return {"status": "success", "data": final_data}


# --- 5. БЛОК ДЛЯ ТЕСТИРОВАНИЯ ---

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    result = asyncio.run(get_ria_news_async())

    print("\n" + "=" * 50)
    print("--- РЕЗУЛТАТ РАБОТЫ СКРИПТА (РИА НОВОСТИ) ---")
    print("=" * 50 + "\n")

    if result.get("status") == "success":
        print(f"Статус: УСПЕХ\n")
        all_news = result.get("data", [])

        print("--- САММАРИ ДЛЯ ВЫВОДА ПОЛЬЗОВАТЕЛЮ (заголовки) ---")
        for i, news_item in enumerate(all_news):
            print(f"{i+1}. {news_item['title']}")

        print("\n\n--- ПОЛНАЯ СТРУКТУРА ДАННЫХ (для отладки) ---")
        print(json.dumps(all_news, ensure_ascii=False, indent=2))
    else:
        print(f"Статус: ОШИБКА\n")
        print(f"Описание ошибки: {result.get('error')}")
