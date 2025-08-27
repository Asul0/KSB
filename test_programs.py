# Файл: test_programs.py

import asyncio
import json

# Импортируем все наши обновленные функции
from program.belarus import check_belarus_program
from program.mskh import check_msh_program
from program.novye_territorii import check_novye_territorii_program
from program.prigranichye import check_prigranichye_program
from program.sovmeshchennaya import check_sovmeshchennaya_program

# --- БЛОК 1: Подготовка тестовых данных (фейковые досье) ---

# Общие данные, которые будут во всех досье
COMMON_DATA = {
    "inn": "1234567890",
    "cbr_key_rate": "16,0",
    "cbr_key_rate_date": "20.07.2024",
    "is_in_egrul": True,
    "msp_category": "Малое предприятие"
}

# --- Данные для программы "БЕЛАРУСЬ" ---
DOSSIER_BELARUS_SUCCESS = {
    **COMMON_DATA,
    "full_cheko_data": {
        "okved_data": {
            "main_okved": {"code": "01.11", "name": "Выращивание зерновых"},
            "additional_okved": []
        }
    }
}

DOSSIER_BELARUS_FAIL_OKVED = {
    **COMMON_DATA,
    "full_cheko_data": {
        "okved_data": {
            "main_okved": {"code": "77.1", "name": "Аренда и лизинг"}, # Запрещенный ОКВЭД
            "additional_okved": []
        }
    }
}

# --- Данные для программы "МСХ" ---
DOSSIER_MSKH_SUCCESS = {
    **COMMON_DATA,
    "full_cheko_data": {
        "general_info": {"address": "394000, Воронежская область, г Воронеж..."},
        "okved_data": {
            "main_okved": {"code": "01.41", "name": "Разведение молочного крупного рогатого скота"}, # Приоритетный ОКВЭД
        },
        "founders_data": ["Учредитель: Иванов И.И. (Россия)"]
    }
}

DOSSIER_MSKH_FAIL_FOUNDER = {
    **COMMON_DATA,
    "full_cheko_data": {
        "general_info": {"address": "394000, Воронежская область, г Воронеж..."},
        "okved_data": {
            "main_okved": {"code": "01.41", "name": "Разведение молочного крупного рогатого скота"},
        },
        "founders_data": ["Учредитель: Компания ABC (Кипр), доля 51%"] # Офшорный учредитель
    }
}

# --- Данные для программы "НОВЫЕ ТЕРРИТОРИИ" ---
# Для этой программы нам нужно "замокать" (подменить) функцию-парсер
# Мы сделаем это прямо в тесте, чтобы не усложнять.
# Допустим, в реестре есть только ИНН "1111111111"

DOSSIER_NT_SUCCESS = {**COMMON_DATA, "inn": "1111111111"}
DOSSIER_NT_FAIL = {**COMMON_DATA, "inn": "2222222222"}


# --- Данные для программы "ПРИГРАНИЧЬЕ" ---
DOSSIER_PRIGRAN_SUCCESS = {
    **COMMON_DATA,
    "full_cheko_data": {
        "general_info": {"address": "308000, Белгородская область, г Белгород..."},
        "okved_data": {
            "main_okved": {"code": "10.71", "name": "Производство хлеба"},
        }
    }
}

DOSSIER_PRIGRAN_FAIL_REGION = {
    **COMMON_DATA,
    "full_cheko_data": {
        "general_info": {"address": "101000, г Москва..."}, # Неправильный регион
        "okved_data": {
            "main_okved": {"code": "10.71", "name": "Производство хлеба"},
        }
    }
}

# --- Данные для программы "СОВМЕЩЕННАЯ" ---
DOSSIER_SOVM_SUCCESS = {
    **COMMON_DATA,
    "msp_category": "Среднее предприятие",
    "full_cheko_data": {
        "okved_data": {
            "main_okved": {"code": "26.20", "name": "Производство компьютеров"}, # Разрешенный ОКВЭД
        }
    }
}

