import asyncio
import logging
import sys
import os
from typing import Dict, List
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from langchain_core.messages import SystemMessage, HumanMessage
import re
import json

# Динамическое добавление пути к src
# Убедитесь, что путь до папки src указан корректно
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Предполагается, что ваш класс GigaChatNLU находится в src/nlu/
# Если это не так, скорректируйте путь
from src.nlu.gigachat_client import GigaChatNLU

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# URL-адреса для парсинга
URLS = [
    "https://www.consultant.ru/document/cons_doc_LAW_52144/08b3ecbcdc9a360ad1dc314150a6328886703356/",  # URL с данными о численности
    "https://www.consultant.ru/document/cons_doc_LAW_196415/#dst100005",  # URL с данными о доходах
]


async def _get_interactive_text_from_url(url: str) -> str:
    """Извлекает и очищает текстовое содержимое со страницы."""
    logger.info(f"Начало извлечения текста с: {url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(
                2000
            )  # Даем время на прогрузку динамического контента
            html_content = await page.content()
            await context.close()

        soup = BeautifulSoup(html_content, "lxml")
        for element in soup(
            ["script", "style", "header", "footer", "nav", "aside", "form", "button"]
        ):
            element.decompose()

        text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
        logger.info(f"Извлечен текст с {url}, длина: {len(text)} символов")
        return text
    except Exception as e:
        logger.error(f"Ошибка при извлечении с {url}: {e}")
        return ""


async def extract_comparison_data(
    gigachat_instance: GigaChatNLU, urls: List[str]
) -> Dict[str, Dict[str, str]]:
    """Извлекает текст с нескольких URL, объединяет его и анализирует с помощью GigaChat."""
    full_text = ""
    # Асинхронно получаем текст с каждого URL
    tasks = [_get_interactive_text_from_url(url) for url in urls]
    texts = await asyncio.gather(*tasks)

    for text in texts:
        if text:
            full_text += text + "\n\n"

    if not full_text:
        logger.error("Не удалось получить текст ни с одной из страниц.")
        return {}

    logger.info("Передача объединенного текста в GigaChat для анализа.")
    system_prompt = (
        "Ты — внимательный ассистент по анализу нормативных документов. Твоя задача — извлечь из текста критерии для "
        "субъектов малого и среднего предпринимательства. Найди и структурируй данные по двум параметрам: "
        "1. Среднесписочная численность сотрудников ('staff_count'). "
        "2. Предельные значения дохода за год ('revenue'). "
        "Категории: 'Микропредприятие', 'Малое предприятие', 'Среднее предприятие'. "
        "Ответ должен быть строго в формате JSON с ключами 'staff_count' и 'revenue'. "
        "В значениях должны быть словари с категориями и их критериями. Обязательно указывай единицы измерения (человек, млн. рублей, млрд. рублей). "
        "Пример: {'staff_count': {'Микропредприятие': 'до 15 человек'}, 'revenue': {'Микропредприятие': '120 млн. рублей', 'Малое предприятие': '800 млн. рублей', 'Среднее предприятие': '2 млрд. рублей'}}. "
        "Если какие-то данные отсутствуют, оставь соответствующий словарь пустым."
    )

    # ИСПРАВЛЕНИЕ: Убираем обрезку текста. Теперь вся информация передается модели.
    user_prompt = f"Извлеки данные из следующего текста:\n{full_text}"

    try:
        client = gigachat_instance._get_client("extraction")
        logger.info("Вызов GigaChat для обработки текста.")
        response = await asyncio.to_thread(
            client.invoke,
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        )
        response_content = response.content.strip()
        logger.info(f"Ответ GigaChat: {response_content}")

        json_match = re.search(r"\{[\s\S]*\}", response_content)
        if json_match:
            json_string = json_match.group(0)
            # Заменяем одинарные кавычки на двойные для совместимости с JSON
            data = json.loads(json_string.replace("'", '"'))
            logger.info(f"GigaChat успешно извлек данные: {data}")
            return data
        else:
            logger.warning("GigaChat не вернул данные в формате JSON.")
            return {}
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON из ответа GigaChat: {e}")
        logger.error(f"Строка, вызвавшая ошибку: {response_content}")
        return {}
    except Exception as e:
        logger.error(f"Ошибка при вызове GigaChat: {e}")
        return {}


async def main():
    gigachat = GigaChatNLU()
    # Передаем список URL в функцию
    comparison_data = await extract_comparison_data(gigachat, URLS)

    if comparison_data:
        print("\nДанные для сравнения (обработаны GigaChat):")
        for category, details in comparison_data.items():
            print(f"\n{category}:")
            if isinstance(details, dict):
                for key, value in details.items():
                    print(f"  {key}: {value}")
            else:
                print(f"  {details}")
    else:
        print("\nНе удалось извлечь данные для сравнения.")


if __name__ == "__main__":
    # Для Windows может потребоваться следующая строка, если возникают проблемы с asyncio
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
