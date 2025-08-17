# src/web_searcher.py (версия 3, с правильной обработкой ошибок и новыми селекторами)
import logging
import os
import random
import time
from playwright.async_api import async_playwright, Error as PlaywrightError
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MODULE_DIR = os.path.dirname(__file__)
USER_DATA_DIR = os.path.join(MODULE_DIR, "yandex_search_session_async")
HEADLESS_MODE = True
DEBUG_SCREENSHOT_DIR = os.path.join(MODULE_DIR, "debug_screenshots")
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)


async def search_links(query: str, max_results: int = 5) -> list[dict]:
    logger.info(f"Запущен АСИНХРОННЫЙ веб-поиск по запросу: '{query}'")
    
    # --- ИЗМЕНЕНИЕ 1: Выносим инициализацию за пределы try-блока ---
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=HEADLESS_MODE,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ],
            slow_mo=random.randint(50, 150)
        )
        page = await context.new_page()

        try:
            search_url = f"https://yandex.ru/search/?text={query.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=40000)

            # --- ИЗМЕНЕНИЕ 2: НОВЫЕ, БОЛЕЕ НАДЕЖНЫЕ СЕЛЕКТОРЫ ---
            # Яндекс сейчас часто использует ID 'search-result' для всего блока
            # или ul/ol с классом 'serp-list' для списка. Пробуем их.
            search_results_selector = "#search-result, ul.serp-list, ol.serp-list"
            captcha_selector = '.CheckboxCaptcha-Checkbox'
            
            logger.debug(f"Ожидаю появления одного из селекторов: {search_results_selector} или {captcha_selector}")
            
            await page.wait_for_selector(
                f"{search_results_selector}, {captcha_selector}",
                state="attached", # 'attached' сработает, даже если элемент еще не виден, но уже есть в DOM
                timeout=15000
            )

            # Проверка на капчу
            if await page.is_visible(captcha_selector):
                logger.error("!!! ОБНАРУЖЕНА КАПЧА ЯНДЕКСА !!!")
                # ... (код для скриншота капчи без изменений)
                return []

            logger.info("Блок с результатами поиска найден. Получаю HTML.")
            html_content = await page.content()
            
        except PlaywrightError as e:
            logger.error(f"Ошибка Playwright во время веб-поиска: {e}")
            logger.info("Делаю скриншот страницы для анализа...")
            try:
                timestamp = int(time.time())
                screenshot_path = os.path.join(DEBUG_SCREENSHOT_DIR, f"playwright_error_{timestamp}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Скриншот страницы сохранен в: {screenshot_path}")
            except Exception as se:
                logger.error(f"Не удалось сделать скриншот при ошибке: {se}")
            
            # Возвращаем пустой список, но не падаем
            html_content = None

        finally:
            # Закрываем контекст здесь, после всех действий
            await context.close()

    if not html_content:
        logger.warning(f"Не удалось получить HTML-контент для запроса '{query}'.")
        return []

    # --- ИЗМЕНЕНИЕ 3: ОБНОВЛЕННЫЕ СЕЛЕКТОРЫ ДЛЯ ПАРСИНГА BS4 ---
    soup = BeautifulSoup(html_content, "lxml")
    results = []
    
    # Ищем карточки по классу, который используется сейчас
    result_cards = soup.select('li.serp-item') 
    
    if not result_cards:
        logger.warning("Не найдено карточек с результатами (li.serp-item). Структура страницы могла измениться.")
    
    for card in result_cards:
        if len(results) >= max_results:
            break

        # Пропускаем рекламу
        if card.select_one('[data-type="ad"]') or "yabs.yandex.ru" in str(card):
            continue

        # Селекторы для заголовка и ссылки тоже обновляем
        title_tag = card.select_one('h2 a, .organic__title-wrapper a')
        link_tag = card.select_one('h2 a, .organic__title-wrapper a')
        
        if title_tag and link_tag and link_tag.has_attr('href'):
            title = title_tag.get_text(strip=True)
            link = link_tag['href']
            
            if title and link.startswith("http"):
                results.append({"title": title, "link": link})

    logger.info(f"Парсинг Яндекса завершен. Извлечено {len(results)} ссылок.")
    if not results and html_content:
         logger.warning("HTML получен, но не удалось извлечь ссылки. Проверьте селекторы для парсинга BS4.")
         
    return results