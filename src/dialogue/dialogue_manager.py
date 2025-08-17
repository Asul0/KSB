# src/dialogue/dialogue_manager.py (ФИНАЛЬНАЯ ВЕРСИЯ С ПОЛНОЙ ПАМЯТЬЮ)

import logging
from typing import Dict, Any, List
import asyncio
import re
import json
from src.nlu.gigachat_client import GigaChatNLU
from src.tools.msh_limits_tool import get_msh_limits_data
from parser.agro_news_parser import get_latest_agro_news
from parser.ria_news_parser import get_ria_news_async
from parser.forecast_generator import generate_price_forecast
from program.mskh import _get_company_region, CREDIT_LIMITS_DATA

# ===============================================

from src.nlu.gigachat_client import GigaChatNLU
from src.web_news_analyzer import get_news_analysis_for_company
from src.tools.state_program_analyzer import run_state_programs_check

# Импортируем парсер из full_cheko.py (как вы и просили, без переименования)
from parser.full_cheko import get_company_data_by_inn_async

from src.config import settings
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class DialogueManager:
    def __init__(self):
        self.giga_nlu = GigaChatNLU()
        self.user_states: Dict[str, Dict[str, Any]] = {}
        # ... RAG и другая инициализация ...

    async def _handle_news_details_query(
        self, user_text: str, state: Dict[str, Any], entities: Dict[str, Any]
    ) -> str:
        logger.info(f"Обработка запроса на детализацию новости. Сущности: {entities}")

        full_report = state.get("analysis_report", {})
        source_identifier = entities.get("news_source", "").lower()
        query_text = entities.get("news_identifier", "").lower()

        target_news_list = []
        # <<< ИЗМЕНЕНИЕ: Улучшенная логика поиска >>>
        # Если в запросе есть "риа" или "агро", ищем только там. Иначе - везде.
        if "агро" in source_identifier or (
            "агро" in query_text and not source_identifier
        ):
            target_news_list = full_report.get("agroinvestor_news", [])
        elif "риа" in source_identifier or (
            "риа" in query_text and not source_identifier
        ):
            target_news_list = full_report.get("ria_news_forecast", [])
        else:  # Если источник не указан и не упоминается в тексте, ищем по всему
            target_news_list = full_report.get(
                "agroinvestor_news", []
            ) + full_report.get("ria_news_forecast", [])

        found_news = None
        # Ищем по ключевым словам из запроса в заголовке
        for news in target_news_list:
            # Проверяем, что все слова из запроса есть в заголовке
            if all(
                word in news.get("title", "").lower() for word in query_text.split()
            ):
                found_news = news
                break

        if not found_news:
            # Если не нашли по словам, попробуем найти по примерному совпадению
            for news in target_news_list:
                if query_text in news.get("title", "").lower():
                    found_news = news
                    break

        if (
            not found_news
            or not found_news.get("full_text")
            or "не на статью" in found_news.get("full_text")
        ):
            return "К сожалению, не удалось найти подробный текст для этой новости или это была ссылка на раздел сайта."

        # <<< ИЗМЕНЕНИЕ: Новый, более детальный промпт для LLM >>>
        system_prompt = (
            "Ты — ассистент-аналитик. Твоя задача — внимательно прочитать текст новостной статьи "
            "и подготовить подробную, структурированную сводку на русском языке. Ответ должен быть информативным."
        )

        user_prompt = (
            f"Вот текст статьи под заголовком «{found_news.get('title')}»:\n\n"
            f"```text\n{found_news['full_text']}\n```\n\n"
            f"**Задание:** Подготовь развернутый пересказ статьи, выделив 2-4 основных тезиса или ключевых факта. "
            f"Ответ должен быть содержательным и подробным, а не состоять из одного предложения. "
            f"Если в статье есть важные цифры (проценты, суммы, объемы тонн), обязательно включи их в ответ. "
            f"Изложи информацию в виде связного текста."
        )

        try:
            client = self.giga_nlu._get_client("formatting")
            response = await asyncio.to_thread(
                client.invoke,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
            )
            response_text = response.content.strip()
            # Добавляем ответ в историю
            state["history"].append({"role": "user", "content": user_text})
            state["history"].append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            logger.error(
                f"Ошибка при генерации ответа о деталях новости: {e}", exc_info=True
            )
            return "Произошла ошибка при обработке вашего запроса."

    def get_or_create_state(self, user_id: str) -> Dict[str, Any]:
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "current_inn": None,
                "company_name": None,
                "analysis_report": None,
                "history": [],
            }
        return self.user_states[user_id]

        # <<< ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ПОЛНОСТЬЮ >>>

    async def _run_full_company_analysis(self, inn: str, state: Dict[str, Any]) -> str:
        logger.info(f"Запускаю НОВЫЙ КОМПЛЕКСНЫЙ анализ для ИНН {inn}.")

        # --- ШАГ 0: Получение базовой информации о компании ---
        company_data = await get_company_data_by_inn_async(inn)
        if company_data.get("error"):
            return f"Не удалось получить данные для компании с ИНН {inn}. Причина: {company_data['error']}"

        company_name = company_data.get("company_name", f"Компания с ИНН {inn}")

        address = company_data.get("general_info", {}).get("address", "")
        company_region = _get_company_region(address)
        state["company_region"] = company_region
        logger.info(f"Для ИНН {inn} определен и сохранен регион: {company_region}")

        main_okved_info = company_data.get("okved_data", {}).get("main_okved", {})
        okved_code = main_okved_info.get("code", "Не определен")

        # --- ШАГ 1-3: Параллельный запуск всех асинхронных инструментов ---
        logger.info("Запускаю параллельный сбор данных из всех источников...")

        # Создаем задачи для асинхронного выполнения
        task_agroinvestor = asyncio.create_task(get_latest_agro_news())
        task_ria_news = asyncio.create_task(get_ria_news_async())

        # <<< ИСПРАВЛЕНИЕ ЗДЕСЬ: Возвращаем вызов к оригинальному виду (1 аргумент вместо 2) >>>
        task_programs = asyncio.create_task(run_state_programs_check(inn))

        # Ожидаем завершения всех асинхронных задач
        agroinvestor_report, ria_news_report, programs_report = await asyncio.gather(
            task_agroinvestor, task_ria_news, task_programs
        )

        # Синхронный вызов генератора прогнозов
        price_forecast_summary = generate_price_forecast(okved_code)
        from parser.forecast_generator import find_category_by_okved

        okved_category = find_category_by_okved(okved_code)

        # --- ШАГ 4: Сохранение полного отчета в "память" ассистента ---
        full_report = {
            "company_info": company_data,
            "agroinvestor_news": agroinvestor_report.get("data", []),
            "ria_news_forecast": ria_news_report.get("data", []),
            "price_forecast_summary": price_forecast_summary,
            "programs_analysis": programs_report,
        }
        state["current_inn"] = inn
        state["company_name"] = company_name
        state["analysis_report"] = full_report
        state["history"] = []

        # --- ШАГ 5: Формирование отчета для пользователя (остается без изменений) ---
        response_parts = [
            f"✅ **Комплексный анализ для «{company_name}» (ИНН: {inn})**\n"
        ]

        # --- Блок 1: Агроинвестор (выводится всегда) ---
        response_parts.append(
            "--- **1. САМОЕ ИНТЕРЕСНОЕ В АПК ЗА ПОСЛЕДНЕЕ ВРЕМЯ (Агроинвестор)** ---"
        )
        agro_news = agroinvestor_report.get("data", [])
        if agroinvestor_report.get("status") == "success" and agro_news:
            for news_item in agro_news[:3]:  # Берем первые 3
                response_parts.append(f"📰 {news_item.get('title', 'Без заголовка')}")
            # Добавляем общую ссылку на подборку
            if agro_news[0].get("summary"):  # Хитрый способ найти ссылку на подборку
                source_link = agro_news[0]["full_article_url"].split("/news/")[0]
                response_parts.append(f"\n   **Источник подборки:** {source_link}")
        else:
            response_parts.append(
                "Не удалось получить свежие новости от 'Агроинвестора'."
            )

        # --- Блок 2: Прогноз урожая от РИА Новости (выводится по условию) ---
        trigger_categories = [
            "Растениеводство",
            "Производство мукомольной и крахмальной продукции",
        ]
        if okved_category in trigger_categories:
            response_parts.append(
                "\n\n--- **2. АКТУАЛЬНЫЕ НОВОСТИ ПО ПРОГНОЗУ УРОЖАЯ (РИА Новости)** ---"
            )
            ria_news = ria_news_report.get("data", [])
            if ria_news_report.get("status") == "success" and ria_news:
                for news_item in ria_news:
                    response_parts.append(
                        f"📰 **{news_item.get('title', 'Без заголовка')}**"
                    )
                    response_parts.append(
                        f"   **Источник:** {news_item.get('full_article_url', 'Не указан')}"
                    )
            else:
                response_parts.append("Не удалось получить новости по прогнозу урожая.")

        # --- Блок 3: Прогноз цен (выводится, если был сгенерирован) ---
        if price_forecast_summary and "не найдена" not in price_forecast_summary:
            response_parts.append("\n\n--- **3. ОТРАСЛЕВОЙ ПРОГНОЗ ЦЕН** ---")
            response_parts.append(price_forecast_summary)

        # --- Блок 4: Госпрограммы (логика остается прежней) ---
        response_parts.append("\n\n--- **4. АНАЛИЗ ПО ГОСПРОГРАММАМ** ---\n")
        if programs_report.get("passed"):
            response_parts.append("**✅ ПРЕДВАРИТЕЛЬНО ПРОХОДИТ:**")
            # ... (здесь и далее код блока госпрограмм остается без изменений, как в вашем файле) ...
            # Я его сокращу для краткости, но у вас он должен остаться полным
            for p in programs_report["passed"]:
                response_parts.append(
                    f"\n➡️ **Программа:** {p.get('program_name', 'Без названия')}"
                )
                conditions_text = p.get("calculated_conditions") or p.get(
                    "base_conditions", "Нет информации об условиях."
                )
                response_parts.append(f"   **Условия:** {conditions_text}")
        if programs_report.get("fixable"):
            response_parts.append("\n**⚠️ ТРЕБУЮТ КОРРЕКТИРОВКИ:**")
            for p in programs_report["fixable"]:
                response_parts.append(
                    f"\n➡️ **Программа:** {p.get('program_name', 'Без названия')}"
                )
                response_parts.append(
                    f"   **РЕКОМЕНДАЦИЯ:** {p.get('recommendation', 'Нет данных.')}"
                )
        if programs_report.get("failed"):
            response_parts.append("\n**❌ НЕ ПРОХОДИТ:**")
            for p in programs_report["failed"]:
                response_parts.append(
                    f"\n➡️ **Программа:** {p.get('program_name', 'Без названия')}"
                )
                response_parts.append(
                    f"   **Причина отказа:** {p.get('reason', 'Нет данных.')}"
                )
        if not any(
            val
            for key, val in programs_report.items()
            if key in ["passed", "fixable", "failed"]
        ):
            response_parts.append(
                "Не найдено подходящих госпрограмм или произошла ошибка при проверке."
            )

        # --- Финальная фраза ---
        response_parts.append(
            "\n\n---\nЯ проанализировал всю доступную информацию. **Вы можете задать любой уточняющий вопрос** по деталям отчета."
        )

        final_response = "\n".join(response_parts)
        state["history"].append({"role": "assistant", "content": final_response})
        return final_response

    async def _handle_msh_borrower_limit_query(
        self, entities: Dict[str, Any], state: Dict[str, Any]
    ) -> str:
        """
        Режим "Справочник": отвечает на вопрос о максимальном размере кредита.
        Улучшенная версия: более гибкий поиск и защита от ошибок.
        """
        logger.info("Режим 'Справочник': запрос максимального лимита кредита.")

        # <<< ИЗМЕНЕНИЕ 1: Добавляем entities = entities or {} для защиты от None >>>
        entities = entities or {}

        # Определяем, по какой категории деятельности задан вопрос
        activity_name = entities.get("activity_name")
        if not activity_name:
            # Если в вопросе нет названия, берем основную категорию клиента из памяти
            program_analysis = state.get("analysis_report", {}).get(
                "programs_analysis", {}
            )
            for program in program_analysis.get("passed", []):
                if "мсх" in program.get("program_name", "").lower():
                    activity_name = program.get("analysis_data", {}).get(
                        "relevant_category"
                    )
                    break

        if not activity_name:
            return "Не удалось определить направление деятельности. Уточните в запросе, например: 'лимит на растениеводство'."

        company_region = state.get("company_region")
        if not company_region:
            return "Регион клиента не определен. Сначала необходимо провести анализ по ИНН."

        # Ищем лимит в загруженных данных
        region_limits = CREDIT_LIMITS_DATA.get(company_region)
        if not region_limits:
            return f"В базе данных отсутствуют сведения о максимальных лимитах для региона «{company_region}»."

        # <<< ИЗМЕНЕНИЕ 2: Гибкий поиск ключа >>>
        found_limit = None
        found_activity_name = None
        for key, value in region_limits.items():
            # Ищем частичное совпадение без учета регистра
            if activity_name.lower() in key.lower():
                found_limit = value
                found_activity_name = key  # Сохраняем "красивое" название из ключа
                break

        if found_limit is None:
            return f"Для направления «{activity_name}» в регионе «{company_region}» максимальный лимит кредита не установлен."

        response = f"По направлению «{found_activity_name}» максимальный лимит кредитования на Заемщика в регионе составляет **{found_limit:,.0f} рублей**.".replace(
            ",", " "
        )

        return response

    async def _handle_msh_regional_balance_query(
        self, entities: Dict[str, Any], state: Dict[str, Any]
    ) -> str:
        """
        Режим "Справочник": отвечает на вопрос об актуальном остатке субсидий в регионе.
        Источник данных: парсер PDF.
        """
        # Эта функция полностью заменяет старую _handle_msh_limits_query
        # Логика остается той же, но меняется стиль ответа.
        logger.info("Режим 'Справочник': запрос актуального остатка субсидий.")

        target_region = state.get("company_region")
        if not target_region:
            return "Регион клиента не определен. Сначала необходимо провести анализ по ИНН."

        all_limits = await get_msh_limits_data()
        if not all_limits:
            return "Не удалось получить актуальные данные о лимитах с сайта Минсельхоза. Сервис может быть временно недоступен."

        region_data, found_region_name = None, None
        target_region_clean = target_region.lower().replace(" ", "")
        for key, value in all_limits.items():
            key_clean = key.lower().replace(" ", "").split("(")[0]
            if key_clean == target_region_clean:
                region_data, found_region_name = value, key
                break

        if not region_data:
            return (
                f"Не найдены данные по остаткам субсидий для региона «{target_region}»."
            )

        response_parts = [
            f"**Справка по актуальным остаткам субсидий в регионе «{found_region_name}»**:\n"
        ]
        has_limits = any(limit > 0 for limit in region_data.values())

        if has_limits:
            for activity, limit in region_data.items():
                if limit > 0:
                    response_parts.append(
                        f"- {activity}: **{limit:,.2f} рублей**".replace(",", " ")
                    )
        else:
            response_parts.append(
                "На текущий момент все лимиты субсидий в данном регионе исчерпаны."
            )

        return "\n".join(response_parts)

    async def _handle_msh_analysis_query(self, state: Dict[str, Any]) -> str:
        """
        Режим "Аналитик": проводит полный расчет и сравнение лимитов,
        формирует итоговую справку для сотрудника.
        """
        logger.info("Режим 'Аналитик': запуск полного расчета по МСХ.")

        # 1. Извлекаем все необходимые данные из state
        programs_analysis = state.get("analysis_report", {}).get(
            "programs_analysis", {}
        )
        msh_data = None
        for program in programs_analysis.get("passed", []):
            if "мсх" in program.get("program_name", "").lower():
                msh_data = program.get("analysis_data")
                break

        if not msh_data:
            return "Не удалось найти данные предварительного анализа по программе МСХ. Убедитесь, что клиент проходит по программе."

        company_region = state.get("company_region")
        if not company_region:
            return "Регион клиента не определен. Невозможно провести анализ."

        # 2. Получаем актуальный остаток субсидий из парсера PDF
        regional_balance_data = await get_msh_limits_data()
        if not regional_balance_data:
            return "Не удалось получить актуальные данные об остатках субсидий. Анализ невозможен."

        # 3. Находим нужные цифры
        max_credit = msh_data.get("max_credit_limit", 0)
        required_subsidy = msh_data.get("calculated_subsidy", 0)
        activity_name = msh_data.get("relevant_category")

        available_subsidy = 0
        target_region_clean = company_region.lower().replace(" ", "")
        for key, value in regional_balance_data.items():
            key_clean = key.lower().replace(" ", "").split("(")[0]
            if key_clean == target_region_clean:
                available_subsidy = value.get(activity_name, 0)
                break

        # 4. Проводим сравнение и формируем вывод
        conclusion = ""
        recommendation = ""
        if required_subsidy == 0:
            conclusion = (
                "Расчет не может быть выполнен, так как требуемая субсидия равна нулю."
            )
        elif available_subsidy >= required_subsidy:
            conclusion = "Лимитов в регионе **достаточно** для предложения максимального кредита."
            recommendation = f"**Заключение:** Клиенту можно предложить кредитование на максимальную сумму, так как доступный остаток ({available_subsidy:,.2f} руб.) превышает требуемую сумму субсидии ({required_subsidy:,.2f} руб.).".replace(
                ",", " "
            )
        else:
            conclusion = "**Внимание:** остаток субсидий в регионе **недостаточен** для получения максимального кредита!"
            # Рассчитываем кредит, который можно обеспечить остатком
            subsidy_rate = msh_data.get("subsidy_rate")
            key_rate = msh_data.get("key_rate")
            possible_credit = 0
            if subsidy_rate and key_rate:
                possible_credit = available_subsidy / (subsidy_rate * (key_rate / 100))

            recommendation = f"**Рекомендация:** Можно предложить клиенту кредит, обеспеченный доступным остатком субсидии (примерно до **{possible_credit:,.0f} рублей**), либо предложить дождаться пополнения лимитов в регионе.".replace(
                ",", " "
            )

        # 5. Собираем финальную справку
        response_parts = [
            f"**Справка по лимитам для клиента ИНН {state['current_inn']} ({state['company_name']})**\n",
            f"**Вывод:** {conclusion}\n",
            "**Детализация расчета:**",
            f"1. **Максимальный кредит к предложению:** {max_credit:,.0f} руб. (для направления «{activity_name}»).".replace(
                ",", " "
            ),
            f"2. **Требуемая годовая субсидия:** {required_subsidy:,.2f} руб. (расчет по формуле).".replace(
                ",", " "
            ),
            f"3. **Доступный остаток субсидий в регионе:** {available_subsidy:,.2f} руб. (данные на сегодня).".replace(
                ",", " "
            ),
            f"\n{recommendation}",
        ]

        return "\n".join(response_parts)

    async def _handle_msh_limits_query(
        self, entities: dict | None, state: Dict[str, Any]
    ) -> str:
        """
        Обрабатывает запросы о лимитах субсидий МСХ на одного заемщика.
        Финальная версия: использует регион из контекста и имеет более гибкую логику сравнения.
        """
        entities = entities or {}
        logger.info(
            f"Обработка запроса о лимитах МСХ. Контекст региона: {state.get('company_region')}"
        )

        # 1. Определяем целевой регион
        target_region = state.get("company_region")
        if not target_region:
            target_region = entities.get("region_name")

        # 2. "Умная" проверка, если регион все еще не известен
        if not target_region:
            if state.get("current_inn"):
                return (
                    f"Я вижу, что мы анализируем компанию с ИНН {state.get('current_inn')}, "
                    "но, к сожалению, я не смог автоматически определить ее регион из адреса.\n\n"
                    "Пожалуйста, уточните его в вашем запросе, например: **«лимиты для Воронежской области»**."
                )
            else:
                return "Чтобы я мог предоставить информацию о лимитах, мне нужно знать ваш регион. Пожалуйста, сначала отправьте ИНН вашей компании для анализа."

        # 3. Вызываем инструмент для получения данных о лимитах (из парсера PDF)
        all_limits = await get_msh_limits_data()
        if not all_limits:
            return "К сожалению, мне не удалось получить актуальные данные о лимитах с сайта Минсельхоза. Возможно, сервис временно недоступен."

        # 4. <<< УЛУЧШЕННАЯ ЛОГИКА ПОИСКА РЕГИОНА >>>
        region_data = None
        found_region_name = None

        # Готовим "чистые" версии названий для сравнения
        target_region_clean = target_region.lower().replace(" ", "")

        for key, value in all_limits.items():
            key_clean = (
                key.lower().replace(" ", "").split("(")[0]
            )  # Убираем скобки типа "(Адыгея)"

            # Сравниваем "очищенные" версии. Это гораздо надежнее.
            if key_clean == target_region_clean:
                region_data = value
                found_region_name = key  # Сохраняем оригинальное, красивое название
                break

        if not region_data:
            return f"К сожалению, я не нашел актуальных данных по остаткам лимитов для региона «{target_region}». Возможно, лимиты уже исчерпаны или данные для региона отсутствуют."

        # 5. Формируем красивый и понятный ответ для пользователя (без изменений)
        response_parts = [
            f"✅ **Актуальный остаток субсидий для одного заемщика в регионе «{found_region_name}»**:\n"
        ]
        has_limits = False
        for activity, limit in region_data.items():
            if limit > 0:
                response_parts.append(
                    f"- **{activity}:** {limit:,.2f} рублей".replace(",", " ")
                )
                has_limits = True

        if not has_limits:
            return f"На текущий момент все лимиты субсидий по программе МСХ для региона «{found_region_name}» исчерпаны."

        final_response = "\n".join(response_parts)
        state["history"].append({"role": "assistant", "content": final_response})
        return final_response

    async def _handle_msh_details_query(self, state: Dict[str, Any]) -> str:
        """
        Формирует конкретный, детальный ответ по программе МСХ,
        используя результаты первоначального анализа.
        """
        logger.info("Формирование детального ответа по программе МСХ.")

        # 1. Извлекаем результаты анализа госпрограмм из "памяти"
        programs_analysis = state.get("analysis_report", {}).get(
            "programs_analysis", {}
        )
        if not programs_analysis:
            return "Не найдены результаты анализа госпрограмм. Пожалуйста, сначала введите ИНН."

        # 2. Ищем конкретно программу МСХ в списке "прошедших"
        msh_program_data = None
        for program in programs_analysis.get("passed", []):
            if "мсх" in program.get("program_name", "").lower():
                msh_program_data = program
                break

        if not msh_program_data:
            # Проверяем, может быть программа в других категориях?
            for category in ["fixable", "failed"]:
                for program in programs_analysis.get(category, []):
                    if "мсх" in program.get("program_name", "").lower():
                        return f"Согласно анализу, ваша компания не проходит по программе МСХ. Причина: {program.get('reason', 'не указана')}"
            return "Анализ по программе МСХ не был найден в отчете."

        # 3. Собираем ответ из уже готовых данных
        conditions = msh_program_data.get(
            "calculated_conditions", "Условия не рассчитаны."
        )
        manual_steps = msh_program_data.get("manual_steps", "")

        response_parts = [
            "✅ **Детальная информация по программе льготного кредитования 'МСХ' для вашей компании:**\n",
            "**Условия кредитования:**",
            conditions,  # Здесь уже есть рассчитанная ставка
            "\n**Требования и примечания:**",
            manual_steps,  # Здесь уже есть рассчитанная субсидия и другие шаги
        ]

        # 4. Добавляем "умное" сравнение с актуальными остатками
        # (Это связывает две части нашей логики вместе)
        actual_limits_data = await get_msh_limits_data()
        company_region = state.get("company_region")

        if actual_limits_data and company_region:
            # ... (здесь можно вставить логику для сравнения субсидии и остатка,
            # как мы обсуждали, но для начала сделаем проще)
            response_parts.append(
                "\n**Напоминание об актуальных остатках:**\n"
                "Не забудьте, что реальная выдача кредита ограничена свободными лимитами субсидий в вашем регионе. "
                "Вы можете проверить их, отправив запрос «какие лимиты в регионе»."
            )

        final_response = "\n".join(response_parts)
        state["history"].append({"role": "assistant", "content": final_response})
        return final_response

    async def _handle_follow_up_query(
        self, user_text: str, state: Dict[str, Any]
    ) -> str:
        logger.info(f"Обработка вопроса в контексте компании «{state['company_name']}»")

        import copy  # Убедитесь, что 'import copy' есть в начале файла

        # Создаем ГЛУБОКУЮ КОПИЮ отчета, чтобы не испортить оригинал в state
        light_report = copy.deepcopy(state.get("analysis_report", {}))

        # Добавляем новостям уникальные ID для ссылок и убираем тяжелые тексты
        news_sources_keys = ["agroinvestor_news", "ria_news_forecast"]
        # Создаем специальный список для краткого ответа, чтобы LLM было проще
        short_news_list = []

        for key in news_sources_keys:
            if key in light_report and light_report[key]:
                for i, news_item in enumerate(light_report[key]):
                    ref_id = f"[{'АГРО' if 'agro' in key else 'РИА'}-{i+1}]"
                    # Добавляем ID, на который сможет сослаться пользователь
                    news_item["reference_id"] = ref_id
                    # Добавляем в отдельный список для промпта
                    short_news_list.append(f"{ref_id} {news_item.get('title')}")
                    # Удаляем полный текст из "легкой" версии
                    if "full_text" in news_item:
                        del news_item["full_text"]

        # Используем "облегченный" отчет для промпта
        context_for_prompt = json.dumps(light_report, ensure_ascii=False, indent=2)

        # --- ИСПРАВЛЕНИЕ: Системный промпт упрощен и сфокусирован ---
        system_prompt = (
            "Ты — дружелюбный финансовый консультант. Твоя задача — отвечать на вопросы пользователя, основываясь ИСКЛЮЧИТЕЛЬНО на фактах из JSON-контекста. "
            "Веди диалог естественно. Не выдумывай информацию. "
            "Если пользователь просит общий обзор новостей, предоставь краткий список заголовков, используя `reference_id` из контекста."
        )

        # --- ИСПРАВЛЕНИЕ: Промпт пользователя теперь использует "облегченный" контекст ---
        user_prompt = (
            f"**КОНТЕКСТ (досье по компании «{state['company_name']}»):**\n"
            f"```json\n{context_for_prompt}\n```\n\n"
            f"**СПИСОК НОВОСТЕЙ С ID:**\n"  # Явно даем список для удобства LLM
            f"{json.dumps(short_news_list, ensure_ascii=False, indent=2)}\n\n"
            f"**ИСТОРИЯ ДИАЛОГА:**\n{json.dumps(state['history'], ensure_ascii=False)}\n\n"
            f"**НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ:** '{user_text}'\n\n"
            f"**ТВОЯ ЗАДАЧА:**\n"
            "Дай полезный ответ на вопрос пользователя, основываясь на данных из JSON.\n"
            "**Если пользователь просит общий обзор новостей**, кратко перечисли их заголовки из списка 'СПИСОК НОВОСТЕЙ С ID', обязательно указывая ID в начале каждой строки (например, '[АГРО-1] Заголовок...').\n"
            "Для всех остальных вопросов ищи информацию в JSON-контексте."
        )

        try:
            client = self.giga_nlu._get_client("formatting")
            response = await asyncio.to_thread(
                client.invoke,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
            )
            response_text = (
                response.content.strip()
                .replace("**", "")
                .replace("##", "")
                .replace("`", "")
            )
            # Удаляем старый ответ из истории, чтобы не дублировать
            if state["history"] and state["history"][-1]["role"] == "user":
                state["history"].pop()

            state["history"].append({"role": "user", "content": user_text})
            state["history"].append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            logger.error(f"Ошибка при генерации диалогового ответа: {e}", exc_info=True)
            return "Произошла ошибка при обработке вашего вопроса. Попробуйте переформулировать."

    # <<< ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ПОЛНОСТЬЮ >>>
    async def handle_message(self, user_id: str, text: str) -> str:
        logger.info(f"Получено сообщение от {user_id}: '{text}'")
        state = self.get_or_create_state(user_id)

        # Проверяем на ИНН в первую очередь
        inn_match = re.fullmatch(r"(\d{10}|\d{12})", text.strip())
        if inn_match:
            return await self._run_full_company_analysis(inn_match.group(1), state)

        # Если это не ИНН, но есть контекст компании, используем NLU
        if state.get("current_inn"):
            state["history"].append({"role": "user", "content": text})

            # Здесь должен быть ваш улучшенный промпт для NLU,
            # который поможет ему различать новые намерения.
            # Например, вы можете передать примеры в вашу функцию extract_intent_and_entities
            nlu_result = self.giga_nlu.extract_intent_and_entities(text, state)
            intent = nlu_result.get("intent")
            entities = nlu_result.get("entities")

            # Новая логика маршрутизации
            if intent == "analyze_msh_for_client":
                return await self._handle_msh_analysis_query(state)

            elif intent == "query_msh_borrower_limit":
                return await self._handle_msh_borrower_limit_query(entities, state)

            elif (
                intent == "query_msh_regional_balance"
            ):  # Это новое название для старого query_msh_limits
                return await self._handle_msh_regional_balance_query(entities, state)

            elif intent == "query_news_details":
                return await self._handle_news_details_query(text, state, entities)

            # Все остальные запросы идут в общий обработчик
            else:
                # Меняем системный промпт для общего обработчика, чтобы он соответствовал новой роли
                # Мы делаем это "на лету" здесь, или вы можете сделать это в самой функции
                # _handle_follow_up_query, передав роль как параметр.
                # Это пример, как можно адаптировать стиль общения.
                original_prompt = "Ты — дружелюбный финансовый консультант."
                new_prompt = "Ты — ассистент-аналитик. Твоя задача — предоставлять сотруднику банка точную информацию по его запросу на основе предоставленных данных. Отвечай в деловом стиле."
                # Здесь нужна логика для временной замены промпта...
                return await self._handle_follow_up_query(text, state)

        # Если контекста нет
        else:
            return "Для начала работы, пожалуйста, предоставьте ИНН клиента для проведения комплексного анализа."
