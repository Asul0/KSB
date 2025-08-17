# test_interactive_msh_logic.py
"""
Интерактивный тестовый скрипт для проверки логики обработки лимитов МСХ.

ЧТО ДЕЛАЕТ ЭТОТ СКРИПТ:
1. Запускает DialogueManager.
2. Запрашивает у пользователя ИНН компании для анализа.
3. Выполняет ПОЛНЫЙ анализ, включая запуск всех парсеров (Cheko, РИА, Агроинвестор, МСХ Лимиты).
4. Выводит первоначальный отчет.
5. Входит в интерактивный режим, где можно задавать уточняющие вопросы
   ассистенту, особенно по лимитам МСХ, и проверять его ответы в реальном времени.

КАК ЗАПУСТИТЬ:
1. Поместите этот файл в КОРНЕВУЮ ДИРЕКТОРИЮ вашего проекта.
2. Убедитесь, что все зависимости установлены.
3. Убедитесь, что во все затронутые файлы (dialogue_manager.py, programs/mskh.py)
   внесены изменения, описанные в инструкции.
4. Запустите из терминала командой: python test_interactive_msh_logic.py
"""
import asyncio
import logging
import os
import sys

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from src.dialogue.dialogue_manager import DialogueManager
except ImportError as e:
    print("=" * 80)
    print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать DialogueManager.")
    print(f"Ошибка: {e}")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(module)s - %(message)s"
)
# Уменьшаем "шум" от selenium
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)


async def main():
    """
    Основная асинхронная функция для интерактивного теста.
    """
    print("=" * 80)
    print(">>> Инициализация DialogueManager для ИНТЕРАКТИВНОГО тестирования...")
    print("=" * 80)

    manager = DialogueManager()
    user_id = "interactive_test_user_001"

    # --- Шаг 1: Получение ИНН от пользователя ---
    inn = input(">>> Пожалуйста, введите ИНН компании для анализа: ").strip()
    if not (inn.isdigit() and len(inn) in [10, 12]):
        print("Ошибка: Введен некорректный ИНН. Завершение работы.")
        return

    print("\n" + "=" * 80)
    print(
        f">>> Запускаю полный анализ для ИНН: {inn}. Это может занять несколько минут..."
    )
    print(">>> Ожидайте, идет сбор данных из всех источников...")
    print("=" * 80)

    # --- Шаг 2: Выполнение полного анализа ---
    initial_response = await manager.handle_message(user_id, inn)
    print("\n[АССИСТЕНТ - ПЕРВИЧНЫЙ ОТЧЕТ]:")
    print("-" * 40)
    print(initial_response)
    print("-" * 40)

    # --- Шаг 3: Интерактивный диалог ---
    print("\n" + "=" * 80)
    print(">>> Анализ завершен. Теперь вы можете задавать уточняющие вопросы.")
    print(">>> Примеры вопросов по лимитам МСХ:")
    print("    - Расскажи подробнее про программу МСХ и ее лимиты")
    print("    - Какой кредит я могу получить по этой программе?")
    print("    - Сколько всего субсидий осталось в моем регионе?")
    print(">>> Для выхода из диалога введите 'выход' или 'exit'.")
    print("=" * 80)

    while True:
        try:
            query = input(f"\n[ВЫ -> АССИСТЕНТУ]: ")
            if query.lower() in ["выход", "exit"]:
                print(">>> Завершение сессии. До свидания!")
                break

            print(">>> Отправка запроса ассистенту... Ожидайте...")
            response = await manager.handle_message(user_id, query)

            print("\n[АССИСТЕНТ]:")
            print(response)

        except KeyboardInterrupt:
            print("\n>>> Сессия прервана пользователем. До свидания!")
            break
        except Exception as e:
            logging.critical(
                "Произошла критическая ошибка в цикле диалога.", exc_info=True
            )
            break


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
