# test_dialogue_logic.py

import pytest
from unittest.mock import patch, AsyncMock

# Импортируем наш главный класс для тестирования
from src.dialogue.dialogue_manager import DialogueManager

# --- МОДУЛЬ ДЛЯ ПОДГОТОВКИ ТЕСТОВЫХ ДАННЫХ ---
# Эти данные имитируют ответы от внешних сервисов (парсер Checko, новостные парсеры и т.д.)

# Имитация данных для компании из "стандартной" категории (Мясопереработка)
FAKE_COMPANY_DATA_MEAT = {
    "company_name": "ООО Мясной Дом",
    "general_info": {"address": "г. Москва"},
    "okved_data": {"main_okved": {"code": "10.13"}}, # Код ОКВЭД для мясопереработки
    "error": None
}

# Имитация данных для компании из категории-исключения (Растениеводство)
FAKE_COMPANY_DATA_PLANTS = {
    "company_name": "АО Агрофирма Поля",
    "general_info": {"address": "Воронежская область"},
    "okved_data": {"main_okved": {"code": "01.11"}}, # Код ОКВЭД для растениеводства
    "error": None
}

# Имитация ответа от парсера Агроинвестора
FAKE_AGRO_NEWS = {
    "status": "success",
    "data": [
        {"title": "Заголовок новости Агроинвестора 1", "summary": "Краткое содержание 1", "full_article_url": "http://..."},
        {"title": "Заголовок новости Агроинвестора 2", "summary": "Краткое содержание 2", "full_article_url": "http://..."}
    ]
}

# Имитация ответа от парсера РИА Новости
FAKE_RIA_NEWS = {
    "status": "success",
    "data": [
        {"title": "Заголовок новости РИА 1", "full_article_url": "http://..."},
        {"title": "Заголовок новости РИА 2", "full_article_url": "http://..."}
    ]
}

# Имитация ответа от анализатора госпрограмм
FAKE_PROGRAMS_REPORT = {
    "passed": [{"program_name": "Программа X", "calculated_conditions": "Условия Y"}],
    "fixable": [],
    "failed": []
}

# --- НАЧАЛО ТЕСТОВ ---

@pytest.fixture
def manager():
    """Эта функция создает экземпляр DialogueManager перед каждым тестом."""
    # Здесь важно: предполагается, что ваш JSON-файл с аналитикой уже загружается
    # при инициализации DialogueManager или доступен ему.
    # Если это не так, здесь нужно будет добавить его загрузку.
    return DialogueManager()

@pytest.mark.asyncio
@patch('src.dialogue.dialogue_manager.get_ria_news_async', new_callable=AsyncMock, return_value=FAKE_RIA_NEWS)
@patch('src.dialogue.dialogue_manager.get_latest_agro_news', new_callable=AsyncMock, return_value=FAKE_AGRO_NEWS)
@patch('src.dialogue.dialogue_manager.run_state_programs_check', new_callable=AsyncMock, return_value=FAKE_PROGRAMS_REPORT)
@patch('src.dialogue.dialogue_manager.get_company_data_by_inn_async', new_callable=AsyncMock)
async def test_parser_category_flow(mock_get_company, mock_programs, mock_agro_news, mock_ria_news, manager):
    """
    Тест-кейс TC-02: Проверяем категорию-исключение ('Растениеводство').
    Ожидаем, что будут вызваны старые парсеры новостей.
    """
    print("\n--- Запуск TC-02: Проверка категории-исключения (Растениеводство) ---")

    # Настраиваем мок-объект, чтобы он вернул данные по компании из сферы растениеводства
    mock_get_company.return_value = FAKE_COMPANY_DATA_PLANTS

    # === Шаг 1: Отправляем ИНН ===
    inn = "2222222222" # Тестовый ИНН для этой логики
    user_id = "user_plant"
    response = await manager.handle_message(user_id, inn)

    # === Шаг 2: Анализ результата ===
    # Проверяем, что в ответе есть заголовки из старых парсеров
    assert "САМОЕ ИНТЕРЕСНОЕ В АПК ЗА ПОСЛЕДНЕЕ ВРЕМЯ (Агроинвестор)" in response
    assert "АКТУАЛЬНЫЕ НОВОСТИ ПО ПРОГНОЗУ УРОЖАЯ (РИА Новости)" in response
    assert "Заголовок новости Агроинвестора 1" in response
    assert "Заголовок новости РИА 1" in response

    # Проверяем, что в ответе НЕТ блока с новой аналитикой
    assert "ОТРАСЛЕВОЙ АНАЛИТИЧЕСКИЙ ОБЗОР" not in response

    # Проверяем, что наши моки (имитаторы парсеров) были вызваны
    mock_agro_news.assert_awaited_once()
    mock_ria_news.assert_awaited_once()

    print("--- TC-02 Успешно пройден: Логика для категорий-исключений работает корректно. ---")


