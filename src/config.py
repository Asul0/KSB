import os
import logging


class Settings:
    LOG_LEVEL_CONSOLE = logging.INFO
    LOG_LEVEL_FILE = logging.DEBUG
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s - %(message)s"

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_FILE_PATH = os.path.join(BASE_DIR, "logs", "financial_bot.log")

    GIGACHAT_CREDENTIALS = os.getenv(
        "GIGACHAT_CREDENTIALS_FINBOT",
        "==",
    )
    GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE_FINBOT", "GIGACHAT_API_PERS")
    TELEGRAM_BOT_TOKEN = os.getenv(
        "TELEGRAM_BOT_TOKEN_FINBOT", ":AAHWgpLlydBFQDVJRKpzsjK7Juy7TcrAGPw"
    )

    INN_OKK_MAPPING_FILE_PATH = os.path.join(BASE_DIR, "data", "inn_okk_mapping.json")
    RECOMMENDATION_RULES_FILE_PATH = os.path.join(
        BASE_DIR, "data", "recommendation_rules.json"
    )
    STATE_PROGRAMS_FILE_PATH = os.path.join(BASE_DIR, "data", "state_programs.json")

    GIGACHAT_MODEL = (
        "GigaChat-Max"  # Попробуем Pro, он может быть стабильнее для сложных промптов
    )
    GIGACHAT_VERIFY_SSL_CERTS = False
    GIGACHAT_TIMEOUT = (
        60  # Уменьшил таймаут для GigaChat запросов, чтобы быстрее выявлять проблемы
    )
    GIGACHAT_PROFANITY_CHECK = False

    GIGACHAT_TEMPERATURE_EXTRACTION = 0.01
    GIGACHAT_MAX_TOKENS_EXTRACTION = 350  # Немного увеличил для очень сложных промптов

    GIGACHAT_TEMPERATURE_FORMATTING = 0.6
    GIGACHAT_MAX_TOKENS_FORMATTING = 550

    REDUCE_STRATEGY_SUGGESTIONS = [
        "переход на льготные программы кредитования в соответствии с рекомендациями",
        "внедрение продуктов цифровой трансформации, позволяющих увеличить рентабельность",
        "использование инструментов хеджирования процентной ставки",
        "замена инвестиционного кредитования займом в ФРП",
        "сокращение оборотного кредитования за счет наращивания кредиторской задолженности перед поставщиками, обеспечиваемой БГ исполнение обязательств по договору / выпуск ЦФА",
    ]


settings = Settings()


def setup_logging_globally():
    root_logger = logging.getLogger()
    effective_root_level = min(settings.LOG_LEVEL_CONSOLE, settings.LOG_LEVEL_FILE)
    if settings.LOG_FILE_PATH is None:
        effective_root_level = settings.LOG_LEVEL_CONSOLE
    root_logger.setLevel(effective_root_level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    formatter = logging.Formatter(settings.LOG_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.LOG_LEVEL_CONSOLE)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    if settings.LOG_FILE_PATH:
        log_dir = os.path.dirname(settings.LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except OSError as e:
                print(f"Error creating log directory {log_dir}: {e}")
        file_handler = logging.FileHandler(
            settings.LOG_FILE_PATH, mode="a", encoding="utf-8"
        )
        file_handler.setLevel(settings.LOG_LEVEL_FILE)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    for lib_logger_name in [
        "httpx",
        "httpcore",
        "telegram.ext",
        "telegram.bot",
        "gigachat",
        "apscheduler",
    ]:
        logging.getLogger(lib_logger_name).setLevel(logging.INFO)

    # <<< ДОБАВЬТЕ ЭТУ СТРОКУ >>>
    # Устанавливаем для pdfminer уровень логирования INFO, чтобы скрыть "спам" уровня DEBUG
    logging.getLogger("pdfminer").setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        f"Logging setup complete. Console: {logging.getLevelName(settings.LOG_LEVEL_CONSOLE)}, File: {settings.LOG_FILE_PATH} ({logging.getLevelName(settings.LOG_LEVEL_FILE) if settings.LOG_FILE_PATH else 'N/A'})."
    )
