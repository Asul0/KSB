import re
import logging
import asyncio
import json
from pathlib import Path




def load_data_from_json(filename: str):
    """Универсальная функция для загрузки данных из JSON."""
    try:
        current_dir = Path(__file__).parent.parent
        json_path = current_dir / "data" / filename
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Критическая ошибка при загрузке файла {filename}: {e}")
        return None


okved_rules = load_data_from_json("msh_okveds.json")
(
    ALLOWED_OKVEDS_STANDARD,
    ALLOWED_OKVEDS_CLARIFICATION,
    ALL_ALLOWED_OKVEDS,
    OKVED_TO_CATEGORY_MAP,
) = (set(), set(), set(), {})
if okved_rules:
    for rule in okved_rules:
        category, codes, status = (
            rule.get("category"),
            rule.get("codes", []),
            rule.get("status"),
        )
        if status == "clarification":
            ALLOWED_OKVEDS_CLARIFICATION.update(codes)
        else:
            ALLOWED_OKVEDS_STANDARD.update(codes)
        for code in codes:
            OKVED_TO_CATEGORY_MAP[code] = category
    ALL_ALLOWED_OKVEDS = ALLOWED_OKVEDS_STANDARD.union(ALLOWED_OKVEDS_CLARIFICATION)

CREDIT_LIMITS_DATA = load_data_from_json("msh_credit_limits.json") or {}

PRIORITY_OKVED_CATEGORIES_MSH = {"Молочное животноводство", "Растениеводство"}
MEDICAL_FOOD_OKVEDS = {"10.86"}

BASE_CONDITIONS_TEXT = """
- **Цели кредита:** Оборотное/инвестиционное/проектное финансирование в соответствии с ДКЦ.
- **Типы кредитов:** Краткосрочные (до 1 года) и инвестиционные (от 2 до 15 лет).
- **Ставка:** неприоритетное направление - 0,5КС+2%, приоритетное направление - 0,3КС+2%, ИСКЛЮЧЕНИЕ (производство лечеб питания) - 2%
- **Размер субсидии:** Расчетный годовой размер субсидии зависит от направления:
  - *Приоритетное:* 0,7 * КС * (Лимит кредита)
  - *Неприоритетное:* 0,5 * КС * (Лимит кредита)
  - *Исключение (лечеб. питание):* 1,0 * КС * (Лимит кредита)
- **Основное требование:** Наличие свободных лимитов субсидий по региону и направлению деятельности заемщика.
- **Режим кредитования:** НКЛ.
"""


def _get_company_region(address: str) -> str | None:
    """
    Извлекает название региона из строки адреса.
    Финальная, надежная версия: использует регулярные выражения для поиска целых слов,
    чтобы избежать частичных замен и повреждения строки.
    """
    if not address or not isinstance(address, str):
        return None

    address_lower = address.lower()
    parts = [part.strip() for part in address_lower.split(",")]

    region_map = {
        "область": [r"\bобл\b", r"\bобласть\b"],
        "край": [r"\bкрай\b"],
        "республика": [r"\bресп\b", r"\bреспублика\b"],
        "автономный округ": [r"\bао\b"],
    }

    federal_cities = ["москва", "санкт-петербург", "севастополь"]

    for part in parts:
        for city in federal_cities:
            if f"г. {city}" == part or city == part:
                return f"г. {city.capitalize()}"

        for standard_name, patterns in region_map.items():
            for pattern in patterns:
                if re.search(pattern, part):
                    region_name_part = re.sub(pattern, "", part).strip()
                    return f"{region_name_part.title()} {standard_name}"

    return parts[1].strip().title() if len(parts) > 1 else None


