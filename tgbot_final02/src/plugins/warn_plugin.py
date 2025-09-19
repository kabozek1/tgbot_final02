import asyncio
import re
from aiogram import Dispatcher, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from models.base import User, Warning
from datetime import datetime
from utils.admin_utils import is_user_admin
import logging
from config import get_settings

# In-memory storage for warnings (TODO: replace with database)
warns = {}  # {user_id: count}


async def delete_command_message(message: Message):
    """Удаляет команду после обработки"""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления


async def send_and_auto_delete(message: Message, text: str, delay: int = 3):
    """Отправляет сообщение и автоматически удаляет его через указанное время"""
    try:
        sent_message = await message.answer(text)
        # Запускаем удаление в фоне
        asyncio.create_task(delete_system_message_after_delay(sent_message, delay))
        return sent_message
    except Exception:
        return None


async def delete_system_message_after_delay(sent_message: Message, delay: int):
    """Удаляет системное сообщение через указанное время"""
    try:
        await asyncio.sleep(delay)
        await sent_message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления


async def extract_user_info(message: Message, bot=None, async_session_local=None):
    """
    Извлекает информацию о пользователе из сообщения.
    Поддерживает два способа:
    1. @username упоминание в тексте команды (приоритетный способ)
    2. Reply на сообщение пользователя
    
    Возвращает: (user_id, username) или (None, None) если не удалось извлечь
    """
    # Способ 1: @username в тексте команды (приоритетный способ)
    if message.text:
        # Ищем @username в тексте команды
        username_match = re.search(r'@(\w+)', message.text)
        if username_match:
            username = username_match.group(1)
            
            # Убираем проверку на отправителя - команда должна работать с любым пользователем
            
            # Ищем пользователя в базе данных по username
            if async_session_local:
                try:
                    from sqlalchemy.future import select
                    from models.base import User
                    
                    async with async_session_local() as session:
                        result = await session.execute(
                            select(User).where(User.username == username)
                        )
                        user = result.scalar_one_or_none()
                        if user:
                            return user.telegram_id, user.username or user.first_name or "Пользователь"
                except Exception as e:
                    pass
            
            # Если не удалось найти в БД, возвращаем только username
            return None, username
    
    # Способ 2: Reply на сообщение (если @username не найден)
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        return target_user.id, target_user.username or target_user.first_name or "Пользователь"
    
    return None, None


# Функция is_user_admin теперь импортируется из utils.admin_utils


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register warn plugin handlers."""
    
    async def warn_command(message: Message):
        """Warn user by replying to their message or using @username."""
        settings = get_settings()
        
        # Удаляем команду сразу после обработки
        await delete_command_message(message)
        
        # Проверяем права администратора для исполнителя команды
        if not await is_user_admin(message, message.from_user.id, async_session_local):
            await send_and_auto_delete(message, "❌ У вас нет прав для выполнения этой команды.", settings.WARN_MESSAGE_DELETE_DELAY)
            return
        
        # Извлекаем информацию о целевом пользователе
        user_id, username = await extract_user_info(message, bot, async_session_local)
        
        if not user_id:
            if username:
                await send_and_auto_delete(message, f"❌ Пользователь @{username} не найден в этом чате.", settings.WARN_MESSAGE_DELETE_DELAY)
            else:
                await send_and_auto_delete(message, "❌ Укажите пользователя: ответьте на его сообщение или используйте @username.", settings.WARN_MESSAGE_DELETE_DELAY)
            return
        
        # Check if user is admin (can't warn admins)
        if await is_user_admin(message, user_id, async_session_local):
            await send_and_auto_delete(message, "❌ Нельзя выдать предупреждение администратору.", settings.WARN_MESSAGE_DELETE_DELAY)
            return
        
        # Increase warning count
        warns[user_id] = warns.get(user_id, 0) + 1
        count = warns[user_id]
        
        try:
            if count == 1:
                await send_and_auto_delete(message, f"⚠️ Первое предупреждение для @{username}", settings.WARN_MESSAGE_DELETE_DELAY)
                
            elif count == 2:
                await send_and_auto_delete(message, f"⚠️ Второе предупреждение для @{username}", settings.WARN_MESSAGE_DELETE_DELAY)
                
            elif count >= 3:
                # Ban user (kick from chat)
                try:
                    await message.bot.ban_chat_member(
                        chat_id=message.chat.id,
                        user_id=user_id
                    )
                    await send_and_auto_delete(message, f"🔨 Пользователь @{username} заблокирован за 3 предупреждения.", settings.WARN_MESSAGE_DELETE_DELAY)
                    
                    # Reset warnings for banned user
                    if user_id in warns:
                        del warns[user_id]
                        
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    await send_and_auto_delete(message, f"❌ Не удалось заблокировать пользователя: {e}", settings.WARN_MESSAGE_DELETE_DELAY)
                    # Reset warnings anyway
                    if user_id in warns:
                        del warns[user_id]
                        
        except Exception as e:
            await send_and_auto_delete(message, f"❌ Ошибка при выдаче предупреждения: {e}", settings.WARN_MESSAGE_DELETE_DELAY)
    
    # Регистрируем обработчик команды
    dp.message.register(warn_command, Command("warn"))