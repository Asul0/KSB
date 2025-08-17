import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
import asyncio
import json
import time
import os

# --- НОВЫЕ ИМПОРТЫ ДЛЯ SELENIUM ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


# --- 1. НАСТРОЙКИ ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("webdriver_manager").setLevel(logging.WARNING)

BASE_URL = "https://www.agroinvestor.ru"
ARCHIVE_URL = urljoin(BASE_URL, "/archive/")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ HTML ЧЕРЕЗ SELENIUM ---
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

    # Пока оставляем закомментированным для отладки
    # options.add_argument("--headless=new")

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

        # "УМНОЕ" ОЖИДАНИЕ (до 30 секунд)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
        )

        # Дополнительная пауза для полной "отрисовки"
        time.sleep(2)

        logging.info("Ключевой элемент найден. Ожидание завершено, получаем HTML-код.")
        return driver.page_source

    except TimeoutException:
        logging.error(f"Тайм-аут: не удалось дождаться элемента '{wait_for_selector}'.")
        if driver:
            filename = f"debug_timeout_{url.split('/')[-2]}.html"
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


def find_latest_digest_url() -> str | None:
    """
    Шаг 1: Находит URL последней подборки 'Самое интересное'.
    """
    logging.info(f"ШАГ 1: Поиск последней подборки на странице {ARCHIVE_URL}...")

    # Указываем, какой элемент ждать на странице архива
    wait_selector = "div.news-list"
    html_content = get_html_with_selenium(ARCHIVE_URL, wait_selector)

    if not html_content:
        return None

    try:
        soup = BeautifulSoup(html_content, "lxml")
        link_selector = "div.news-list .news__item:first-child a.news__item-img"
        link_tag = soup.select_one(link_selector)

        if not link_tag or not link_tag.has_attr("href"):
            logging.error(
                f"Элемент '{link_selector}' не найден, хотя контейнер '{wait_selector}' был."
            )
            return None

        digest_url = urljoin(BASE_URL, link_tag["href"])
        logging.info(f"ШАГ 1 УСПЕХ: Найдена ссылка на подборку: {digest_url}")
        return digest_url

    except Exception as e:
        logging.error(
            f"ШАГ 1 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при парсинге HTML. Ошибка: {e}"
        )
        return None


