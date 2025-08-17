# Файл: programs/sovmeshchennaya.py (ИСПРАВЛЕННАЯ ВЕРСИЯ С ПРОВЕРКОЙ ПО ПРЕФИКСУ)

import logging
import asyncio
from parser import full_cheko, msp_check, cb

# Списки правил остаются без изменений
ALLOWED_OKVED_RULES = [
    {"code": "10"},
    {"code": "11", "exceptions": []},
    {"code": "13"},
    {"code": "14"},
    {"code": "15"},
    {"code": "16"},
    {"code": "17"},
    {"code": "18"},
    {"code": "19", "exceptions": ["19.2"]},
    {"code": "20", "exceptions": ["20.14"]},
    {"code": "21"},
    {"code": "22"},
    {"code": "23"},
    {"code": "24", "exceptions": ["24.52"]},
    {"code": "25"},
    {"code": "26"},
    {"code": "27"},
    {"code": "28"},
    {"code": "29", "exceptions": ["29.1"]},
    {"code": "30", "exceptions": ["30.91"]},
    {"code": "31"},
    {"code": "32"},
    {"code": "33"},
    {"code": "52"},
    {"code": "55"},
    {"code": "63"},
    {"code": "71", "exceptions": ["71.12.2"]},
    {"code": "72"},
    {"code": "74"},
]
FORBIDDEN_OKVED_RULES = [
    {"code": "05", "exceptions": ["05.10.2", "05.20.2"]},
    {"code": "06", "exceptions": []},
    {"code": "07", "exceptions": ["07.10.3", "07.29.33"]},
    {"code": "08", "exceptions": ["08.12.1", "08.92.2"]},
    {"code": "46.12"},
    {"code": "46.17"},
    {"code": "46.3"},
    {"code": "46.72"},
    {"code": "46.76.4"},
    {"code": "11", "exceptions": ["11.06", "11.07"]},
    {"code": "12", "exceptions": []},
    {"code": "19.2"},
    {"code": "20.14"},
    {"code": "24.52"},
    {"code": "29.1"},
    {"code": "30.91"},
    {"code": "35.2"},
    {"code": "45.1"},
    {"code": "45.40"},
    {"code": "46.12.1"},
    {"code": "46.71"},
    {"code": "47.11"},
    {"code": "47.2"},
    {"code": "47.3"},
    {"code": "47.78.6"},
    {"code": "47.81"},
    {"code": "47.99.3"},
    {"code": "56.3"},
    {"code": "09.10.3"},
    {"code": "64.1"},
    {"code": "64.3"},
    {"code": "64.92"},
    {"code": "64.99"},
    {"code": "65", "exceptions": []},
    {"code": "66", "exceptions": ["66.19.3", "66.19.6", "66.19.7", "66.29.2"]},
    {"code": "92", "exceptions": []},
]

# ==============================================================================
# <<< ПОЛНОСТЬЮ ПЕРЕПИСАННАЯ ФУНКЦИЯ ПРОВЕРКИ ОКВЭД >>>
# ==============================================================================
def _check_okved_rules(all_okveds: list[tuple[str, str]], main_okved_code: str, main_okved_name: str) -> dict:
    """
    Проверяет ОКВЭД по иерархическому принципу (по префиксам).
    1. Основной ОКВЭД должен начинаться с одного из разрешенных кодов (и не быть в исключениях).
    2. Ни один из ОКВЭД (основной или дополнительный) не должен начинаться с запрещенного кода (и не быть в исключениях).
    """
    
    def is_code_allowed(code_to_check: str, rules: list[dict]) -> bool:
        """Проверяет, соответствует ли код правилам (с учетом исключений)."""
        for rule in rules:
            rule_code = rule["code"]
            exceptions = rule.get("exceptions", [])
            
            # Проверяем, не является ли код исключением
            is_exception = False
            for exc in exceptions:
                if code_to_check.startswith(exc):
                    is_exception = True
                    break
            if is_exception:
                continue # Переходим к следующему правилу, т.к. этот код - исключение

            # Если код начинается с разрешенного/запрещенного префикса и не является исключением
            if code_to_check.startswith(rule_code):
                return True
        return False

    # 1. Проверяем, что основной ОКВЭД соответствует РАЗРЕШЕННЫМ правилам
    if not is_code_allowed(main_okved_code, ALLOWED_OKVED_RULES):
        return {
            "passed": False,
            "reason": f"Основной ОКВЭД ({main_okved_code} - {main_okved_name}) не входит в приоритетные отрасли.",
        }

    # 2. Проверяем все ОКВЭДы компании на соответствие ЗАПРЕЩЕННЫМ правилам
    for code, name in all_okveds:
        if is_code_allowed(code, FORBIDDEN_OKVED_RULES):
            return {
                "passed": False,
                "reason": f"Обнаружен запрещенный ОКВЭД ({code} - {name}).",
            }

    # 3. Если все проверки пройдены
    return {"passed": True}


