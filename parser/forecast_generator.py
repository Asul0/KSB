import json
import os

# --- ШАГ 1: ЗАГРУЗКА ДАННЫХ ИЗ ФАЙЛОВ ---


def load_data_from_json(file_path: str) -> list | dict:
    """Универсальная функция для загрузки JSON-файла."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Файл '{file_path}' не найден.")
        return None
    except json.JSONDecodeError:
        print(
            f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось прочитать файл '{file_path}'. Проверьте его содержимое."
        )
        return None


# --- ИЗМЕНЕНИЕ: Указываем правильные пути к файлам относительно скрипта ---
# Скрипт находится в 'parser', данные - в 'data'. Путь '../data/' означает "подняться на уровень выше и зайти в папку data".
base_dir = os.path.dirname(
    os.path.abspath(__file__)
)  # Папка, где лежит скрипт (parser)
okved_file_path = os.path.join(base_dir, "..", "data", "msh_okveds.json")
forecast_file_path = os.path.join(base_dir, "..", "data", "price_forecasts.json")

OKVED_CATEGORIES = load_data_from_json(okved_file_path)
PRICE_FORECAST_DATA = load_data_from_json(forecast_file_path)


# --- ШАГ 2: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (остаются без изменений) ---


def find_category_by_okved(okved_code: str) -> str | None:
    """Находит название категории по коду ОКВЭД."""
    if not OKVED_CATEGORIES:
        return None
    for item in OKVED_CATEGORIES:
        if okved_code in item.get("codes", []):
            return item["category"]
    return None


def get_forecast_for_category(category_name: str) -> dict | None:
    """Находит прогнозы для указанной категории."""
    if not PRICE_FORECAST_DATA:
        return None
    for item in PRICE_FORECAST_DATA:
        if item["подотрасль"] == category_name:
            return item
    return None


def calculate_percentage_change(current_price: float, previous_price: float) -> str:
    """Рассчитывает процентное изменение и форматирует строку."""
    if previous_price is None or previous_price == 0:
        return ""

    change = ((current_price / previous_price) - 1) * 100
    sign = "+" if change >= 0 else ""  # Ставим '+' даже для 0.0%
    return f"({sign}{change:.1f}% к АППГ)"


# --- ШАГ 3: ГЛАВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ САММАРИ (остается без изменений) ---


def generate_price_forecast(okved_code: str) -> str:
    """
    Основная функция-оркестратор. Принимает ОКВЭД и возвращает готовое саммари.
    """
    category_name = find_category_by_okved(okved_code)
    if not category_name:
        return f"Для кода ОКВЭД '{okved_code}' не найдена соответствующая категория прогнозов."

    print(f"INFO: Найдена категория: '{category_name}'")

    forecast_data = get_forecast_for_category(category_name)
    if not forecast_data or not forecast_data.get("продукты"):
        return f"Для категории '{category_name}' прогнозы цен не найдены."

    products_to_report = forecast_data["продукты"]
    source = products_to_report[0]["источник"]

    summary_parts = []
    years = ["2026", "2027"]

    for product in products_to_report:
        product_name = product["наименование"]
        unit = product["ед_измерения"]

        year_forecasts = []
        for year in years:
            current_year_str = str(year)
            prev_year_str = str(int(year) - 1)

            current_price = product["прогноз"].get(current_year_str)
            prev_price = product["прогноз"].get(prev_year_str)

            if current_price is not None:
                change_str = (
                    calculate_percentage_change(current_price, prev_price)
                    if prev_price is not None
                    else ""
                )
                year_forecasts.append(
                    f"{current_year_str} - {current_price} {unit} {change_str}".strip()
                )

        if year_forecasts:
            summary_parts.append(f"{product_name} " + ", ".join(year_forecasts))

    if not summary_parts:
        return f"Не удалось сформировать прогноз для категории '{category_name}'."

    final_summary = (
        f"По данным {source} прогнозируются цены на: " + "; ".join(summary_parts) + "."
    )
    return final_summary


# --- ШАГ 4: ИНТЕРАКТИВНЫЙ РЕЖИМ ДЛЯ ТЕСТИРОВАНИЯ ---

if __name__ == "__main__":
    print("--- Тестовый генератор прогнозов по ОКВЭД ---")

    if not OKVED_CATEGORIES or not PRICE_FORECAST_DATA:
        print(
            "\nОШИБКА ЗАГРУЗКИ ДАННЫХ. Проверьте сообщения об ошибках выше и перезапустите скрипт."
        )
    else:
        print(
            f"Справочник ОКВЭД ({len(OKVED_CATEGORIES)} кат.) и прогнозы ({len(PRICE_FORECAST_DATA)} кат.) успешно загружены."
        )
        print("Введите код ОКВЭД (например, 10.41.1) или 'exit' для выхода.")

        while True:
            try:
                input_okved = input("\nВведите ОКВЭД: ").strip()

                if input_okved.lower() == "exit":
                    print("Завершение работы.")
                    break

                if not input_okved:
                    continue

                result_summary = generate_price_forecast(input_okved)

                print("\n--- РЕЗУЛЬТАТ ---")
                print(result_summary)
                print("-----------------")

            except KeyboardInterrupt:
                print("\n\nПрограмма остановлена пользователем.")
                break
            except Exception as e:
                print(f"\nПроизошла непредвиденная ошибка: {e}")
