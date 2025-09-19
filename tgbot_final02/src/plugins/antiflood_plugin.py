from aiogram import Dispatcher, F
from aiogram.types import Message, TelegramObject
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram import BaseMiddleware
from collections import deque
import time
import asyncio
import logging
from typing import Callable, Dict, Any, Awaitable
from sqlalchemy.ext.asyncio import async_sessionmaker

from utils.plugin_settings import load_plugin_settings

logger = logging.getLogger(__name__)

# In-memory storage for flood control
flood_control = {}

# Глобальные переменные для хранения настроек (инициализируются из БД)
ANTISPAM_ENABLED = True
ANTISPAM_MAX_MESSAGES = 5
ANTISPAM_WINDOW_SECONDS = 10


async def initialize_antispam_settings(async_session_local: async_sessionmaker):
    """Инициализация настроек антиспама из БД"""
    global ANTISPAM_ENABLED, ANTISPAM_MAX_MESSAGES, ANTISPAM_WINDOW_SECONDS
    
    logger.info(f"🔍 DEBUG: initialize_antispam_settings called with async_session_local type={type(async_session_local)}")
    
    try:
        settings = await load_plugin_settings("antispam", async_session_local)
        ANTISPAM_ENABLED = settings.get("enabled", True)
        ANTISPAM_MAX_MESSAGES = settings.get("max_messages", 5)
        ANTISPAM_WINDOW_SECONDS = settings.get("window_seconds", 10)
        
        logger.info(f"✅ Antispam settings initialized: enabled={ANTISPAM_ENABLED}, max_messages={ANTISPAM_MAX_MESSAGES}, window_seconds={ANTISPAM_WINDOW_SECONDS}")
    except Exception as e:
        logger.error(f"❌ Error initializing antispam settings: {e}")
        # Используем дефолтные значения
        ANTISPAM_ENABLED = True
        ANTISPAM_MAX_MESSAGES = 5
        ANTISPAM_WINDOW_SECONDS = 10


def get_antispam_config():
    """Получить конфигурацию антиспама"""
    return {
        "enabled": ANTISPAM_ENABLED,
        "max_messages": ANTISPAM_MAX_MESSAGES,
        "window_seconds": ANTISPAM_WINDOW_SECONDS
    }


async def sync_antispam_settings(async_session_local: async_sessionmaker):
    """Синхронизация настроек антиспама с БД"""
    global ANTISPAM_ENABLED, ANTISPAM_MAX_MESSAGES, ANTISPAM_WINDOW_SECONDS
    
    logger.info(f"🔍 DEBUG: sync_antispam_settings called with async_session_local type={type(async_session_local)}")
    
    try:
        settings = await load_plugin_settings("antispam", async_session_local)
        ANTISPAM_ENABLED = settings.get("enabled", True)
        ANTISPAM_MAX_MESSAGES = settings.get("max_messages", 5)
        ANTISPAM_WINDOW_SECONDS = settings.get("window_seconds", 10)
        
        logger.info(f"✅ Antispam settings synced: enabled={ANTISPAM_ENABLED}, max_messages={ANTISPAM_MAX_MESSAGES}, window_seconds={ANTISPAM_WINDOW_SECONDS}")
    except Exception as e:
        logger.error(f"❌ Error syncing antispam settings: {e}")

def is_flooding(message: Message) -> bool:
    """Checks if a user is flooding. Has side effects on flood_control dict."""
    # Получаем актуальную конфигурацию
    config = get_antispam_config()
    
    logger.info(f"🔍 ANTIFLOOD_CHECK: Checking message from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"🔍 ANTIFLOOD_CONFIG: enabled={config['enabled']}, max_messages={config['max_messages']}, window_seconds={config['window_seconds']}")
    
    # Если антиспам выключен, не блокируем
    if not config["enabled"]:
        logger.info(f"🔍 ANTIFLOOD_DISABLED: Antispam is disabled, allowing message")
        return False
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    current_time = time.time()
    
    key = (chat_id, user_id)
    
    if key not in flood_control:
        flood_control[key] = deque()
    
    flood_control[key].append(current_time)
    
    # Remove timestamps older than window_seconds
    window_seconds = config["window_seconds"]
    while flood_control[key] and current_time - flood_control[key][0] > window_seconds:
        flood_control[key].popleft()
    
    # Return True if user exceeded message limit
    max_messages = config["max_messages"]
    message_count = len(flood_control[key])
    is_flood = message_count > max_messages
    
    logger.info(f"🔍 ANTIFLOOD_RESULT: User {user_id} has {message_count} messages in {window_seconds}s window (max: {max_messages}), flooding: {is_flood}")
    
    return is_flood

class AntifloodMiddleware(BaseMiddleware):
    """Middleware для проверки антиспама."""
    
    def __init__(self):
        super().__init__()
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события через middleware."""
        
        # Проверяем только сообщения
        if not isinstance(event, Message):
            return await handler(event, data)
            
        message = event
        
        # Проверяем только текстовые сообщения
        if not message.text:
            return await handler(event, data)
            
        logger.info(f"🔍 ANTIFLOOD_MIDDLEWARE: Checking message {message.message_id} from user {message.from_user.id}")
        
        # Проверяем на флуд
        if is_flooding(message):
            logger.info(f"🚫 ANTIFLOOD_MIDDLEWARE: Flood detected for user {message.from_user.id}")
            await self.handle_flood_message(message)
            return  # Прерываем обработку
            
        logger.info(f"✅ ANTIFLOOD_MIDDLEWARE: Message {message.message_id} passed flood check")
        return await handler(event, data)
        
    async def handle_flood_message(self, message: Message):
        """Handle flood message."""
        try:
            user_id = message.from_user.id
            chat_id = message.chat.id
            
            # Удаляем сообщение
            try:
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError):
                pass  # Игнорируем ошибки удаления
            
            # Отправляем предупреждение
            warning_msg = await message.answer(
                f"⚠️ {message.from_user.first_name}, вы отправляете сообщения слишком быстро! Пожалуйста, подождите."
            )
            
            # Удаляем предупреждение через 5 секунд
            async def delete_warning():
                await asyncio.sleep(5)
                try:
                    await warning_msg.delete()
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass  # Игнорируем ошибки удаления
            
            asyncio.create_task(delete_warning())
            
        except Exception as e:
            logger.error(f"Unexpected antiflood error: {e}")

def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register antiflood plugin middleware."""
    logger.info(f"🔍 DEBUG: antiflood_plugin.register called with async_session_local type={type(async_session_local)}")
    logger.info(f"🔍 DEBUG: bot type={type(bot)}")
    
    # Инициализируем настройки при регистрации
    asyncio.create_task(initialize_antispam_settings(async_session_local))
    
    # Регистрируем middleware для антифлуда
    dp.message.middleware(AntifloodMiddleware())
    logger.info("✅ Antiflood middleware registered")
