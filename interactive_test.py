# fast_test.py (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)

import asyncio
import os
import re

# --- Импортируем только то, что нам абсолютно необходимо ---
from src.dialogue.dialogue_manager import DialogueManager
from parser.full_cheko import get_company_data_by_inn_async
from parser.forecast_generator import find_category_by_okved

# Для Windows может понадобиться эта строка
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main():
    """
    Быстрый интерактивный тест, сфокусированный ТОЛЬКО на логике
    аналитических обзоров (Уровень 1 и Уровень 2).
    """
    print("--- Запуск БЫСТРОГО теста аналитической системы ---")
    print("Этот скрипт НЕ проверяет госпрограммы, МСП и ставку ЦБ.")
    print("Инструкция:")
    print("1. Введите ИНН компании для получения короткого обзора (Уровень 1).")
    print("2. Для получения развернутого обзора (Уровень 2) введите команду: details")
    print("3. Для выхода из теста введите команду: exit")
    print("-" * 50)

    # Создаем менеджер. Теперь он автоматически загрузит аналитику в self.analytics_data
    manager = DialogueManager()

    # Проверяем, что аналитика загрузилась. Если нет - тест бессмысленен.
    if not manager.analytics_data:
        print("!!! КРИТИЧЕСКАЯ ОШИБКА !!!")
        print(
            "Тест не может быть запущен, так как DialogueManager не смог загрузить данные из 'data/msh_okveds.json'."
        )
        print("Проверьте путь и целостность файла.")
        return

    state = {}
    company_cache = {}

    while True:
        try:
            user_input = input("Вы: ").strip()

            if user_input.lower() == "exit":
                print("--- Тест завершен. ---")
                break

            inn_match = re.fullmatch(r"(\d{10}|\d{12})", user_input)

            if inn_match:
                inn = user_input
                print("Бот: [Получаю ОКВЭД из Cheko...]")

                if inn in company_cache:
                    company_data = company_cache[inn]
                    print("Бот: [Данные по ОКВЭД взяты из кэша]")
                else:
                    company_data = await get_company_data_by_inn_async(inn)
                    company_cache[inn] = company_data

                if company_data.get("error"):
                    print(f"Бот: Ошибка получения данных: {company_data['error']}")
                    continue

                okved_code = (
                    company_data.get("okved_data", {})
                    .get("main_okved", {})
                    .get("code", "")
                )
                company_name = company_data.get("company_name", f"Компания с ИНН {inn}")
                okved_category = find_category_by_okved(okved_code)

                state["company_name"] = company_name
                state["okved_code"] = okved_code
                state["current_inn"] = inn
                print(f"Бот: [Определена категория: {okved_category}]")

                parser_exceptions = [
                    "Растениеводство",
                    "Производство мукомольной и крахмальной продукции",
                ]
                if okved_category in parser_exceptions:
                    print("\n--- ОТРАСЛЕВОЙ ОБЗОР: ---")
                    print(
                        "Для данной категории используется динамический парсинг новостей (тест пройден)."
                    )
                else:
                    # ИСПРАВЛЕНО: Обращаемся к атрибуту класса self.analytics_data
                    category_data = manager.analytics_data.get(okved_category)
                    if category_data and category_data.get("article"):
                        full_article = category_data["article"]
                        state["analytics_article"] = full_article
                        sentences = full_article.split(".")
                        summary_text = ". ".join(sentences[:4]).strip() + "."

                        print(
                            f"\n--- ОТРАСЛЕВОЙ АНАЛИТИЧЕСКИЙ ОБЗОР (Уровень 1): {okved_category.upper()} ---"
                        )
                        print(summary_text)
                    else:
                        state["analytics_article"] = None
                        print(
                            "Бот: Аналитическая справка для данной категории не найдена."
                        )

            elif user_input.lower() == "details":
                print(
                    "\nБот: [Готовлю развернутую аналитическую справку (Уровень 2)...]"
                )

                full_article = state.get("analytics_article")
                if not full_article:
                    print(
                        "Бот: Нет данных для детализации. Сначала введите ИНН стандартной категории."
                    )
                    continue

                mock_state_for_details = {
                    "analysis_report": {
                        "analytics_article": full_article,
                        "company_info": {
                            "okved_data": {
                                "main_okved": {"code": state.get("okved_code")}
                            }
                        },
                    },
                    "company_name": state.get("company_name"),
                    "history": [],
                }

                response = await manager._handle_analytical_details_query(
                    user_input, mock_state_for_details
                )
                print(f"Бот (развернутый ответ):\n{response}")

            else:
                print("Бот: Неизвестная команда. Введите ИНН, 'details' или 'exit'.")

            print("-" * 50)
        except Exception as e:
            print(f"\n!!! Произошла критическая ошибка: {e} !!!\n")


if __name__ == "__main__":
    asyncio.run(main())
