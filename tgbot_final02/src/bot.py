from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import time
import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession # Import async SQLAlchemy

from config import get_settings
from plugin_loader import register_plugins
from models.init_db import init_db
from utils.plugin_settings import load_all_plugin_settings

# Импортируем настройки логирования
from logging_config import get_logger
logger = get_logger(__name__)


# Get bot token from config
settings = get_settings()
print(f"DEBUG: Token before Bot init: {settings.TELEGRAM_BOT_TOKEN[:10]}...{settings.TELEGRAM_BOT_TOKEN[-10:]} (length: {len(settings.TELEGRAM_BOT_TOKEN)})", flush=True)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# antiflood logic moved to src/plugins/antiflood_plugin.py — see plugin_loader for registration


@dp.message(Command("start"))
async def start_handler(message: Message):
    """Handle /start command."""
    # Start command received
    await message.answer("Бот запущен.")


@dp.message(Command("help"))
async def help_handler(message: Message):
    """Handle /help command."""
    # Help command received
    
    help_text = """🤖 <b>Доступные команды бота:</b>

<b>Основные команды:</b>
/start - Запуск бота
/help - Показать это сообщение
ping - Ответить "pong"

<b>Модерация (только для админов):</b>
/warn - Выдать предупреждение (ответ на сообщение)
/mute [минуты] - Замутить пользователя (ответ на сообщение, по умолчанию 10 мин)
/unmute - Размутить пользователя (ответ на сообщение)
/kick - Кикнуть пользователя (ответ на сообщение)
/ban - Забанить пользователя (ответ на сообщение)
/delete - Удалить сообщение (ответ или ID сообщения)

<b>Репутация:</b>
+ - Увеличить репутацию (ответ на сообщение)
- - Уменьшить репутацию (ответ на сообщение)
/rep - Показать репутацию (ответ на сообщение)
/top - Показать топ-5 пользователей по репутации

<b>Опросы:</b>
/poll Вопрос;Вариант1;Вариант2;... - Создать опрос с кнопками

<b>Реакции:</b>
👍 - Лайк (ответ на сообщение)
👎 - Дизлайк (ответ на сообщение)
/reactions - Показать реакции (ответ на сообщение)

<b>Автоматические функции:</b>
• Антифлуд - блокирует спам (5+ сообщений за 10 сек)
• Капча - проверка новых участников
• Черный список - фильтрация запрещенных слов/ссылок"""
    
    await message.answer(help_text, parse_mode="HTML")






async def main():
    """Main function to start the bot."""
    # Initializing database
    corrected_db_url = await init_db(settings.DATABASE_URL)

    # Centralized AsyncSessionLocal initialization
    async_engine = create_async_engine(corrected_db_url)
    AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
    # AsyncSessionLocal initialized

    # Initialize system monitoring
    try:
        from plugins.admin_panel.system_monitor import set_bot_start_time
        set_bot_start_time()
        # System monitoring initialized
    except Exception as e:
        logger.warning(f"Failed to initialize system monitoring: {e}")

    # Load all plugin settings from database
    # Loading plugin settings from database
    all_settings = await load_all_plugin_settings(AsyncSessionLocal)
    
    # Register plugins AFTER main handlers, passing AsyncSessionLocal
    # Registering plugins
    register_plugins(dp, bot, AsyncSessionLocal)
    
    # Global debug message handler - MUST be registered AFTER plugins to not interfere
    @dp.message()
    async def global_debug_message_handler(message: Message):
        logger.debug(f"GLOBAL_DEBUG: Unhandled message from={message.from_user.id} ct={message.content_type} text={message.text}")

    # Starting bot
    
    try:
        # Start polling - limit updates to necessary types for performance
        allowed_updates = [
            "message",
            "chat_member",
            "my_chat_member",  # Добавляем для получения обновлений о боте и инвайт-ссылках
            "callback_query",
            "poll",
            "poll_answer",
        ]
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())