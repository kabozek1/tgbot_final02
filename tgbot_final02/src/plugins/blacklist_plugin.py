from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import asyncio
import logging
from sqlalchemy.ext.asyncio import async_sessionmaker

from utils.plugin_settings import load_plugin_settings

logger = logging.getLogger(__name__)

# Глобальные переменные для хранения настроек (инициализируются из БД)
ANTIMAT_ENABLED = True
ANTIMAT_WARNINGS_ENABLED = True
blacklist_words = []
blacklist_links = []


def get_antimat_config():
    """Получить конфигурацию антимата из БД"""
    try:
        from utils.plugin_settings import load_plugin_settings
        # Используем синхронную версию для совместимости
        return {
            "enabled": ANTIMAT_ENABLED,
            "warnings_enabled": ANTIMAT_WARNINGS_ENABLED,
            "blacklist_words": blacklist_words,
            "blacklist_links": blacklist_links
        }
    except ImportError:
        # Fallback конфигурация
        return {
            "enabled": True,
            "warnings_enabled": True,
            "blacklist_words": ["дурак", "лох"],
            "blacklist_links": ["t.me/", "http://", "https://"]
        }


async def initialize_antimat_settings(async_session_local: async_sessionmaker):
    """Инициализация настроек антимата из БД"""
    global ANTIMAT_ENABLED, ANTIMAT_WARNINGS_ENABLED, blacklist_words, blacklist_links
    
    logger.info(f"🔧 ANTIMAT_INIT: Starting antimat settings initialization")
    
    try:
        settings = await load_plugin_settings("antimat", async_session_local)
        logger.info(f"🔍 ANTIMAT_INIT: Loaded settings from DB: {settings}")
        
        ANTIMAT_ENABLED = settings.get("enabled", True)
        ANTIMAT_WARNINGS_ENABLED = settings.get("warnings_enabled", True)
        blacklist_words = settings.get("blacklist_words", ["дурак", "лох"])
        blacklist_links = settings.get("blacklist_links", ["t.me/", "http://", "https://"])
        
        logger.info(f"✅ ANTIMAT_INIT: Settings initialized: enabled={ANTIMAT_ENABLED}, warnings={ANTIMAT_WARNINGS_ENABLED}")
        logger.info(f"✅ ANTIMAT_INIT: Blacklist words: {blacklist_words}")
        logger.info(f"✅ ANTIMAT_INIT: Blacklist links: {blacklist_links}")
    except Exception as e:
        logger.error(f"❌ ANTIMAT_INIT: Error initializing antimat settings: {e}")
        # Используем дефолтные значения
        ANTIMAT_ENABLED = True
        ANTIMAT_WARNINGS_ENABLED = True
        blacklist_words = ["дурак", "лох"]
        blacklist_links = ["t.me/", "http://", "https://"]
        logger.info(f"🔄 ANTIMAT_INIT: Using default values: words={blacklist_words}, links={blacklist_links}")


async def sync_antimat_settings(async_session_local: async_sessionmaker):
    """Синхронизация настроек антимата с БД"""
    global ANTIMAT_ENABLED, ANTIMAT_WARNINGS_ENABLED, blacklist_words, blacklist_links
    
    logger.info(f"🔄 ANTIMAT_SYNC: Starting antimat settings synchronization")
    
    try:
        settings = await load_plugin_settings("antimat", async_session_local)
        logger.info(f"🔍 ANTIMAT_SYNC: Loaded settings from DB: {settings}")
        
        ANTIMAT_ENABLED = settings.get("enabled", True)
        ANTIMAT_WARNINGS_ENABLED = settings.get("warnings_enabled", True)
        blacklist_words = settings.get("blacklist_words", ["дурак", "лох"])
        blacklist_links = settings.get("blacklist_links", ["t.me/", "http://", "https://"])
        
        logger.info(f"✅ ANTIMAT_SYNC: Settings synced: enabled={ANTIMAT_ENABLED}, warnings={ANTIMAT_WARNINGS_ENABLED}")
        logger.info(f"✅ ANTIMAT_SYNC: Updated blacklist_words: {blacklist_words}")
        logger.info(f"✅ ANTIMAT_SYNC: Updated blacklist_links: {blacklist_links}")
    except Exception as e:
        logger.error(f"❌ ANTIMAT_SYNC: Error syncing antimat settings: {e}")


