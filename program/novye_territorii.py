# programs/novye_territorii.py (ИСПРАВЛЕННАЯ ВЕРСИЯ С BASE_CONDITIONS)
import logging
import asyncio
from parser import cb
from parser.nt import get_sez_inns

# Кэш для хранения списка ИНН
_cached_sez_inns = None

async def _get_sez_inns_cached() -> set:
    """Вспомогательная функция для получения и кэширования списка ИНН."""
    global _cached_sez_inns
    if _cached_sez_inns is None:
        logging.info("[Кэш СЭЗ] Кэш пуст, запускаю парсер nt.get_sez_inns...")
        _cached_sez_inns = await asyncio.to_thread(get_sez_inns)
        if _cached_sez_inns is None:
            _cached_sez_inns = set()
            logging.error("[Кэш СЭЗ] Парсер nt.get_sez_inns вернул ошибку. Кэш остался пустым.")
        else:
            logging.info(f"[Кэш СЭЗ] Кэш успешно заполнен. Найдено {len(_cached_sez_inns)} ИНН.")
    return _cached_sez_inns

# --- ИЗМЕНЕНИЕ 1: Добавляем блок с базовыми условиями ---
BASE_CONDITIONS_TEXT = """
- **Цели кредита:** Реализация инвестиционных проектов на территориях СЭЗ (ДНР, ЛНР, Запорожская и Херсонская области). До 20% от суммы кредита можно направить на пополнение оборотных средств.
- **Сумма кредита:** От 1 миллиона до 5 миллиардов рублей.
- **Срок:** До 5 лет.
- **Общий принцип ставки:** Плавающая ставка, привязанная к Ключевой ставке ЦБ, но с государственной субсидией, значительно снижающей итоговую стоимость кредита для заемщика.
- **Основное требование:** Компания должна быть участником свободной экономической зоны (СЭЗ).
"""

# <<< ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ПОЛНОСТЬЮ >>>
async def check_novye_territorii_program(company_dossier: dict) -> dict:
    inn = company_dossier.get("inn", "N/A")
    log_prefix = f"[Новые территории, ИНН {inn}]"
    check_log = []
    # --- ИЗМЕНЕНИЕ 2: Всегда начинаем с базового словаря ---
    result = {
        "program_name": "Программа 'Новые территории' (СЭЗ)",
        "base_conditions": BASE_CONDITIONS_TEXT,
    }

    try:
        # Шаг 1: Проверка в реестре СЭЗ
        check_log.append("Шаг 1: Проверка нахождения компании в Едином реестре участников СЭЗ.")
        
        sez_inns_set = await _get_sez_inns_cached()
        is_in_registry = inn in sez_inns_set

        if not is_in_registry:
            check_log.append("❌ РЕЗУЛЬТАТ: Компания не найдена в реестре СЭЗ.")
            result.update({
                "passed": False,
                "reason": "Компания не найдена в едином реестре участников свободной экономической зоны (СЭЗ).",
                "check_log": check_log,
                "calculated_conditions": None
            })
            return result
        check_log.append("✅ РЕЗУЛЬТАТ: Компания найдена в реестре СЭЗ.")

        # Шаг 2: Расчет ставки
        check_log.append("Шаг 2: Расчет льготной ставки на основе ключевой ставки ЦБ.")
        key_rate_str = company_dossier.get("cbr_key_rate")
        key_rate_date = company_dossier.get("cbr_key_rate_date")
        
        rate_calculation_text = "Не удалось рассчитать ставку (нет данных от ЦБ)."
        if key_rate_str and key_rate_date:
            try:
                ks = float(key_rate_str.replace(",", "."))
                standard_rate, refund_rate = ks + 4.0, min(ks, 10.0)
                final_rate = standard_rate - refund_rate
                rate_calculation_text = (
                    f"Ваша ставка является плавающей.\n"
                    f"• Стандартная ставка: {ks:.2f}% (КС на {key_rate_date}) + 4.00% = {standard_rate:.2f}%.\n"
                    f"• Государство возмещает {refund_rate:.2f}% (в размере КС, но не более 10%).\n"
                    f"• **Ваша итоговая ставка: {final_rate:.2f}% годовых.**"
                )
                check_log.append(f"✅ РЕЗУЛЬТАТ: Ставка успешно рассчитана.")
            except (ValueError, TypeError):
                check_log.append("❌ РЕЗУЛЬТАТ: Не удалось преобразовать ставку ЦБ в число.")
        else:
             check_log.append("❌ РЕЗУЛЬТАТ: Данные о ключевой ставке отсутствуют в досье.")

        # --- Формирование УСПЕШНОГО ответа ---
        calculated_conditions_text = (
            f"- Цели кредита: Реализация инвестпроекта в СЭЗ (до 20% на оборотные средства).\n"
            f"- Сумма кредита: От 1 млн до 5 млрд рублей.\n"
            f"- Срок: до 5 лет.\n"
            f"- Льготная процентная ставка:\n{rate_calculation_text}"
        )
        manual_steps_text = (
            "- НЕОБХОДИМО ПРЕДОСТАВИТЬ действующий договор об условиях деятельности в СЭЗ.\n"
            "- Необходимо соответствовать требованиям Программы Фонда развития территорий (ФРТ)."
        )

        result.update({
            "passed": True,
            "calculated_conditions": calculated_conditions_text, # --- ИЗМЕНЕНИЕ 3: Переименовываем ключ
            "manual_steps": manual_steps_text,
            "check_log": check_log,
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