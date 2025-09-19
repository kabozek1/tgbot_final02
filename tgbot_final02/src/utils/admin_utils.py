"""Утилиты для проверки прав администратора"""

import logging
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from config import get_settings
from models.base import Admin

logger = logging.getLogger(__name__)


async def is_user_admin(message: Message, user_id: int, async_session_local: async_sessionmaker = None) -> bool:
    """
    Универсальная проверка прав администратора.
    Проверяет:
    1. Администраторов из конфига (ADMINS)
    2. Администраторов из базы данных
    3. Администраторов Telegram-чата
    
    Args:
        message: Сообщение для получения контекста чата
        user_id: ID пользователя для проверки
        async_session_local: Сессия базы данных (опционально)
        
    Returns:
        bool: True если пользователь администратор, False иначе
    """
    try:
        settings = get_settings()
        
        # 1. Проверяем администраторов из конфига
        if user_id in settings.ADMINS:
            print(f"DEBUG ADMIN_UTILS: User {user_id} is config admin")
            return True
        
        # 2. Проверяем администраторов из базы данных (если передана сессия)
        if async_session_local:
            try:
                async with async_session_local() as session:
                    result = await session.execute(
                        select(Admin).filter_by(telegram_id=user_id)
                    )
                    db_admin = result.scalar_one_or_none()
                    if db_admin:
                        print(f"DEBUG ADMIN_UTILS: User {user_id} is DB admin with role {db_admin.role}")
                        return True
            except Exception as e:
                print(f"DEBUG ADMIN_UTILS: Error checking DB admin for user {user_id}: {e}")
        
        # 3. Проверяем администраторов Telegram-чата
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=user_id
        )
        
        # Отладочная информация
        print(f"DEBUG ADMIN_UTILS: User {user_id} chat status: {chat_member.status}")
        
        # Проверяем статус: creator (создатель) или administrator (администратор)
        is_chat_admin = chat_member.status in ['creator', 'administrator']
        print(f"DEBUG ADMIN_UTILS: User {user_id} is_chat_admin: {is_chat_admin}")
        
        return is_chat_admin
        
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        print(f"DEBUG ADMIN_UTILS: Telegram error checking admin status for user {user_id}: {e}")
        return False
    except Exception as e:
        print(f"DEBUG ADMIN_UTILS: Unexpected error checking admin status for user {user_id}: {e}")
        return False


class IsAdmin(BaseFilter):
    """Фильтр для проверки прав администратора"""
    
    def __init__(self, async_session_local: async_sessionmaker = None):
        self.async_session_local = async_session_local
    
    async def __call__(self, message: Message) -> bool:
        """Проверяет, является ли отправитель сообщения администратором"""
        if not message.from_user:
            return False
        
        return await is_user_admin(message, message.from_user.id, self.async_session_local)