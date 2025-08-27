# Файл: programs/belarus.py (ИСПРАВЛЕННАЯ ВЕРСИЯ С BASE_CONDITIONS)

import logging
import asyncio
from parser import egrul, full_cheko, cb # Эти импорты остаются, т.к. мы работаем с готовым досье

# Списки остаются без изменений
FORBIDDEN_OKVED_CODES = [
    "64.91", "77.1", "77.31", "77.32", "77.33", "77.34", "77.35", "77.39", "77.40",
]

# --- ИЗМЕНЕНИЕ 1: Добавляем блок с базовыми условиями ---
# Это общая информация о программе, которая не зависит от клиента.
BASE_CONDITIONS_TEXT = """
- **Цели кредита:** Приобретение товаров, произведенных в Республике Беларусь (техника, оборудование и т.д.).
- **Сумма кредита:** До 90% от стоимости товара. Для продукции ОАО «БЕЛАЗ» - до 70%.
- **Валюта и срок:** Кредит выдается в рублях РФ на срок до 5 лет.
- **Общий принцип ставки:** Ставка для заемщика субсидируется Правительством Республики Беларусь, что делает ее значительно ниже рыночной.
"""

# <<< ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ПОЛНОСТЬЮ >>>
async def check_belarus_program(company_dossier: dict) -> dict:
    inn = company_dossier.get("inn", "N/A")
    log_prefix = f"[Беларусь, ИНН {inn}]"
    check_log = []
    
    result = {
        "program_name": "Программа поддержки 'Беларусь'",
        "base_conditions": BASE_CONDITIONS_TEXT,
        # Создаем словарь для хранения всех расчетных данных, который будет доступен всегда
        "analysis_data": {}
    }

    try:
        # --- ШАГ 1 (НОВЫЙ): Ранний расчет ставки ---
        # Этот блок выполняется всегда, до основных проверок
        check_log.append("Шаг 1: Расчет потенциальной ставки на основе ключевой ставки ЦБ.")
        key_rate_str = company_dossier.get("cbr_key_rate")
        key_rate_date = company_dossier.get("cbr_key_rate_date")

        rate_calculation_text = "Не удалось рассчитать ставку (нет данных от ЦБ)."
        if key_rate_str and key_rate_date:
            try:
                ks = float(key_rate_str.replace(",", "."))
                max_rate = ks + 3.0
                subsidy = (2/3) * ks
                final_rate = max_rate - subsidy
                rate_calculation_text = (
                    f"Ваша процентная ставка рассчитывается от Ключевой Ставки ЦБ ({ks:.2f}% на {key_rate_date}).\n"
                    f"• Максимальная ставка по кредиту: {max_rate:.2f}%.\n"
                    f"• Республика Беларусь компенсирует ≈{subsidy:.2f}%.\n"
                    f"• **Ваша итоговая эффективная ставка: ≈{final_rate:.2f}% годовых.**\n"
                    f"(Примечание: для 'Гомсельмаш' и 'МТЗ' субсидия - 3/4 от КС)."
                )
                result["analysis_data"]["final_rate"] = final_rate # Сохраняем числовое значение
                check_log.append("✅ РЕЗУЛЬТАТ: Потенциальная ставка успешно рассчитана.")
            except (ValueError, TypeError):
                check_log.append("❌ РЕЗУЛЬТАТ: Не удалось преобразовать полученную ставку ЦБ в число.")
        else:
            check_log.append("❌ РЕЗУЛЬТАТ: Данные о ключевой ставке отсутствуют в досье.")
        
        # Сохраняем текстовое описание ставки в любом случае
        result["analysis_data"]["rate_text"] = rate_calculation_text

        # --- ШАГ 2: Проверка в ЕГРЮЛ ---
        check_log.append("Шаг 2: Проверка наличия компании в ЕГРЮЛ.")
        if not company_dossier.get("is_in_egrul"):
            check_log.append("❌ РЕЗУЛЬТАТ: Компания не найдена в ЕГРЮЛ.")
            result.update({
                "passed": False,
                "reason": "Компания не найдена в Едином государственном реестре юридических лиц.",
                "check_log": check_log,
            })
            return result # Возвращаем result, который уже содержит analysis_data
        check_log.append("✅ РЕЗУЛЬТАТ: Компания найдена в ЕГРЮЛ.")

        # --- ШАГ 3: Проверка ОКВЭД ---
        check_log.append("Шаг 3: Анализ видов деятельности (ОКВЭД).")
        okved_data = company_dossier.get("full_cheko_data", {}).get("okved_data")
        
        if not okved_data or not okved_data.get("main_okved"):
            check_log.append("❌ РЕЗУЛЬТАТ: Данные по ОКВЭД отсутствуют в досье компании.")
            result.update({
                "passed": False,
                "reason": "Не удалось получить данные по ОКВЭД.",
                "check_log": check_log,
            })
            return result

        main_okved = okved_data["main_okved"]
        additional_okveds = okved_data.get("additional_okved", [])

        # Проверка основного ОКВЭД
        if any(main_okved['code'].startswith(forbidden) for forbidden in FORBIDDEN_OKVED_CODES):
            reason = f"Основной вид деятельности ({main_okved['code']} - {main_okved['name']}) несовместим с программой (связан с лизингом/арендой)."
            check_log.append(f"❌ РЕЗУЛЬТАТ: {reason}")
            result.update({"passed": False, "reason": reason, "check_log": check_log})
            return result

        # Проверка дополнительных ОКВЭД
        for okved in additional_okveds:
            if any(okved['code'].startswith(forbidden) for forbidden in FORBIDDEN_OKVED_CODES):
                reason = f"Обнаружен дополнительный ОКВЭД ({okved['code']} - {okved['name']}), связанный с лизингом/арендой."
                check_log.append(f"❌ РЕЗУЛЬТАТ: {reason}")
                result.update({
                    "passed": False,
                    "reason": reason,
                    "recommendation": "Для участия в программе рассмотрите возможность исключения данного вида деятельности из ЕГРЮЛ.",
                    "check_log": check_log,
                })
                return result
        check_log.append("✅ РЕЗУЛЬТАТ: В видах деятельности не найдено запрещенных кодов.")

        # --- ШАГ 4: Формирование УСПЕШНОГО ответа ---
        # Все проверки пройдены
        calculated_conditions_text = (
            f"- Цели кредита: Приобретение товаров, произведенных в Республике Беларусь.\n"
            f"- Сумма кредита: До 90% от стоимости товара (до 70% для ОАО «БЕЛАЗ»).\n"
            f"- Валюта и срок: Рубли РФ, до 5 лет.\n"
            # Используем уже рассчитанный текст ставки из analysis_data
            f"- Льготная процентная ставка:\n{result['analysis_data']['rate_text']}"
        )
        manual_steps_text = (
            "- Необходимо получить от производителя письмо-подтверждение сделки с VIN/серийным номером товара.\n"
            "- Помните, что по одному VIN/серийному номеру кредит по программе не может быть оформлен дважды."
        )

        result.update({
            "passed": True,
            "calculated_conditions": calculated_conditions_text,
            "manual_steps": manual_steps_text,
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
        })
        return result