@pytest.mark.asyncio
@patch('src.dialogue.dialogue_manager.run_state_programs_check', new_callable=AsyncMock, return_value=FAKE_PROGRAMS_REPORT)
@patch('src.dialogue.dialogue_manager.get_company_data_by_inn_async', new_callable=AsyncMock)
async def test_standard_category_flow(mock_get_company, mock_programs, manager):
    """
    Тест-кейс TC-01: Проверяем стандартную категорию ('Мясопереработка').
    Ожидаем, что будет использована логика из JSON-файла с аналитикой.
    """
    print("\n--- Запуск TC-01: Проверка стандартной категории (Мясопереработка) ---")

    # Настраиваем мок-объект, чтобы он вернул данные по компании из сферы мясопереработки
    mock_get_company.return_value = FAKE_COMPANY_DATA_MEAT
    
    # === Шаг 1: Отправляем ИНН ===
    inn = "1111111111" # Тестовый ИНН
    user_id = "user_meat"
    
    # Здесь мы "подглядываем" за вызовами новостных парсеров, чтобы убедиться, что их НЕ было
    with patch('src.dialogue.dialogue_manager.get_latest_agro_news') as mock_agro_news, \
         patch('src.dialogue.dialogue_manager.get_ria_news_async') as mock_ria_news:
        
        response_level1 = await manager.handle_message(user_id, inn)

        # Проверяем, что парсеры НЕ вызывались
        mock_agro_news.assert_not_called()
        mock_ria_news.assert_not_called()

    # === Шаг 2: Анализ результата (Уровень 1 - короткая выжимка) ===
    assert "ОТРАСЛЕВОЙ АНАЛИТИЧЕСКИЙ ОБЗОР: МЯСОПЕРЕРАБОТКА" in response_level1
    # Проверяем наличие ключевых слов из короткого саммари
    assert "Государственная поддержка" in response_level1 
    assert "рост затрат" in response_level1
    # Проверяем, что это именно КОРОТКИЙ текст, а не вся статья
    assert "ТР ТС 034/2013" not in response_level1 # Фраза из полной статьи

    print("--- Уровень 1 (короткое саммари) пройден успешно. ---")

    # *** ВАЖНОЕ ПРИМЕЧАНИЕ ***
    # Для теста Уровня 2 (детальный ответ) нужно будет доработать DialogueManager.
    # Текущая функция _handle_news_details_query не подходит, нужна новая, например,
    # _handle_analytical_details_query, которая будет генерировать средний саммари.
    # Ниже приведен код, который будет работать ПОСЛЕ этой доработки.

    # === Шаг 3: Отправляем запрос на детализацию ===
    # Имитируем, что NLU распознал наше намерение
    mock_nlu_result = {"intent": "query_analytical_details", "entities": {}}
    
    with patch.object(manager.giga_nlu, 'extract_intent_and_entities', return_value=mock_nlu_result):
        # response_level2 = await manager.handle_message(user_id, "расскажи подробнее")
        pass # Пока заглушка, раскомментировать после доработки кода

    # === Шаг 4: Анализ результата (Уровень 2 - средний саммари) ===
    # assert "Техническом регламенте Таможенного союза" in response_level2 # Фраза из середины статьи
    # assert len(response_level2) > len(response_level1) # Ответ 2 должен быть длиннее ответа 1

    print("--- TC-01 Успешно пройден (частично): Логика для стандартных категорий работает. ---")
    print("--- ПРЕДУПРЕЖДЕНИЕ: Тест детального ответа (Уровень 2) требует доработки основного кода. ---")