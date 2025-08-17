# main.py (ФИНАЛЬНАЯ ВЕРСИЯ С УМНЫМ РАЗРЕЗАНИЕМ И ЭКРАНИРОВАНИЕМ)
import logging
import asyncio
import re
from telegram import Update, constants
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from src.dialogue.dialogue_manager import DialogueManager
from src.config import settings, setup_logging_globally

# --- Настройки и инициализация ---
setup_logging_globally()
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
dialogue_manager = DialogueManager()

# --- Вспомогательные функции ---

def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown V2, которые могут сломать парсинг.
    """
    # \ должен экранироваться первым
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    # Создаем регулярное выражение для поиска любого из этих символов
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


async def send_long_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    """
    Отправляет длинное сообщение, безопасно разрезая его и экранируя Markdown.
    """
    MAX_LENGTH = constants.MessageLimit.MAX_TEXT_LENGTH
    
    # Сразу экранируем весь текст. Это безопасно, так как GigaChat не использует Markdown.
    # Если бы вы сами вставляли *жирный* текст, экранировать нужно было бы по-другому.
    safe_text = escape_markdown(text)
    
    if len(safe_text) <= MAX_LENGTH:
        try:
            await update.message.reply_text(safe_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
        except BadRequest as e:
            logger.error(f"Ошибка отправки короткого сообщения: {e}. Текст: {safe_text[:200]}")
            # Отправляем без форматирования как запасной вариант
            await update.message.reply_text("Возникла ошибка при форматировании ответа. Отправляю текст без разметки:\n\n" + text)
        return

    parts = []
    while len(safe_text) > 0:
        # Если оставшийся текст помещается в одно сообщение, добавляем его и выходим
        if len(safe_text) <= MAX_LENGTH:
            parts.append(safe_text)
            break

        # Ищем лучшее место для разрыва, предпочтительно по двойному переносу строки
        cut_off = safe_text.rfind("\n\n", 0, MAX_LENGTH)
        if cut_off == -1:
            # Если не нашли двойной перенос, ищем одинарный
            cut_off = safe_text.rfind("\n", 0, MAX_LENGTH)
        
        if cut_off == -1:
            # Если даже переносов нет, режем по последнему пробелу
            cut_off = safe_text.rfind(" ", 0, MAX_LENGTH)

        if cut_off == -1:
            # В крайнем случае, режем по максимальной длине
            cut_off = MAX_LENGTH

        parts.append(safe_text[:cut_off])
        safe_text = safe_text[cut_off:].lstrip()

    logger.info(f"Сообщение разделено на {len(parts)} частей.")
    for i, part in enumerate(parts):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=part,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
            )
            # Небольшая задержка между сообщениями, чтобы не спамить
            if i < len(parts) - 1:
                await asyncio.sleep(0.5)
        except BadRequest as e:
            logger.error(f"Ошибка отправки части {i+1}/{len(parts)}: {e}. Текст части: {part[:200]}")
            # Отправляем проблемную часть без форматирования
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Проблема с форматированием этой части. Отправляю как есть:\n\n" + text[sum(len(p) for p in parts[:i]):][:len(part)]
            )


# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Здравствуйте, {user_name}!\n\n"
        "Я ваш финансовый ассистент. Отправьте мне ИНН компании для комплексного анализа."
    )
    await update.message.reply_text(welcome_message)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_id = str(update.effective_user.id)
    user_text = update.message.text
    logger.info(f"Получен запрос от {user_id}: '{user_text}'")

    inn_match = re.search(r"(\b\d{10}\b|\b\d{12}\b)", user_text)
    if inn_match:
        await update.message.reply_text(
            "🔎 Начинаю комплексный анализ... Это может занять несколько минут, пожалуйста, ожидайте."
        )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING
    )

    response_text = await dialogue_manager.handle_message(user_id, user_text)

    logger.info(f"Отправка ответа пользователю {user_id}: '{response_text[:120]}...'")
    await send_long_message(update, context, response_text)


def run_bot() -> None:
    """Запускает бота."""
    logger.info("Запуск Telegram-бота...")
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчик ошибок
    # application.add_error_handler(error_handler) # Вы можете создать свою функцию error_handler
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    
    logger.info("Бот запущен и готов к работе. Нажмите Ctrl+C для остановки.")
    application.run_polling()


if __name__ == "__main__":
    run_bot()