def parse_digest_page(digest_url: str) -> list[dict] | None:
    """
    Шаг 2: Парсит страницу подборки, собирая заголовки, краткие описания и ссылки.
    (ФИНАЛЬНАЯ ВЕРСИЯ с гибким поиском ссылки)
    """
    logging.info(f"ШАГ 2: Сбор данных со страницы подборки {digest_url}...")

    wait_selector = "div.article__body h2"
    html_content = get_html_with_selenium(digest_url, wait_selector)

    if not html_content:
        return None

    try:
        soup = BeautifulSoup(html_content, "lxml")
        article_body = soup.find("div", class_="article__body")

        if not article_body:
            logging.error("ШАГ 2 НЕУДАЧА: Не найден контейнер 'article__body'.")
            return None

        all_h2s = article_body.find_all("h2")
        if not all_h2s:
            logging.error(
                "Критическая ошибка: контейнер 'article__body' найден, но он ПУСТ."
            )
            return None

        news_items = []
        for h2 in all_h2s:
            title = h2.get_text(strip=True)
            summary_p = h2.find_next_sibling("p")

            # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
            # Ищем не непосредственного соседа, а первый тег 'a' после тега 'p'.
            # Это игнорирует любые <br> и другие теги между ними.
            link_a = summary_p.find_next("a") if summary_p else None
            # ----------------------------

            if title and summary_p and link_a and link_a.has_attr("href"):
                news_items.append(
                    {
                        "title": title,
                        "summary": summary_p.get_text(strip=True),
                        "full_article_url": urljoin(BASE_URL, link_a["href"]),
                        "full_text": None,
                    }
                )
            else:
                # Добавим лог, чтобы понять, что именно пошло не так для конкретной новости
                logging.warning(
                    f"Не удалось полностью разобрать новость с заголовком '{title[:50]}...'. Пропускаем."
                )

        if not news_items:
            logging.error(
                "ШАГ 2 КРИТИЧЕСКАЯ ОШИБКА: Не удалось собрать ни одной полной новости. Проверьте структуру HTML."
            )
            with open("debug_digest_page_final.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify())
            logging.info(
                "HTML-код финальной неудачной попытки сохранен в 'debug_digest_page_final.html'"
            )
            return []

        logging.info(f"ШАГ 2 УСПЕХ: Собрана информация по {len(news_items)} новостям.")
        return news_items

    except Exception as e:
        logging.error(
            f"ШАГ 2 КРИТИЧЕСКАЯ ОШИБКА: Ошибка при парсинге страницы подборки. Ошибка: {e}"
        )
        return None


async def fetch_full_article_text(session, url: str) -> str:
    """
    Асинхронно загружает и парсит полный текст ОДНОЙ СТАТЬИ.
    Игнорирует страницы, не являющиеся статьями (например, карточки компаний).
    """
    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Проверяем, что это ссылка на новость ---
    if "/news/" not in url:
        logging.info(f"Пропускаем URL (не является новостью): {url}")
        return "Это ссылка на карточку компании или другой раздел, а не на статью."
    # -------------------------------------------------------------

    try:
        logging.info(f"Загружаю полный текст статьи: {url}")
        async with session.get(url, headers=HEADERS, timeout=30) as response:
            response.raise_for_status()
            html = await response.text()
            soup = BeautifulSoup(html, "lxml")

            article_body = soup.find("div", class_="article__body")
            if not article_body:
                logging.warning(f"Не найден 'article__body' на странице статьи {url}")
                return "Контейнер с текстом статьи не найден."

            paragraphs = article_body.find_all("p")
            full_text = " ".join([p.get_text(strip=True) for p in paragraphs])
            return full_text

    except Exception as e:
        logging.error(f"Ошибка при загрузке статьи {url}: {e}")
        return f"Ошибка загрузки: {e}"


# --- 3. ГЛАВНАЯ ФУНКЦИЯ-ОРКЕСТРАТОР ---


async def get_latest_agro_news() -> dict:
    """
    Основная функция, которая запускает и координирует весь процесс парсинга.
    """
    start_time = time.time()
    logging.info("--- ЗАПУСК ПАРСЕРА НОВОСТЕЙ AGROINVESTOR ---")

    digest_url = find_latest_digest_url()
    if not digest_url:
        return {"status": "failure", "error": "Не удалось найти URL подборки."}

    news_list = parse_digest_page(digest_url)
    if news_list is None:
        return {"status": "failure", "error": "Не удалось спарсить страницу подборки."}

    if not news_list:
        logging.info("--- ЗАВЕРШЕНИЕ: Новости для обработки не найдены. ---")
        return {"status": "success", "data": [], "message": "Подборка пуста."}

    logging.info(f"ШАГ 3: Загрузка полных текстов для {len(news_list)} статей...")

    try:
        import aiohttp
    except ImportError:
        logging.error(
            "Для асинхронной работы требуется библиотека aiohttp. Установите ее: pip install aiohttp"
        )
        return {"status": "failure", "error": "Отсутствует aiohttp."}

    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_full_article_text(session, item["full_article_url"])
            for item in news_list
        ]
        full_texts = await asyncio.gather(*tasks, return_exceptions=True)

    for i, text in enumerate(full_texts):
        if isinstance(text, Exception):
            news_list[i]["full_text"] = f"Ошибка при загрузке: {text}"
            logging.error(
                f"Не удалось загрузить статью {news_list[i]['full_article_url']}: {text}"
            )
        else:
            news_list[i]["full_text"] = text

    logging.info("ШАГ 3 УСПЕХ: Все тексты статей обработаны.")

    end_time = time.time()
    logging.info(
        f"--- ПАРСИНГ НОВОСТЕЙ УСПЕШНО ЗАВЕРШЕН (за {end_time - start_time:.2f} сек) ---"
    )

    return {"status": "success", "data": news_list}


# --- 4. БЛОК ДЛЯ ТЕСТИРОВАНИЯ ---

if __name__ == "__main__":
    if asyncio.get_event_loop().is_running():
        pass
    else:
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    result = asyncio.run(get_latest_agro_news())

    print("\n" + "=" * 50)
    print("--- РЕЗУЛЬТАТ РАБОТЫ СКРИПТА ---")
    print("=" * 50 + "\n")

    if result.get("status") == "success":
        print(f"Статус: УСПЕХ\n")
        all_news = result.get("data", [])

        print("--- САММАРИ ДЛЯ ВЫВОДА ПОЛЬЗОВАТЕЛЮ (первые 3 заголовка) ---")
        for i, news_item in enumerate(all_news[:3]):
            print(f"{i+1}. {news_item['title']}")

        print("\n\n--- ПОЛНАЯ СТРУКТУРА ДАННЫХ (для отладки) ---")
        print(json.dumps(all_news, ensure_ascii=False, indent=2))
    else:
        print(f"Статус: ОШИБКА\n")
        print(f"Описание ошибки: {result.get('error')}")