def is_blacklisted_content(text: str) -> bool:
    """Проверяет, содержит ли текст запрещённое содержимое"""
    logger.info(f"🔍 BLACKLIST_CHECK: Checking text: '{text[:50]}...' (enabled={ANTIMAT_ENABLED})")
    logger.info(f"🔍 BLACKLIST_CHECK: Current blacklist_words: {blacklist_words}")
    logger.info(f"🔍 BLACKLIST_CHECK: Current blacklist_links: {blacklist_links}")
    
    if not text or not ANTIMAT_ENABLED:
        logger.info(f"🔍 BLACKLIST_CHECK: Skipping check - text empty or antimat disabled")
        return False
    
    # Исключаем все команды из проверки
    commands = [
        "/start", "/help", "/ping", "/set_name_topic", "/stats", "/rep", "/top",
        "/delete", "/poll", "/mute", "/unmute", "/invites", "/kick", "/ban", "/warn", "/admin"
    ]
    
    text_lower = text.lower().strip()
    for command in commands:
        if text_lower.startswith(command.lower()):
            logger.info(f"🔍 BLACKLIST_CHECK: Skipping command: {command}")
            return False
    
    text_lower = text.lower()
    
    # Проверяем запрещённые слова
    for word in blacklist_words:
        if word in text_lower:
            logger.info(f"🚫 BLACKLIST_MATCH: Found blacklisted word '{word}' in text")
            return True
    
    # Проверяем запрещённые ссылки
    for link in blacklist_links:
        if link in text_lower:
            logger.info(f"🚫 BLACKLIST_MATCH: Found blacklisted link '{link}' in text")
            return True
    
    logger.info(f"✅ BLACKLIST_CHECK: Text is clean")
    return False

