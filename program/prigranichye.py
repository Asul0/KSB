# Файл: programs/prigranichye.py

import logging
import asyncio
import re
from bs4 import BeautifulSoup
from parser import full_cheko, msp_check, cb

ALLOWED_REGIONS = ["курская область", "белгородская область", "брянская область"]
FORBIDDEN_OKVED_RULES = [
    {"code": "05", "exceptions": ["05.10.2", "05.20.2"]},
    {"code": "06", "exceptions": []},
    {"code": "07", "exceptions": ["07.10.3", "07.29.33"]},
    {"code": "08", "exceptions": ["08.12.1", "08.92.2"]},
    {"code": "46.12"},
    {"code": "46.72"},
    {"code": "46.76.4"},
    {"code": "01.21"},
    {"code": "11", "exceptions": ["11.06", "11.07"]},
    {"code": "12", "exceptions": []},
    {"code": "19.2"},
    {"code": "20.14"},
    {"code": "29.1"},
    {"code": "30.91"},
    {"code": "35.2"},
    {"code": "45.1"},
    {"code": "45.40"},
    {"code": "46.12.1"},
    {"code": "46.17"},
    {"code": "46.3"},
    {"code": "46.71"},
    {"code": "47.11"},
    {"code": "47.2"},
    {"code": "47.3"},
    {"code": "47.78.6"},
    {"code": "47.81"},
    {"code": "47.99.3"},
    {"code": "09.10.3"},
    {"code": "64.1"},
    {"code": "64.3"},
    {"code": "64.92"},
    {"code": "64.99"},
    {"code": "65", "exceptions": []},
    {"code": "66", "exceptions": ["66.19.3", "66.19.6", "66.19.7", "66.29.2"]},
    {"code": "92", "exceptions": []},
]


def _get_company_region(address: str) -> str | None:
    if not address:
        return None
    parts = address.split(",")
    for part in parts:
        part = part.strip().lower()
        if any(
            keyword in part for keyword in ["область", "край", "республика", "округ"]
        ):
            return part
    return None


def _check_forbidden_okved(company_okveds):
    """
    Проверяет ОКВЭД компании по списку запрещенных кодов на ТОЧНОЕ совпадение.
    """
    forbidden_codes = {rule["code"] for rule in FORBIDDEN_OKVED_RULES}

    for code, name in company_okveds:
        if code in forbidden_codes:
            return {
                "passed": False,
                "reason": f"Обнаружен запрещенный вид деятельности ({code} - {name}).",
            }
            
    return {"passed": True}


BASE_CONDITIONS_TEXT = """
- **Территория действия:** Программа доступна для предпринимателей, зарегистрированных и ведущих деятельность в Курской, Белгородской и Брянской областях.
- **Цели кредита:** Оборотное и инвестиционное кредитование, а также рефинансирование ранее полученных кредитов.
- **Сумма кредита:** До 30 миллионов рублей.
- **Срок:** До 12 месяцев.
- **Ставка:** Равна Ключевой ставке ЦБ РФ на дату заключения договора.
- **Основные требования:** Отсутствие процедуры банкротства, соответствие ОКВЭД правилам программы.
"""

async def check_prigranichye_program(company_dossier: dict) -> dict:
    inn = company_dossier.get("inn", "N/A")
    log_prefix = f"[Приграничье, ИНН {inn}]"
    check_log = []
    # --- ИЗМЕНЕНИЕ 2: Всегда начинаем с базового словаря ---
    result = {
        "program_name": "Программа 'КМСП Приграничье'",
        "base_conditions": BASE_CONDITIONS_TEXT,
    }

    try:
        # Шаг 1: Получение данных о компании
        check_log.append("Шаг 1: Анализ данных о компании для определения региона и ОКВЭД.")
        full_cheko_data = company_dossier.get("full_cheko_data", {})
        if not full_cheko_data:
            check_log.append("❌ РЕЗУЛЬТАТ: Данные с checko.ru отсутствуют в досье.")
            result.update({"passed": False, "reason": "Не удалось получить данные о компании с checko.ru.", "check_log": check_log, "calculated_conditions": None})
            return result

        general_info = full_cheko_data.get("general_info", {})
        okved_data = full_cheko_data.get("okved_data", {})

        # Шаг 2: Проверка региона
        company_region = _get_company_region(general_info.get("address"))
        check_log.append(f"Шаг 2: Проверка региона компании ('{company_region}') на вхождение в список приграничных.")

        if not company_region or not any(r in company_region for r in ALLOWED_REGIONS):
            check_log.append("❌ РЕЗУЛЬТАТ: Регион не входит в перечень (Курская, Белгородская, Брянская области).")
            result.update({
                "passed": False,
                "reason": f"Регион компании ('{company_region}') не входит в перечень приграничных.",
                "check_log": check_log,
                "calculated_conditions": None
            })
            return result
        check_log.append(f"✅ РЕЗУЛЬТАТ: Регион '{company_region}' подходит.")

        # Шаг 3: Проверка ОКВЭД
        check_log.append("Шаг 3: Проверка ОКВЭД на наличие запрещенных видов деятельности.")
        if not okved_data or not okved_data.get("main_okved"):
            check_log.append("❌ РЕЗУЛЬТАТ: Данные по ОКВЭД отсутствуют в досье.")
            result.update({"passed": False, "reason": "Не удалось получить данные по ОКВЭД.", "check_log": check_log, "calculated_conditions": None})
            return result

        all_okveds = [(okved_data["main_okved"]["code"], okved_data["main_okved"]["name"])]
        all_okveds.extend([(item["code"], item["name"]) for item in okved_data.get("additional_okved", [])])

        okved_res = _check_forbidden_okved(all_okveds)
        if not okved_res["passed"]:
            check_log.append(f"❌ РЕЗУЛЬТАТ: {okved_res['reason']}")
            result.update({**okved_res, "check_log": check_log, "calculated_conditions": None})
            return result
        check_log.append("✅ РЕЗУЛЬТАТ: Запрещенные ОКВЭД не найдены.")

        # Шаг 4: Получение информации о ставке
        check_log.append("Шаг 4: Получение ключевой ставки ЦБ для информации.")
        key_rate_str = company_dossier.get("cbr_key_rate")
        key_rate_date = company_dossier.get("cbr_key_rate_date")
        rate_text = (f"равна Ключевой ставке ЦБ РФ ({key_rate_str}% на {key_rate_date})." if key_rate_str else "равна Ключевой ставке ЦБ РФ.")

        # --- Формирование УСПЕШНОГО ответа ---
        calculated_conditions = (
            f"- Цель кредита: Оборотное/инвестиционное/рефинансирование.\n"
            f"- Сумма кредита: Не более 30 млн руб.\n"
            f"- Срок: Не более 12 месяцев.\n"
            f"- Процентная ставка: {rate_text}"
        )
        manual_steps = (
            "- Необходимо предоставить в банк:\n"
            "  • Документы, подтверждающие отсутствие процедуры банкротства.\n"
            "  • Документы о структуре собственности."
        )
        
        # --- ИЗМЕНЕНИЕ 3: Обновляем и возвращаем итоговый словарь ---
        result.update({
            "passed": True,
            "calculated_conditions": calculated_conditions,
            "manual_steps": manual_steps,
            "check_log": check_log
        })
        return result

    except Exception as e:
        logging.error(f"{log_prefix} Непредвиденная ошибка: {e}", exc_info=True)
        check_log.append(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        result.update({
            "passed": False,
            "reason": f"Внутренняя ошибка при проверке: {e}",
            "check_log": check_log,
            "calculated_conditions": None
        })
        return result