DOSSIER_SOVM_FAIL_NO_MSP = {
    **COMMON_DATA,
    "msp_category": None, # Нет в реестре МСП
    "full_cheko_data": {
        "okved_data": {
            "main_okved": {"code": "26.20", "name": "Производство компьютеров"},
        }
    }
}


# --- БЛОК 2: Функция для запуска и вывода тестов ---

async def run_tests():
    """Запускает все тесты и красиво выводит результаты."""
    
    # Вспомогательная функция для красивой печати
    def print_result_details(scenario, result):
        print(f"\n[{scenario}] passed: {result.get('passed')}")
        if not result.get('passed'):
            print(f"  Причина отказа: {result.get('reason')}")
        
        analysis_data = result.get('analysis_data', {})
        if analysis_data:
            print("  Содержимое 'analysis_data':")
            # Используем json.dumps для аккуратного форматирования словаря
            print(json.dumps(analysis_data, indent=4, ensure_ascii=False))
        else:
            print("  'analysis_data' отсутствует или пусто.")

    print("="*50)
    print("🚀 ЗАПУСК МОДУЛЬНЫХ ТЕСТОВ ДЛЯ ПРОГРАММ (ДЕТАЛЬНЫЙ ВЫВОД) 🚀")
    print("="*50)

    # --- ТЕСТ 1: Программа "Беларусь" ---
    print("\n--- 🇧🇾 Тестирование программы 'Беларусь' ---")
    result_ok = await check_belarus_program(DOSSIER_BELARUS_SUCCESS)
    print_result_details("УСПЕХ", result_ok)
    result_fail = await check_belarus_program(DOSSIER_BELARUS_FAIL_OKVED)
    print_result_details("ОТКАЗ", result_fail)

    # --- ТЕСТ 2: Программа "МСХ" ---
    print("\n\n--- 🌾 Тестирование программы 'МСХ' ---")
    result_ok = await check_msh_program(DOSSIER_MSKH_SUCCESS)
    print_result_details("УСПЕХ", result_ok)
    result_fail = await check_msh_program(DOSSIER_MSKH_FAIL_FOUNDER)
    print_result_details("ОТКАЗ", result_fail)

    # --- ТЕСТ 3: Программа "Новые территории" ---
    print("\n\n--- 🗺️  Тестирование программы 'Новые территории' ---")
    import program.novye_territorii as nt
    nt._get_sez_inns_cached = lambda: asyncio.sleep(0, result={"1111111111"})
    result_ok = await check_novye_territorii_program(DOSSIER_NT_SUCCESS)
    print_result_details("УСПЕХ", result_ok)
    result_fail = await check_novye_territorii_program(DOSSIER_NT_FAIL)
    print_result_details("ОТКАЗ", result_fail)
    
    # --- ТЕСТ 4: Программа "Приграничье" ---
    print("\n\n--- 🛡️  Тестирование программы 'Приграничье' ---")
    result_ok = await check_prigranichye_program(DOSSIER_PRIGRAN_SUCCESS)
    print_result_details("УСПЕХ", result_ok)
    result_fail = await check_prigranichye_program(DOSSIER_PRIGRAN_FAIL_REGION)
    print_result_details("ОТКАЗ", result_fail)

    # --- ТЕСТ 5: Программа "Совмещенная" ---
    print("\n\n--- ⚙️  Тестирование программы 'Совмещенная' ---")
    result_ok = await check_sovmeshchennaya_program(DOSSIER_SOVM_SUCCESS)
    print_result_details("УСПЕХ", result_ok)
    result_fail = await check_sovmeshchennaya_program(DOSSIER_SOVM_FAIL_NO_MSP)
    print_result_details("ОТКАЗ", result_fail)

    print("\n\n" + "="*50)
    print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ЗАВЕРШЕНЫ! 🎉")
    print("="*50)



if __name__ == "__main__":
    asyncio.run(run_tests())