async def on_message_filter(message: Message):
    """Filter messages for blacklisted content."""
    logger.info(f"🔍 MESSAGE_FILTER: Processing message from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"🔍 MESSAGE_FILTER: Message text: '{message.text[:100] if message.text else 'No text'}...'")
    
    if not is_blacklisted_content(message.text):
        logger.info(f"✅ MESSAGE_FILTER: Message passed blacklist check")
        return
    
    logger.warning(f"🚫 MESSAGE_FILTER: Message contains blacklisted content, attempting to delete")
    
    try:
        await message.delete()
        logger.info(f"✅ MESSAGE_FILTER: Successfully deleted message {message.message_id}")
        
        if ANTIMAT_WARNINGS_ENABLED:
            warning_msg = await message.answer("Сообщение удалено: запрещённое содержимое.")
            logger.info(f"📢 MESSAGE_FILTER: Sent warning message {warning_msg.message_id}")
            
            # Удаляем предупреждающее сообщение через 3 секунды
            async def delete_warning():
                await asyncio.sleep(3)
                try:
                    await warning_msg.delete()
                    logger.info(f"🗑️ MESSAGE_FILTER: Deleted warning message {warning_msg.message_id}")
                except (TelegramBadRequest, TelegramForbiddenError):
                    logger.debug(f"Could not delete warning message {warning_msg.message_id}")
                    pass  # Игнорируем ошибки удаления
            
            asyncio.create_task(delete_warning())
        
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning(f"❌ MESSAGE_FILTER: Cannot delete message {message.message_id}: {e}")
        # If can't delete, just send warning
        if ANTIMAT_WARNINGS_ENABLED:
            warning_msg = await message.answer("⚠️ Запрещённое содержимое в сообщении!")
            logger.info(f"📢 MESSAGE_FILTER: Sent warning message {warning_msg.message_id} (could not delete original)")
            
            # Удаляем предупреждающее сообщение через 3 секунды
            async def delete_warning():
                await asyncio.sleep(3)
                try:
                    await warning_msg.delete()
                    logger.info(f"🗑️ MESSAGE_FILTER: Deleted warning message {warning_msg.message_id}")
                except (TelegramBadRequest, TelegramForbiddenError):
                    logger.debug(f"Could not delete warning message {warning_msg.message_id}")
                    pass  # Игнорируем ошибки удаления
            
            asyncio.create_task(delete_warning())
        
    except Exception as e:
        logger.error(f"❌ MESSAGE_FILTER: Blacklist plugin error: {e}")


class BlacklistMiddleware:
    """Middleware для проверки сообщений на запрещённое содержимое"""
    
    def __init__(self):
        self.name = "BlacklistMiddleware"
    
    async def __call__(self, handler, event, data):
        # Проверяем только текстовые сообщения
        if hasattr(event, 'text') and event.text:
            # Исключаем команды из проверки
            commands = [
                "/start", "/help", "/ping", "/set_name_topic", "/stats", "/rep", "/top",
                "/delete", "/poll", "/mute", "/unmute", "/invites", "/kick", "/ban", "/warn", "/admin"
            ]
            
            text_lower = event.text.lower().strip()
            is_command = any(text_lower.startswith(command.lower()) for command in commands)
            
            if not is_command and is_blacklisted_content(event.text):
                logger.warning(f"🚫 BLACKLIST_MIDDLEWARE: Message contains blacklisted content, attempting to delete")
                
                try:
                    await event.delete()
                    logger.info(f"✅ BLACKLIST_MIDDLEWARE: Successfully deleted message {event.message_id}")
                    
                    if ANTIMAT_WARNINGS_ENABLED:
                        warning_msg = await event.answer("Сообщение удалено: запрещённое содержимое.")
                        logger.info(f"📢 BLACKLIST_MIDDLEWARE: Sent warning message {warning_msg.message_id}")
                        
                        # Удаляем предупреждающее сообщение через 3 секунды
                        async def delete_warning():
                            await asyncio.sleep(3)
                            try:
                                await warning_msg.delete()
                                logger.info(f"🗑️ BLACKLIST_MIDDLEWARE: Deleted warning message {warning_msg.message_id}")
                            except (TelegramBadRequest, TelegramForbiddenError):
                                logger.debug(f"Could not delete warning message {warning_msg.message_id}")
                                pass
                        
                        asyncio.create_task(delete_warning())
                    
                    # Не продолжаем обработку для удалённых сообщений
                    return
                    
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.warning(f"❌ BLACKLIST_MIDDLEWARE: Cannot delete message {event.message_id}: {e}")
                    # Если не можем удалить, просто отправляем предупреждение
                    if ANTIMAT_WARNINGS_ENABLED:
                        warning_msg = await event.answer("⚠️ Запрещённое содержимое в сообщении!")
                        logger.info(f"📢 BLACKLIST_MIDDLEWARE: Sent warning message {warning_msg.message_id} (could not delete original)")
                        
                        # Удаляем предупреждающее сообщение через 3 секунды
                        async def delete_warning():
                            await asyncio.sleep(3)
                            try:
                                await warning_msg.delete()
                                logger.info(f"🗑️ BLACKLIST_MIDDLEWARE: Deleted warning message {warning_msg.message_id}")
                            except (TelegramBadRequest, TelegramForbiddenError):
                                logger.debug(f"Could not delete warning message {warning_msg.message_id}")
                                pass
                        
                        asyncio.create_task(delete_warning())
                
                except Exception as e:
                    logger.error(f"❌ BLACKLIST_MIDDLEWARE: Blacklist middleware error: {e}")
        
        # Продолжаем обработку другими обработчиками
        return await handler(event, data)


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register blacklist plugin middleware."""
    logger.info(f"🔧 BLACKLIST_REGISTER: Starting blacklist plugin registration")
    
    # Инициализируем настройки при регистрации
    import asyncio
    asyncio.create_task(initialize_antimat_settings(async_session_local))
    
    # Регистрируем middleware вместо обработчика
    dp.message.middleware(BlacklistMiddleware())
    
    logger.info(f"✅ BLACKLIST_REGISTER: Blacklist middleware registered successfully")
