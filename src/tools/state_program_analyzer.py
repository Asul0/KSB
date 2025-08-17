# src/tools/state_program_analyzer.py (ВЕРСИЯ С БЕЗОПАСНЫМ СБОРОМ ДОСЬЕ)

import asyncio
import logging
from typing import Dict, Any

# --- Импорты программ-проверщиков (без изменений) ---
from program import belarus, novye_territorii, mskh, prigranichye, sovmeshchennaya

# --- Импорты ВСЕХ необходимых парсеров (без изменений) ---
from parser import cb, egrul, msp_check, msx_limit
from parser.full_cheko import get_company_data_by_inn_async


logger = logging.getLogger(__name__)

# <<< ВОЗВРАЩАЕМ СЕМАФОР, НО ИСПОЛЬЗУЕМ ЕГО НА ЭТАПЕ СБОРА ДАННЫХ >>>
SELENIUM_SEMAPHORE = asyncio.Semaphore(1)

PROGRAM_CHECKERS = {
    "Программа поддержки 'Беларусь'": belarus.check_belarus_program,
    "Программа 'Новые территории' (СЭЗ)": novye_territorii.check_novye_territorii_program,
    "Программа льготного кредитования 'МСХ'": mskh.check_msh_program,
    "Программа 'КМСП Приграничье'": prigranichye.check_prigranichye_program,
    "МЭР-2025 'Совмещенная' (Комбо 2.0)": sovmeshchennaya.check_sovmeshchennaya_program,
}


# <<< ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ПОЛНОСТЬЮ >>>
async def _gather_company_dossier_async(inn: str) -> Dict[str, Any]:
    """
    (ФИНАЛЬНАЯ ВЕРСИЯ) Собирает досье. Selenium-задачи выполняются последовательно,
    остальные - параллельно.
    """
    logger.info(f"Начинаю централизованный и безопасный сбор досье для ИНН: {inn}")

    async def _safe_selenium_task(func, *args):
        async with SELENIUM_SEMAPHORE:
            logger.info(f"Запускаю Selenium-задачу: {func.__name__}")
            if asyncio.iscoroutinefunction(func):
                result = await func(*args)
            else:
                result = await asyncio.to_thread(func, *args)
            logger.info(f"Завершил Selenium-задачу: {func.__name__}")
            return result
    
    tasks = {
        # Задачи, использующие Selenium:
        "full_cheko_data": _safe_selenium_task(get_company_data_by_inn_async, inn),
        "is_in_egrul": _safe_selenium_task(egrul.check_inn_on_nalog_ru_selenium, inn),
        "msp_category": _safe_selenium_task(msp_check.get_msp_category, inn),
        
        # Легкие задачи, которые теперь не ждут Selenium:
        "cbr_rate_data": asyncio.to_thread(cb.get_cbr_key_rate),
        "msh_limits_data": asyncio.to_thread(msx_limit.get_subsidy_limits),
        # Проверка СЭЗ теперь вызывается и кэшируется внутри check_novye_territorii_program
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    dossier = {"inn": inn}
    task_keys = list(tasks.keys())
    for i, result in enumerate(results):
        key = task_keys[i]
        if isinstance(result, Exception):
            logger.error(f"Ошибка при сборе данных для '{key}': {result}")
            dossier[key] = None
        else:
            if key == "cbr_rate_data" and isinstance(result, tuple):
                dossier["cbr_key_rate"] = result[0]
                dossier["cbr_key_rate_date"] = result[1]
            else:
                dossier[key] = result
    
    logger.info(f"Полное досье для ИНН {inn} успешно собрано.")
    return dossier


# <<< Эта функция остается БЕЗ ИЗМЕНЕНИЙ, так как вся логика инкапсулирована выше >>>
async def run_state_programs_check(inn: str) -> Dict[str, Any]:
    logger.info(f"Запуск анализа по всем госпрограммам для ИНН: {inn}")
    
    company_dossier = await _gather_company_dossier_async(inn)
    
    tasks = []
    for name, checker_func in PROGRAM_CHECKERS.items():
        task = asyncio.create_task(checker_func(company_dossier))
        tasks.append((name, task))

    results = []
    for name, task in tasks:
        try:
            result = await task
            result["program_name"] = name
            results.append(result)
        except Exception as e:
            logger.error(f"Ошибка при проверке программы '{name}': {e}", exc_info=True)
            results.append({
                "program_name": name, "passed": False, "reason": f"Внутренняя ошибка: {e}",
            })

    report = {
        "passed": [res for res in results if res.get("passed")],
        "fixable": [res for res in results if not res.get("passed") and res.get("recommendation")],
        "failed": [res for res in results if not res.get("passed") and not res.get("recommendation")],
    }
    
    logger.info(f"Анализ госпрограмм для ИНН {inn} завершен.")
    return report