async def check_msh_program(company_dossier: dict) -> dict:
    inn = company_dossier.get("inn", "N/A")
    log_prefix = f"[МСХ, ИНН {inn}]"
    check_log = []

    result = {
        "program_name": "Программа льготного кредитования 'МСХ'",
        "base_conditions": BASE_CONDITIONS_TEXT,
        "analysis_data": {
            "is_priority": None, "subsidy_rate": 0.0, "key_rate": 0.0,
            "relevant_category": None, "max_credit_limit": 0, "calculated_subsidy": 0,
            "rate_text": "Ставка не рассчитана.", "subsidy_text": "Субсидия не рассчитана."
        },
    }

    try:
        check_log.append("Шаг 1: Проверка наличия компании в ЕГРЮЛ и базовых данных.")
        if not company_dossier.get("is_in_egrul"):
            result.update({"passed": False, "reason": "Компания не найдена в ЕГРЮЛ.", "check_log": check_log})
            return result
        full_cheko_data = company_dossier.get("full_cheko_data", {})
        okved_data = full_cheko_data.get("okved_data", {})
        if not okved_data or not okved_data.get("main_okved"):
            result.update({"passed": False, "reason": "Отсутствуют данные по ОКВЭД.", "check_log": check_log})
            return result
        check_log.append("✅ РЕЗУЛЬТАТ: Компания найдена, данные по ОКВЭД присутствуют.")
        
        check_log.append("Шаг 2: Анализ ОКВЭД и ранний расчет потенциальных условий.")
        company_okveds_list = [okved_data["main_okved"]] + okved_data.get("additional_okved", [])
        company_okved_codes = {o["code"] for o in company_okveds_list}
        matched_codes = company_okved_codes.intersection(ALL_ALLOWED_OKVEDS)
        
        relevant_category = "Не определена"
        is_priority = False
        if matched_codes:
            for okved in company_okveds_list:
                if okved["code"] in matched_codes:
                    relevant_category = OKVED_TO_CATEGORY_MAP.get(okved["code"], "Прочее")
                    if relevant_category in PRIORITY_OKVED_CATEGORIES_MSH:
                        is_priority = True
                    break
        result["analysis_data"]["relevant_category"] = relevant_category
        result["analysis_data"]["is_priority"] = is_priority
        check_log.append(f"   - Определена категория '{relevant_category}' (Приоритет: {is_priority}).")
        
        key_rate_str = company_dossier.get("cbr_key_rate")
        key_rate_date = company_dossier.get("cbr_key_rate_date")
        ks = 0.0
        if key_rate_str:
            try:
                ks = float(key_rate_str.replace(",", "."))
                result["analysis_data"]["key_rate"] = ks
                main_okved_code = okved_data["main_okved"]["code"]
                if main_okved_code in MEDICAL_FOOD_OKVEDS:
                    final_rate, rate_desc = 2.0, f"**фиксированная ставка: 2.00% годовых**"
                elif is_priority:
                    final_rate = 0.3 * ks + 2.0
                    rate_desc = f"(0.3 * {ks:.2f}% КС) + 2% = **{final_rate:.2f}% годовых**."
                else:
                    final_rate = 0.5 * ks + 2.0
                    rate_desc = f"(0.5 * {ks:.2f}% КС) + 2% = **{final_rate:.2f}% годовых**."
                result["analysis_data"]["rate_text"] = f"Ставка от Ключевой Ставки ЦБ ({ks:.2f}% на {key_rate_date}).\nРасчет: {rate_desc}"
            except (ValueError, TypeError): pass
        
        company_region = _get_company_region(full_cheko_data.get("general_info", {}).get("address"))
        if company_region and CREDIT_LIMITS_DATA and ks > 0:
            region_limits = CREDIT_LIMITS_DATA.get(company_region)
            if region_limits:
                credit_limit = region_limits.get(relevant_category)
                if credit_limit:
                    result["analysis_data"]["max_credit_limit"] = credit_limit
                    main_okved_code = okved_data["main_okved"]["code"]
                    subsidy_rate = 1.0 if main_okved_code in MEDICAL_FOOD_OKVEDS else (0.7 if is_priority else 0.5)
                    subsidy_amount = subsidy_rate * (ks / 100) * credit_limit
                    result["analysis_data"]["subsidy_rate"] = subsidy_rate
                    result["analysis_data"]["calculated_subsidy"] = subsidy_amount
                    result["analysis_data"]["subsidy_text"] = f"**{subsidy_amount:,.2f} рублей**.".replace(",", " ")

        check_log.append("Шаг 3: Проверка соответствия ОКВЭД требованиям программы.")
        if not matched_codes:
            reason = "Ни один из ОКВЭД компании не соответствует требованиям программы."
            result.update({"passed": False, "reason": reason, "check_log": check_log})
            return result
        check_log.append(f"✅ РЕЗУЛЬТАТ: Найдены соответствующие ОКВЭД: {', '.join(matched_codes)}.")

        check_log.append("Шаг 4: Проверка доли иностранных учредителей из офшорных зон.")
        founders_data = full_cheko_data.get("founders_data", [])
        foreign_share = sum(float(re.search(r"(\d+[.,]?\d*)\s*%", line).group(1).replace(",", ".")) for line in founders_data if "Россия" not in line and any(c in line for c in ["Кипр", "Сейшелы", "Белиз"]) and re.search(r"(\d+[.,]?\d*)\s*%", line))
        if foreign_share > 25.0:
            reason = f"Доля иностранных учредителей из офшорных зон превышает 25% ({foreign_share}%)."
            result.update({"passed": False, "reason": reason, "check_log": check_log})
            return result
        check_log.append(f"✅ РЕЗУЛЬТАТ: Доля офшоров ({foreign_share}%) не превышает 25%.")

        manual_steps_text = "- Предоставить в банк справки: об отсутствии задолженности (ФНС), о статусе сельхозтоваропроизводителя (форма 6-АПК).\n"
        manual_steps_text += f"- Расчетный размер годовой субсидии: {result['analysis_data']['subsidy_text']}"
        if company_okved_codes.intersection(ALLOWED_OKVEDS_CLARIFICATION):
            manual_steps_text += f"\n- **ВАЖНО:** Обнаружен ОКВЭД `{next(iter(company_okved_codes.intersection(ALLOWED_OKVEDS_CLARIFICATION)))}`, который может потребовать доп. согласования."
        manual_steps_text += "\n\nДополнительно: Подробнее с направлениями целевого использования можно ознакомиться по [ссылке](https://mcx.gov.ru/activity/state-support/measures/preferential-credit/)."
        
        result.update({
            "passed": True,
            "calculated_conditions": result['analysis_data']['rate_text'],
            "manual_steps": manual_steps_text,
            "check_log": check_log,
        })
        return result

    except Exception as e:
        logging.error(f"{log_prefix} Непредвиденная ошибка: {e}", exc_info=True)
        check_log.append(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        result.update({"passed": False, "reason": f"Внутренняя ошибка при проверке: {e}", "check_log": check_log})
        return result
