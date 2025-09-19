
import asyncio
import re
from datetime import datetime, timedelta
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import time
from sqlalchemy.ext.asyncio import async_sessionmaker # Added import
from config import get_settings

# Хранилище репутации пользователей
# TODO: Replace with Redis/DB in production
reputation = {}  # {user_id: score}

# Rate limiting: allow 1 rep action per actor per 30s
last_rep_action = {}  # {(actor_id, target_id): timestamp}


async def delete_command_message(message: Message):
    """Удаляет команду после обработки"""
    try:
        print(f"[DEBUG] Attempting to delete message {message.message_id} from user {message.from_user.id}")
        await message.delete()
        print(f"[DEBUG] Successfully deleted message {message.message_id}")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        print(f"[DEBUG] Failed to delete message {message.message_id}: {e}")
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
    print(f"[DEBUG] extract_user_info called by user {message.from_user.id} (@{message.from_user.username})")
    print(f"[DEBUG] Message text: {message.text}")
    
    # Способ 1: @username в тексте команды (приоритетный способ)
    if message.text:
        # Ищем @username в тексте команды
        username_match = re.search(r'@(\w+)', message.text)
        if username_match:
            username = username_match.group(1)
            print(f"[DEBUG] Found username mention: @{username}")
            
            # Проверяем, не является ли это самим отправителем команды
            if username.lower() == (message.from_user.username or "").lower():
                print(f"[DEBUG] User mentioned themselves, returning their own info")
                return message.from_user.id, message.from_user.username or message.from_user.first_name or "Пользователь"
            
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
                            print(f"[DEBUG] Found user in DB: {user.telegram_id} (@{user.username})")
                            return user.telegram_id, user.username or user.first_name or "Пользователь"
                except Exception as e:
                    print(f"[DEBUG] Failed to get user from DB: {e}")
            
            # Если не удалось найти в БД, возвращаем только username
            print(f"[DEBUG] Cannot resolve username @{username} to user_id, returning username only")
            return None, username
    
    # Способ 2: Reply на сообщение пользователя
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        print(f"[DEBUG] Found reply target: {target_user.id} (@{target_user.username})")
        return target_user.id, target_user.username or target_user.first_name or "Пользователь"
    
    print(f"[DEBUG] No user info found")
    return None, None


async def on_rep_mark(message: Message):
    """Handle reputation changes from replies."""
    try:
        # Get user info
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        actor_id = message.from_user.id
        
        # Prevent users from changing their own reputation
        if actor_id == target_user_id:
            await message.answer("❌ Нельзя менять репутацию самому себе!")
            return
        
        # Prevent changing bot's reputation
        if target_user.is_bot:
            await message.answer("❌ Нельзя менять репутацию боту!")
            return
        
        # Rate limiting: check if actor already acted on this target recently
        rate_key = (actor_id, target_user_id)
        current_time = time.time()
        if rate_key in last_rep_action and current_time - last_rep_action[rate_key] < 30:
            await message.answer("❌ Слишком часто! Подождите 30 секунд.")
            return
        
        # Initialize reputation if user doesn't exist
        if target_user_id not in reputation:
            reputation[target_user_id] = 0
        
        # Change reputation based on trigger
        trigger = message.text.strip()
        if trigger in ("+", "👍"):
            reputation[target_user_id] += 1
        elif trigger in ("-", "👎"):
            reputation[target_user_id] -= 1
        
        # Update rate limiting timestamp
        last_rep_action[rate_key] = current_time
        
        # Send confirmation
        username = target_user.username or target_user.first_name or f"ID {target_user_id}"
        await message.answer(f"Репутация @{username}: {reputation[target_user_id]}")
        
        # Delete the trigger message (+, -, 👍, 👎)
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass # Ignore if can't delete
            
    except Exception as e:
        await message.answer("❌ Ошибка при изменении репутации")
        print(f"Reputation change error: {e}")


async def handle_rep_cmd(message: Message, bot):
    """Show user's reputation by replying to their message or using @username."""
    settings = get_settings()
    
    # Удаляем команду сразу после обработки
    await delete_command_message(message)
    
    try:
        # Извлекаем информацию о целевом пользователе
        target_user_id, username = await extract_user_info(message, bot, async_session_local)
        
        if not target_user_id and not username:
            await send_and_auto_delete(message, "❌ Укажите пользователя: ответьте на его сообщение или используйте @username.", settings.REP_MESSAGE_DELETE_DELAY)
            return
        
        if target_user_id:
            # Get reputation (default to 0)
            user_reputation = reputation.get(target_user_id, 0)
            # Send reputation info
            await send_and_auto_delete(message, f"📊 Репутация пользователя @{username}: {user_reputation}", settings.REP_MESSAGE_DELETE_DELAY)
        else:
            # Если user_id неизвестен, показываем что пользователь не найден в чате, но репутация 0
            await send_and_auto_delete(message, f"📊 Репутация пользователя @{username}: 0 (пользователь не найден в чате)", settings.REP_MESSAGE_DELETE_DELAY)
        
    except Exception as e:
        await send_and_auto_delete(message, "❌ Ошибка при получении репутации", settings.REP_MESSAGE_DELETE_DELAY)
        print(f"Reputation command error: {e}")


async def handle_top_cmd(message: Message):
    """Show top 5 users by reputation."""
    try:
        print(f"[DEBUG] handle_top_cmd called for user {message.from_user.id}")
        if not reputation:
            await message.answer("Рейтинг пуст")
            # Удаляем команду даже если рейтинг пуст
            await delete_command_message(message)
            return
        
        # Sort users by reputation descending
        sorted_users = sorted(reputation.items(), key=lambda x: x[1], reverse=True)
        
        # Get top 5
        top_users = sorted_users[:5]
        
        # Format the rating text
        result_text = "Топ пользователей по репутации:\n"
        
        for i, (user_id, score) in enumerate(top_users, 1):
            # TODO: Fetch username for better display instead of just ID
            result_text += f"{i}) ID {user_id} — {score}\n"
        
        await message.answer(result_text)
        
        # Удаляем команду после обработки
        await delete_command_message(message)
        
    except Exception as e:
        await message.answer("❌ Ошибка при получении топа")
        print(f"Top command error: {e}")
        # Удаляем команду даже при ошибке
        await delete_command_message(message)


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register reputation plugin handlers."""
    
    # Создаем обертки для команд
    async def rep_command_wrapper(message: Message):
        return await handle_rep_cmd(message, bot)
    
    async def top_command_wrapper(message: Message):
        return await handle_top_cmd(message)
    
    # Register handler for text replies (+, -, 👍, 👎)
    dp.message.register(on_rep_mark, lambda m: m.text and m.text.strip() in ("+", "-", "👍", "👎") and m.reply_to_message is not None)
    
    # Register command handlers
    dp.message.register(rep_command_wrapper, Command(commands=["rep"]))
    dp.message.register(top_command_wrapper, Command(commands=["top"]))
