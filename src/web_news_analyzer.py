# src/web_news_analyzer.py
import logging
import asyncio
from typing import Dict, Any, List, Tuple
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re
import json
from langchain_core.messages import SystemMessage, HumanMessage

# Эти импорты остаются, так как они нужны для поиска и анализа новостей
from src.web_searcher import search_links
from src.nlu.gigachat_client import GigaChatNLU

logger = logging.getLogger(__name__)

GIGACHAT_BLACKLIST_MARKER = "временно ограничены"
MAX_ANALYSIS_ATTEMPTS = 3
# Этот список доменов нужен для фильтрации нерелевантных новостных источников
BAD_NEWS_DOMAINS = [
    "che-cko.ru",
    "companies.rbc.ru",
    "telegram.im",
    "list-org.com",
    "audit-it.ru",
    "rusprofile.ru",
    "sbis.ru",
    "basis.myseldon.com" # Убираем агрегаторы, чтобы получать первоисточники
]


async def _get_interactive_text_from_url(url: str) -> str:
    """
    (Без изменений)
    Вспомогательная функция для асинхронного извлечения текста со страницы.
    """
    logger.info(f"Интерактивное извлечение текста с: {url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                ignore_https_errors=True  # <-- ВОТ ЭТА СТРОКА
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(1500)
            html_content = await page.content()
            await context.close()
        if "пожалуйста, подтвердите, что вы человек" in html_content.lower():
            return ""
        soup = BeautifulSoup(html_content, "lxml")
        for element in soup(
            ["script", "style", "header", "footer", "nav", "aside", "form", "button"]
        ):
            element.decompose()
        return soup.body.get_text(separator="\n", strip=True) if soup.body else ""
    except Exception as e:
        logger.error(f"Критическая ошибка при извлечении с {url}: {e}")
        return ""


async def _search_and_scrape_news(okved_description: str, attempt_number: int) -> Tuple[str, List[Dict[str, str]]]:
    if not okved_description:
        logger.warning("ОКВЭД не предоставлен, поиск новостей по отрасли невозможен.")
        return "", []

    logger.info(f"Поиск отраслевой аналитики (попытка {attempt_number}): '{okved_description}'")

    search_queries = []
    if attempt_number == 1:
        # Основные, глубокие запросы
        search_queries = [
            f'анализ рынка "{okved_description}" Россия: ключевые показатели, проблемы и перспективы начиная с 2025 года',
            f'ключевые тренды и прогноз развития отрасли "{okved_description}" до 2030',
            f'цифровизация, импортозамещение и инновации в отрасли "{okved_description}" кейсы и решения'
        ]
    elif attempt_number == 2:
        # Альтернативные, более общие запросы
        search_queries = [
            f'обзор отрасли "{okved_description}" в РФ новости 2025',
            f'статистика и показатели "{okved_description}" Россия 2025-2026',
            f'государственная поддержка отрасли "{okved_description} 2025-2026"'
        ]
    else: # attempt_number >= 3
        # Запросы "последней надежды", максимально нейтральные
        search_queries = [
            f'перспективы развития "{okved_description}" в текущих условиях 2025',
            f'драйверы роста "{okved_description}" 2025',
            f'рынок "{okved_description}" события 2025-2026'
        ]

    all_links = {}
    for query in search_queries:
        links = await search_links(query, max_results=2)
        for item in links:
            if any(bad_domain in item["link"] for bad_domain in BAD_NEWS_DOMAINS):
                continue
            all_links[item["link"]] = item["title"]

    if not all_links:
        return "", []

    tasks = [_get_interactive_text_from_url(link) for link in all_links.keys()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scraped_texts, source_info = [], []
    link_list = list(all_links.keys())

    for i, res in enumerate(results):
        if not isinstance(res, Exception) and res and len(res) > 300:
            current_link = link_list[i]
            scraped_texts.append(f"--- Статья со страницы {current_link} ---\n{res[:3500]}")
            source_info.append({"url": current_link, "title": all_links[current_link]})

    logger.info(f"Успешно собрано {len(scraped_texts)} аналитических статей из {len(source_info)} источников.")
    return "\n\n".join(scraped_texts), source_info

# <<< НОВАЯ ГЛАВНАЯ ФУНКЦИЯ, КОТОРУЮ ИЩЕТ DIALOGUE_MANAGER >>>
async def get_news_analysis_for_company(
    company_name: str, 
    inn: str, 
    okved_description: str,
    gigachat_instance: GigaChatNLU
) -> Dict[str, Any]:
    logger.info(f"Запущен анализ отраслевой аналитики для: '{company_name}' (ОКВЭД: {okved_description})")

    system_prompt = (
        "Ты — старший отраслевой аналитик. Твоя задача — извлечь из большого текста ключевые рыночные сигналы, тенденции и факты. "
        "Ты должен игнорировать поверхностную и нерелевантную информацию. "
        "Отвечай строго в формате JSON без каких-либо пояснений."
    )
    
    last_error = None
    source_urls = []

    for attempt in range(1, MAX_ANALYSIS_ATTEMPTS + 1):
        logger.info(f"Анализ отраслевой аналитики. Попытка {attempt}/{MAX_ANALYSIS_ATTEMPTS}")
        
        news_context_text, news_sources_info = await _search_and_scrape_news(okved_description, attempt_number=attempt)
        source_urls = [source['url'] for source in news_sources_info]

        if not news_context_text:
            logger.warning(f"На попытке {attempt} не найдено статей для анализа. Пробуем другие запросы.")
            last_error = "Не удалось найти релевантные статьи в открытых источниках."
            await asyncio.sleep(1) # Небольшая пауза перед следующей попыткой
            continue

        user_prompt = (
            f"Проанализируй текст по отрасли «{okved_description}». Извлеки 3-4 самых значимых рыночных тренда или факта.\n\n"
            "**Что нужно найти и отразить в выжимке (summary):**\n"
            "*   **Конкретные факты:** Изменения в законодательстве, запуск новых технологий, динамика цен на сырье или продукцию, важные статистические данные.\n"
            "*   **Ключевые вызовы и возможности:** Проблемы, с которыми сталкивается отрасль (логистика, кадры), или новые рыночные ниши.\n"
            "*   **Прогнозы экспертов:** Мнения аналитиков о будущем рынка.\n\n"
            "**ЧЕГО СЛЕДУЕТ ИЗБЕГАТЬ:**\n"
            "*   **Новостей о мелких компаниях:** Не включай новости об открытии или деятельности отдельных, не системообразующих компаний. Нас интересует рынок в целом.\n"
            "*   **Общих фраз:** Избегай неинформативных формулировок типа 'обсуждаются вопросы'. Укажи, *какие* выводы были сделаны.\n"
            "*   **Пересказа регистрационных данных:** Информация о том, что какая-то компания была основана в определенную дату, не является отраслевой аналитикой. Не включай это.\n\n"
            "Для каждого найденного тренда или факта:\n"
            "1.  Придумай информативный заголовок (ключ 'title').\n"
            "2.  Сделай конкретную и полезную выжимку (ключ 'summary').\n\n"
            "Верни результат в виде JSON-объекта с ключом 'top_news', который содержит массив этих новостей. "
            "Критически важно, чтобы в каждом JSON-объекте не было повторяющихся ключей.\n\n"
            "--- ТЕКСТ ДЛЯ АНАЛИЗА ---\n"
            f"{news_context_text}"
        )

        try:
            client = gigachat_instance._get_client("extraction")
            response = await asyncio.to_thread(
                client.invoke,
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
            )
            response_content = response.content.strip()
            logger.info(f"GigaChat (попытка {attempt}) вернул: {response_content[:300]}...")

            # ЯВНАЯ ПРОВЕРКА НА BLACKLIST
            if GIGACHAT_BLACKLIST_MARKER in response_content:
                logger.warning(f"GigaChat вернул ответ из 'blacklist' на попытке {attempt}. Пробуем снова с другими источниками.")
                last_error = "Анализ был заблокирован контент-фильтром нейросети."
                continue # Переходим к следующей итерации цикла

            json_match = re.search(r"\{[\s\S]*\}", response_content)
            if json_match:
                analysis_result = json.loads(json_match.group(0))
                final_news = analysis_result.get("top_news", [])
                
                # Проверка, что результат не пустой и осмысленный
                if not final_news:
                    logger.warning(f"GigaChat вернул пустой список новостей на попытке {attempt}. Пробуем снова.")
                    last_error = "Нейросеть не смогла извлечь значимые факты из найденных статей."
                    continue

                for i, news_item in enumerate(final_news):
                    news_item["source_url"] = news_sources_info[i]["url"] if i < len(news_sources_info) else "Источник не определен"
                
                analysis_result["top_news"] = final_news
                analysis_result["source_urls"] = source_urls
                logger.info("Анализ новостей от GigaChat успешно получен и обработан.")
                return analysis_result # <<< УСПЕХ! ВЫХОДИМ ИЗ ЦИКЛА И ФУНКЦИИ
            else:
                last_error = "GigaChat не вернул ответ в формате JSON."
                logger.warning(f"{last_error} на попытке {attempt}. Пробуем снова.")
                continue

        except Exception as e:
            logger.error(f"Критическая ошибка при анализе новостей на попытке {attempt}: {e}", exc_info=True)
            last_error = f"Внутренняя ошибка при обращении к сервису аналитики: {e}"
            # При критической ошибке можно прервать цикл раньше
            break
    
    # <<< ЭТОТ БЛОК ВЫПОЛНИТСЯ, ЕСЛИ ВСЕ ПОПЫТКИ В ЦИКЛЕ ПРОВАЛИЛИСЬ >>>
    logger.error(f"Не удалось получить анализ новостей после {MAX_ANALYSIS_ATTEMPTS} попыток. Последняя ошибка: {last_error}")
    return {
        "top_news": [],
        "summary": f"Не удалось автоматически проанализировать новостной фон. Причина: {last_error}",
        "source_urls": source_urls,
    }