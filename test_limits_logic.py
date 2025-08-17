# test_limits_logic.py

import asyncio
import unittest.mock
import logging

# Настраиваем логирование, чтобы видеть, что происходит внутри
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Важно: Убедитесь, что эти импорты соответствуют структуре вашего проекта
from src.dialogue.dialogue_manager import DialogueManager

# --- ШАГ 1: ГОТОВИМ ФЕЙКОВЫЕ ДАННЫЕ (ИМИТАЦИЯ ПАРСЕРОВ) ---

# Это имитация ответа от парсера PDF (msx_limit.py).
# Он вернет эти данные мгновенно, вместо реального скачивания и парсинга.
MOCK_LIMITS_DATA = {
    "Российская Федерация": {"Краткосрочное кредитование": 5000000000.0},
    "Тамбовская область": {
        "Краткосрочное кредитование": 223149714.73,
        "Малые формы": 43389288.91,
        "Растениеводство": 160550499.71,
        "Животноводство": 0.0,  # Нулевые лимиты должны быть проигнорированы в ответе
        "Переработка продукции растениеводства и животноводства": 9639141.47,
        "Молочное скотоводство": 7539713.88,
    },
    "Воронежская область": {
        "Краткосрочное кредитование": 231200468.87,
        "Растениеводство": 106393137.62,
    },
}

# Это имитация ответа от GigaChat NLU. Мы "заставляем" его всегда
# правильно определять намерение, чтобы протестировать именно нашу логику.
MOCK_NLU_RESULT = {
    "intent": "query_msh_limits",
    "entities": {},  # Сущности пусты, т.к. пользователь не указал регион в тексте
}


# --- ШАГ 2: ОСНОВНАЯ ТЕСТОВАЯ ФУНКЦИЯ ---


async def run_test():
    """
    Запускает изолированный тест логики обработки лимитов.
    """
    print("\n--- ЗАПУСК ТЕСТА ЛОГИКИ ЛИМИТОВ МСХ ---\n")

    # 1. Создаем экземпляр нашего менеджера диалогов
    dialogue_manager = DialogueManager()

    # 2. Создаем фейковый контекст (state), как будто пользователь уже ввел ИНН
    #    и мы определили его регион как "Тамбовская область".
    user_id = "test_user_123"
    state = dialogue_manager.get_or_create_state(user_id)
    state["current_inn"] = "6829052587"  # ИНН из Тамбовской области
    state["company_name"] = "Тестовая Компания 'Агро-Тамбов'"
    state["company_region"] = "Тамбовская область"  # <-- Самая важная часть!
    state["history"] = []

    # 3. Сообщение, которое "отправит" пользователь
    user_text = "какие лимиты по мсх?"

    # 4. Используем "магию" unittest.mock для временной подмены реальных функций
    #    на наши фейковые. `patch` работает как временная "заглушка".
    with unittest.mock.patch(
        "src.dialogue.dialogue_manager.get_msh_limits_data",
        new=unittest.mock.AsyncMock(return_value=MOCK_LIMITS_DATA),
    ) as mock_get_limits, unittest.mock.patch.object(
        dialogue_manager.giga_nlu,
        "extract_intent_and_entities",
        return_value=MOCK_NLU_RESULT,
    ) as mock_nlu:

        print(
            f"1. Пользователь '{user_id}' (из региона: {state['company_region']}) отправляет сообщение: '{user_text}'"
        )

        # 5. Вызываем основной обработчик, который мы хотим протестировать
        response = await dialogue_manager.handle_message(user_id, user_text)

        print("\n2. Проверяем, что наши 'заглушки' были вызваны:")
        mock_nlu.assert_called_once()
        print("   - NLU был вызван для определения намерения. [OK]")
        mock_get_limits.assert_called_once()
        print("   - Функция получения лимитов была вызвана. [OK]")

        print("\n3. Полученный ответ от бота:")
        print("--------------------------------")
        print(response)
        print("--------------------------------")

        # 6. Проверяем результат
        print("\n4. Автоматическая проверка ответа:")
        assert "Тамбовская область" in response
        print("   - В ответе упоминается правильный регион из контекста. [OK]")
        assert "160 550 499.71" in response
        print("   - В ответе содержатся правильные цифры из фейковых данных. [OK]")
        assert "Животноводство" not in response
        print("   - В ответе отсутствует направление с нулевым лимитом. [OK]")

        print("\n--- ТЕСТ УСПЕШНО ПРОЙДЕН! ---\n")


# --- ШАГ 3: ЗАПУСК АСИНХРОННОГО ТЕСТА ---

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except Exception as e:
        print(f"\n--- ТЕСТ ПРОВАЛЕН! ОШИБКА: {e} ---")
        # Выводим traceback для детальной отладки
        import traceback

        traceback.print_exc()