# BASE_CONDITIONS_TEXT остается без изменений
BASE_CONDITIONS_TEXT = """
- **Цели кредита:** Инвестиционные цели, такие как приобретение или создание основных средств, запуск новых производств. До 20% от суммы кредита можно направить на пополнение оборотных средств.
- **Срок:** До 10 лет, при этом период субсидирования процентной ставки составляет 5 лет.
- **Сумма кредита:** От 50 миллионов рублей. Максимальный лимит зависит от категории субъекта МСП (микро, малое или среднее предприятие).
- **Общий принцип ставки:** Плавающая ставка, привязанная к Ключевой ставке ЦБ РФ, но субсидируемая государством.
- **Основные требования:** Компания должна быть в реестре МСП, основной ОКВЭД должен относиться к приоритетным отраслям (обрабатывающие производства, IT, туризм и др.), и отсутствовать запрещенные виды деятельности.
"""

# Основная функция check_sovmeshchennaya_program остается без изменений,
# так как вся логика инкапсулирована в _check_okved_rules
async def check_sovmeshchennaya_program(company_dossier: dict) -> dict:
    inn = company_dossier.get("inn", "N/A")
    log_prefix = f"[Совмещенная, ИНН {inn}]"
    check_log = []
    result = {
        "program_name": "МЭР-2025 'Совмещенная' (Комбо 2.0)",
        "base_conditions": BASE_CONDITIONS_TEXT,
    }

    try:
        # Шаг 1: Проверка в реестре МСП
        check_log.append("Шаг 1: Проверка в Едином реестре субъектов МСП.")
        msp_category = company_dossier.get("msp_category")

        if not msp_category:
            check_log.append("❌ РЕЗУЛЬТАТ: Компания не найдена в реестре МСП.")
            result.update({
                "passed": False,
                "reason": "Компания не найдена в Едином реестре субъектов МСП.",
                "check_log": check_log, "calculated_conditions": None
            })
            return result
            
        clean_msp_category = msp_category.replace("\n", " ").strip().lower()
        check_log.append(f"✅ РЕЗУЛЬТАТ: Компания найдена, категория - '{clean_msp_category}'.")

        # Шаг 2: Проверка ОКВЭД
        check_log.append("Шаг 2: Проверка ОКВЭД на соответствие правилам программы.")
        okved_data = company_dossier.get("full_cheko_data", {}).get("okved_data")
        
        if not okved_data or not okved_data.get("main_okved"):
            check_log.append("❌ РЕЗУЛЬТАТ: Данные по ОКВЭД отсутствуют в досье.")
            result.update({"passed": False, "reason": "Не удалось получить данные по ОКВЭД.", "check_log": check_log, "calculated_conditions": None})
            return result

        main_okved = okved_data["main_okved"]
        all_okveds = [(main_okved["code"], main_okved["name"])] + [(i["code"], i["name"]) for i in okved_data.get("additional_okved", [])]

        # Вызываем новую, умную функцию проверки
        okved_result = _check_okved_rules(all_okveds, main_okved["code"], main_okved["name"])
        if not okved_result["passed"]:
            check_log.append(f"❌ РЕЗУЛЬТАТ: {okved_result['reason']}")
            result.update({**okved_result, "check_log": check_log, "calculated_conditions": None})
            return result
        check_log.append("✅ РЕЗУЛЬТАТ: ОКВЭДы соответствуют требованиям программы.")
        
        # Шаг 3: Расчет лимита и ставки
        check_log.append("Шаг 3: Расчет кредитного лимита и льготной ставки.")
        limit_map = {"микропредприятие": "200 млн рублей", "малое предприятие": "500 млн рублей", "среднее предприятие": "2 млрд рублей"}
        credit_limit_text = limit_map.get(clean_msp_category, "не определен")
        check_log.append(f"   - Лимит для категории '{clean_msp_category}' составляет {credit_limit_text}.")

        key_rate_str = company_dossier.get("cbr_key_rate")
        key_rate_date = company_dossier.get("cbr_key_rate_date")
        rate_text = "Не удалось рассчитать ставку."
        if key_rate_str and key_rate_date:
            try:
                ks = float(key_rate_str.replace(",", "."))
                final_rate = (ks - 3.5) if ks > 12 else max(3.0, ks - 2.5)
                calc_info = f"КС ({ks:.1f}%) > 12%, ставка = КС - 3.5%" if ks > 12 else f"КС ({ks:.1f}%) <= 12%, ставка = max(3%, КС - 2.5%)"
                rate_text = f"**{final_rate:.2f}%** годовых ({calc_info})."
                check_log.append(f"   - Ставка рассчитана на основе КС={ks}%. Итог: {final_rate:.2f}%.")
            except Exception:
                check_log.append("   - Ошибка при расчете ставки.")
        else:
            check_log.append("   - Данные о ключевой ставке отсутствуют в досье.")
        
        # --- Формирование УСПЕШНОГО ответа ---
        calculated_conditions = (
            f"- Цель кредита: Инвестиционные цели (до 20% на оборотные средства).\n"
            f"- Сумма кредита: От 50 млн до **{credit_limit_text}** (категория '{clean_msp_category}').\n"
            f"- Срок: До 10 лет (субсидия на 5 лет).\n"
            f"- Льготная процентная ставка: {rate_text}"
        )
        manual_steps = (
            "- Необходимо предоставить в банк:\n"
            "  • Учредительные документы.\n"
            "  • Документы для подтверждения отсутствия банкротства и структуры собственности."
        )

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
            "reason": f"Произошла внутренняя ошибка при проверке: {e}",
            "check_log": check_log,
            "calculated_conditions": None
        })
        return result