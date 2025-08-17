from langchain_gigachat import GigaChat
from langchain_core.messages import SystemMessage, HumanMessage
from typing import List, Optional, Dict, Any
import json
import re
import logging
import time

# Правильный относительный импорт для вашей структуры проекта
from src.config import settings

logger = logging.getLogger(__name__)


# Вспомогательная функция для безопасного преобразования
def safe_float_convert(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", "."))
    except (ValueError, TypeError):
        return None


class GigaChatNLU:
    _client_extraction: Optional[GigaChat] = None
    _client_formatting: Optional[GigaChat] = None

    def _get_client(self, purpose: str = "extraction") -> GigaChat:
        client_attr = f"_client_{purpose}"
        current_client_instance = getattr(self, client_attr, None)
        if current_client_instance is None:
            logger.debug(f"GigaChat client for {purpose} is None, will create new.")
            temperature_to_use = (
                settings.GIGACHAT_TEMPERATURE_EXTRACTION
                if purpose == "extraction"
                else settings.GIGACHAT_TEMPERATURE_FORMATTING
            )
            max_tokens_to_use = (
                settings.GIGACHAT_MAX_TOKENS_EXTRACTION
                if purpose == "extraction"
                else settings.GIGACHAT_MAX_TOKENS_FORMATTING
            )
            # Увеличим токен для NLU, чтобы избежать проблем с длинными контекстами
            if purpose == "extraction":
                max_tokens_to_use = 450

            # Увеличим токен и для форматирования
            if purpose == "formatting":
                max_tokens_to_use = 550

            client_params = {
                "credentials": settings.GIGACHAT_CREDENTIALS,
                "scope": settings.GIGACHAT_SCOPE,
                "verify_ssl_certs": settings.GIGACHAT_VERIFY_SSL_CERTS,
                "model": settings.GIGACHAT_MODEL,
                "timeout": settings.GIGACHAT_TIMEOUT,
                "profanity_check": settings.GIGACHAT_PROFANITY_CHECK,
                "temperature": temperature_to_use,
                "max_tokens": max_tokens_to_use,
            }
            logger.debug(
                f"Initializing GigaChat for {purpose} with params: {client_params}"
            )
            try:
                new_client = GigaChat(**client_params)
                setattr(self, client_attr, new_client)
                logger.info(f"GigaChat client for {purpose} created successfully.")
                return new_client
            except Exception as e:
                logger.critical(
                    f"Failed to initialize GigaChat client for {purpose}: {e}",
                    exc_info=True,
                )
                raise
        if getattr(self, client_attr, None) is None:
            logger.critical(f"CRITICAL: GigaChat client for {purpose} is STILL None.")
            raise RuntimeError(f"Failed to obtain GigaChat client for {purpose}")
        return getattr(self, client_attr)

    def extract_intent_and_entities(
        self, user_input: str, dialogue_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        client = self._get_client(purpose="extraction")
        logger.debug(
            f"Extracting intent/entities from: '{user_input}' with context: {dialogue_context}"
        )

        program_name_ids = [
            "mer_2025_combined",
            "belarus_tech_purchase",
            "new_territories_sez",
            "prigranichye_kmsp",
            "agroprom_lending",
        ]

        program_name_synonyms_map_str = json.dumps(
            {
                "мэр 2025": "mer_2025_combined",
                "мэр совмещенная": "mer_2025_combined",
                "программа 1780": "mer_2025_combined",
                "возмещение недополученных доходов": "mer_2025_combined",
                "беларусь": "belarus_tech_purchase",
                "белорусская техника": "belarus_tech_purchase",
                "покупка белорусских товаров": "belarus_tech_purchase",
                "новые территории": "new_territories_sez",
                "свободная экономическая зона": "new_territories_sez",
                "днр лнр": "new_territories_sez",
                "программа фрт": "new_territories_sez",
                "приграничье": "prigranichye_kmsp",
                "программа для приграничных территорий": "prigranichye_kmsp",
                "кмсп приграничье": "prigranichye_kmsp",
                "мсх": "agroprom_lending",
                "минсельхоз": "agroprom_lending",
                "программа мсх": "agroprom_lending",
                "льготный кредит для апк": "agroprom_lending",
                "агропромышленный комплекс": "agroprom_lending",
            },
            ensure_ascii=False,
        )

        context_hint_parts = []
        if dialogue_context:
            if dialogue_context.get("awaiting_financial_coeffs"):
                context_hint_parts.append(
                    "Бот ожидает от пользователя числовые значения для 'чистый долг/EBITDA' и/или 'ISCR/ICR'."
                )
            if dialogue_context.get("awaiting_program_check_decision"):
                context_hint_parts.append(
                    "Бот только что предложил пользователю проверить госпрограммы и ожидает ответ 'да' или 'нет'."
                )
            if dialogue_context.get("awaiting_program_clarification"):
                context_hint_parts.append(
                    "Бот предоставил информацию по госпрограммам и ожидает уточняющий вопрос о конкретной программе или новый ИНН."
                )
        context_hint = (
            f"Контекст диалога: {' '.join(context_hint_parts)}"
            if context_hint_parts
            else "Контекст диалога: Начало разговора или общий запрос."
        )

        system_prompt_text = (
            "Твоя задача - извлечь структурированные данные и определить основное намерение пользователя-сотрудника банка. "
            f"{context_hint} Всегда отвечай СТРОГО в формате JSON. Не добавляй пояснений."
            "\nКлючи в JSON: 'intent' (строка), 'entities' (объект или null)."
            "\n\nВозможные 'intent':"
            "\n1. 'provide_financial_data': Пользователь предоставляет ИНН и/или фин. коэффициенты."
            "\n2. 'affirmative_response': Ответ 'да', 'хорошо', 'давай'."
            "\n3. 'negative_response': Ответ 'нет', 'не хочу'."
            "\n4. 'check_inn_for_state_programs': Явный запрос проверить ИНН на госпрограммы."
            "\n5. 'list_available_state_programs': Запрос списка всех госпрограмм."
            "\n6. 'query_program_details': Запрос деталей по КОНКРЕТНОЙ программе."
            "\n7. 'query_reasons_for_ineligibility': Почему клиент не подошел под программу."
            "\n8. 'query_web_search': Общий вопрос, требующий поиска в интернете."
            "\n9. 'query_news_details': Запрос подробностей по конкретной новости."
            "\n\n-- СПЕЦИАЛЬНЫЕ НАМЕРЕНИЯ ДЛЯ ПРОГРАММЫ МСХ --"
            "\n10. 'analyze_msh_for_client': **Аналитический запрос.** Требует провести полный расчет и СРАВНЕНИЕ лимитов для клиента."
            "    Примеры: 'проведи расчет по мсх', 'сколько можно выдать клиенту', 'хватит ли лимитов', 'какая субсидия предусмотрена', 'сколько субсидий нужно на год', 'рассчитай субсидию'."
            "\n11. 'query_msh_borrower_limit': **Справка о МАКСИМАЛЬНОМ КРЕДИТЕ.** Запрос теоретического лимита на ОДНОГО заемщика (числа вроде 600 млн)."
            "    Примеры: 'какой максимальный лимит кредита для клиента', 'максимальный лимит в регионе', 'а на животноводство какой лимит?', 'какой потолок по кредиту?'."
            "\n12. 'query_msh_regional_balance': **Справка об ОСТАТКАХ СУБСИДИЙ.** Запрос актуального ОСТАТКА денег в 'общем котле' региона (числа из PDF)."
            "    Примеры: 'какой остаток субсидий в регионе', 'сколько денег осталось в воронежской области', 'покажи актуальные остатки'."
            "\n--------------------------------------------"
            "\n13. 'chitchat_greeting', 'chitchat_thankyou', 'chitchat_capabilities', 'stop_dialogue'."
            "\n14. 'unknown_intent': Если намерение неясно."
            "\n\nСущности 'entities':"
            "\n- 'inn': строка 10 или 12 цифр."
            "\n- 'program_name': Сопоставь с ID из ["
            + ", ".join(program_name_ids)
            + f"]. Карта синонимов: {program_name_synonyms_map_str}."
            "\n- 'region_name': название региона, например 'Белгородская область'."
            "\n- 'activity_name': (Для 'query_msh_borrower_limit') название направления, например 'животноводство'."
            "\n- 'news_source': источник новостей, например 'агроинвестор'."
            "\n- 'news_identifier': ключевые слова из заголовка новости."
        )
        messages = [
            SystemMessage(content=system_prompt_text),
            HumanMessage(content=user_input),
        ]
        default_response = {
            "intent": "unknown_intent",
            "entities": None,
            "_nlu_error": None,
        }
        start_time = time.time()

        try:
            logger.debug(
                f"Sending to GigaChat NLU. Prompt hash: {hash(system_prompt_text)}, Input: '{user_input}'"
            )

            response_object = client.invoke(messages)
            response_content = response_object.content.strip()
            end_time = time.time()

            usage_metadata = response_object.response_metadata.get("token_usage", {})
            prompt_tokens = usage_metadata.get("prompt_tokens", "N/A")
            completion_tokens = usage_metadata.get("completion_tokens", "N/A")
            total_tokens = usage_metadata.get("total_tokens", "N/A")
            logger.info(
                f"GigaChat NLU call took {end_time - start_time:.2f}s. "
                f"Tokens: P={prompt_tokens}, C={completion_tokens}, T={total_tokens}. "
                f"Raw response: '{response_content}'"
            )

            json_match = re.search(r"\{[\s\S]*\}", response_content)
            if json_match:
                json_str = json_match.group(0)
                try:
                    json_str_fixed = json_str.replace("'", '"')
                    parsed_json = json.loads(json_str_fixed)

                    logger.debug(f"Parsed JSON from GigaChat NLU: {parsed_json}")
                    intent = parsed_json.get("intent", "unknown_intent")
                    entities = parsed_json.get("entities")
                    if intent == "provide_financial_data" and isinstance(
                        entities, dict
                    ):
                        for key in ["net_debt_ebitda", "iscr_icr"]:
                            if key in entities and not isinstance(
                                entities[key], (float, int)
                            ):
                                converted_val = safe_float_convert(str(entities[key]))
                                if converted_val is not None:
                                    entities[key] = converted_val
                                else:
                                    entities.pop(key, None)
                    if intent == "query_web_search" and isinstance(entities, dict):
                        if "original_query" not in entities:
                            entities["original_query"] = user_input

                    return {
                        "intent": intent,
                        # <<< ИЗМЕНЕНИЕ: Всегда возвращаем словарь, даже если он пустой >>>
                        "entities": entities if isinstance(entities, dict) else {},
                        "_nlu_error": None,
                    }
                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to parse NLU JSON: '{json_str}'. Error: {e}",
                        exc_info=True,
                    )
                    default_response["_nlu_error"] = "json_decode_error"
            else:
                logger.warning(
                    f"No JSON in GigaChat NLU response: '{response_content}'"
                )
                user_input_lower = user_input.strip().lower()
                if user_input_lower in [
                    "да",
                    "давай",
                    "ага",
                    "хорошо",
                    "согласен",
                    "хочу",
                    "да, хочу",
                ]:
                    return {
                        "intent": "affirmative_response",
                        "entities": None,
                        "_nlu_error": "no_json_fallback",
                    }
                if user_input_lower in [
                    "нет",
                    "не",
                    "не надо",
                    "не хочу",
                    "отказываюсь",
                    "нет, спасибо",
                ]:
                    return {
                        "intent": "negative_response",
                        "entities": None,
                        "_nlu_error": "no_json_fallback",
                    }
                if user_input_lower in ["стоп", "выход", "пока", "завершить"]:
                    return {
                        "intent": "stop_dialogue",
                        "entities": None,
                        "_nlu_error": "no_json_fallback",
                    }

                default_response["_nlu_error"] = "no_json_found"
                if (
                    "blacklist" in response_content.lower()
                    or "ограничены" in response_content.lower()
                ):
                    default_response["_nlu_error"] = "giga_blacklist_error"

            return default_response
        except Exception as e:
            end_time = time.time()
            logger.error(
                f"GigaChat NLU call failed after {end_time - start_time:.2f}s. Error: {e}",
                exc_info=True,
            )
            default_response["_nlu_error"] = "api_call_error"
            return default_response

    def format_message_for_user(
        self,
        base_text: str,
        recommendation: Optional[str] = None,
        explanation: Optional[str] = None,
        suggestions: Optional[List[str]] = None,
        program_info_blocks: Optional[List[Dict[str, Any]]] = None,
        is_error: bool = False,
        prompt_for_next_action: Optional[str] = None,
    ) -> str:
        client = self._get_client(purpose="formatting")
        role_prompt = (
            "Ты — дружелюбный и профессиональный финансовый ассистент. Твоя задача — ясно и понятно донести информацию до пользователя. "
            "Будь вежлив и структурируй ответ. Не используй markdown для выделения жирным шрифтом (никаких `**`)."
        )
        if is_error:
            role_prompt += (
                " Сообщение содержит информацию об ошибке; будь особенно тактичен."
            )
        if recommendation == "Сокращать" and suggestions:
            role_prompt += " Если дана рекомендация 'Сокращать' и есть предложения по улучшению, оформи их как маркированный список (дефис и пробел)."

        role_prompt += (
            " При выводе информации о госпрограммах: используй заголовок для каждой программы (например, 'Программа КМСП Приграничье'). "
            "Если это УСЛОВИЯ, начни с подзаголовка 'Условия программы:'. "
            "Если это ПРИЧИНЫ НЕСООТВЕТСТВИЯ ТРЕБОВАНИЯМ, начни с 'Не соответствует следующим ТРЕБОВАНИЯМ:'. "
            "Если это ОБЩИЕ ТРЕБОВАНИЯ, начни с 'Основные ТРЕБОВАНИЯ для участия:'. "
            "Если это список программ, начни с 'Список доступных программ:'. "
            "Для всех списков внутри условий/требований/списка программ используй маркеры '* ' (звездочка и пробел)."
        )

        task_description = "Сформулируй ответ пользователю на основе информации ниже. Не добавляй ничего, что не предоставлено. Если части информации нет, не упоминай ее.\n---\n"
        content_to_format = base_text
        if recommendation:
            content_to_format += f"\nРекомендация: {recommendation}."
        if explanation:
            content_to_format += f"\nПояснение: {explanation}."
        if suggestions:
            content_to_format += "\n\nПредложения по улучшению ситуации:"
            for suggestion in suggestions:
                content_to_format += f"\n- {suggestion}"
        if program_info_blocks:
            content_to_format += "\n"
            for block in program_info_blocks:
                status_emoji = block.get("status_emoji", "")
                content_to_format += f"\n\n{status_emoji} {block['title']}"

                type_map = {
                    "conditions": "Условия программы",
                    "requirements_failed": "Не соответствует следующим ТРЕБОВАНИЯМ",
                    "general_requirements": "Основные ТРЕБОВАНИЯ для участия",
                    "program_list": "Список доступных программ",
                    "info": "",
                }
                header_text = type_map.get(block["type"])
                if header_text:
                    content_to_format += f"\n    {header_text}:"
                elif block["type"] != "info":
                    content_to_format += (
                        f"\n    {block['type'].replace('_', ' ').capitalize()}:"
                    )

                if isinstance(block["details"], dict):
                    for key, value in block["details"].items():
                        content_to_format += (
                            f"\n    * {key.strip()}: {str(value).strip()}"
                        )
                elif isinstance(block["details"], list):
                    for item_text in block["details"]:
                        content_to_format += f"\n    * {str(item_text).strip()}"
                elif block["details"] is not None:
                    content_to_format += f"\n    {str(block['details'])}"
        if prompt_for_next_action:
            content_to_format += f"\n\n{prompt_for_next_action}"
        user_prompt_for_formatter = task_description + content_to_format + "\n---"

        fallback_response = content_to_format.replace("**", "")

        start_time = time.time()
        try:
            logger.debug(
                f"Sending to GigaChat Formatter. Sys prompt hash: {hash(role_prompt)}, User content hash: {hash(user_prompt_for_formatter)}"
            )

            response_object = client.invoke(
                [
                    SystemMessage(content=role_prompt),
                    HumanMessage(content=user_prompt_for_formatter),
                ]
            )
            end_time = time.time()

            formatted_response = response_object.content.strip().replace("**", "")

            usage_metadata = response_object.response_metadata.get("token_usage", {})
            prompt_tokens = usage_metadata.get("prompt_tokens", "N/A")
            completion_tokens = usage_metadata.get("completion_tokens", "N/A")
            total_tokens = usage_metadata.get("total_tokens", "N/A")

            logger.info(
                f"GigaChat Formatter call took {end_time - start_time:.2f}s. "
                f"Tokens used: Prompt={prompt_tokens}, Completion={completion_tokens}, Total={total_tokens}. "
                f"Formatted response: '{formatted_response}'"
            )

            return formatted_response if formatted_response else fallback_response

        except Exception as e:
            end_time = time.time()
            logger.error(
                f"GigaChat Formatter call failed after {end_time - start_time:.2f}s. Error: {e}",
                exc_info=True,
            )
            logger.warning(
                f"Returning fallback for formatter error: '{fallback_response}'"
            )
            return fallback_response
