import asyncio
import re
import logging
import sys
from datetime import datetime, timedelta
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker
from config import get_settings
from utils.admin_utils import is_user_admin

# Force logging configuration for this module
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info("🔧 MUTE_PLUGIN: Логирование инициализировано")


async def delete_command_message(message: Message):
    """Удаляет команду после обработки"""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления


async def send_and_auto_delete(message: Message, text: str, delay: int = 3):
    """Отправляет сообщение и удаляет его через указанное время"""
    try:
        sent_message = await message.answer(text)
        await asyncio.sleep(delay)
        await sent_message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления


async def delete_system_message_after_delay(sent_message: Message, delay: int):
    """Удаляет системное сообщение через указанное время."""
    await asyncio.sleep(delay)
    try:
        await sent_message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления


async def save_user_to_db(user_id, username, first_name, async_session_local, search_username):
    """Сохраняет пользователя в базу данных"""
    if async_session_local:
        try:
            from models.base import User
            from sqlalchemy.future import select
            async with async_session_local() as session:
                # Проверяем, есть ли уже такой пользователь
                result = await session.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                existing_user = result.scalar_one_or_none()
                
                if not existing_user:
                    # Создаем нового пользователя
                    new_user = User(
                        telegram_id=user_id,
                        username=username,
                        first_name=first_name
                    )
                    session.add(new_user)
                    await session.commit()
                    logger.info(f"💾 Пользователь @{search_username} сохранен в БД")
                else:
                    # Обновляем данные существующего пользователя
                    existing_user.username = username
                    existing_user.first_name = first_name
                    await session.commit()
                    logger.info(f"🔄 Данные пользователя @{search_username} обновлены в БД")
        except Exception as db_e:
            logger.warning(f"⚠️ Ошибка при сохранении в БД: {db_e}")


async def extract_user_info(message: Message, bot=None, async_session_local=None):
    """
    Извлекает информацию о пользователе из сообщения.
    Поддерживает два способа:
    1. @username упоминание в тексте команды (приоритетный способ)
    2. Reply на сообщение пользователя
    
    Возвращает: (user_id, username) или (None, None) если не удалось извлечь
    """
    
    logger.info(f"🔍 extract_user_info вызвана для сообщения от {message.from_user.username or message.from_user.first_name}")
    logger.info(f"📝 Текст сообщения: {message.text}")
    
    # Способ 1: @username в тексте команды (приоритетный способ)
    if message.text:
        # Ищем @username в тексте команды
        username_match = re.search(r'@(\w+)', message.text)
        if username_match:
            username = username_match.group(1)
            logger.info(f"🎯 Найден username в тексте: @{username}")
            
            # Ищем пользователя в базе данных по username
            if async_session_local:
                try:
                    from sqlalchemy.future import select
                    from models.base import User
                    
                    logger.info(f"🔍 Ищем пользователя {username} в базе данных...")
                    async with async_session_local() as session:
                        result = await session.execute(
                            select(User).where(User.username == username)
                        )
                        user = result.scalar_one_or_none()
                        if user:
                            logger.info(f"✅ Пользователь найден в БД: {user.username} (telegram_id: {user.telegram_id})")
                            return user.telegram_id, user.username or user.first_name or "Пользователь"
                        else:
                            logger.warning(f"❌ Пользователь {username} не найден в БД")
                except Exception as e:
                    logger.error(f"❌ Ошибка при поиске в БД: {e}")
            else:
                logger.warning("❌ async_session_local не передан")
            
            # Если не найден в БД, пробуем найти через список участников чата
            if bot:
                try:
                    logger.info(f"🔍 Ищем пользователя @{username} среди участников чата...")
                    
                    # Пробуем среди администраторов
                    chat_admins = await bot.get_chat_administrators(message.chat.id)
                    for admin in chat_admins:
                        if admin.user.username and admin.user.username.lower() == username.lower():
                            user_id = admin.user.id
                            user_name = admin.user.username or admin.user.first_name
                            logger.info(f"✅ Пользователь найден среди администраторов: @{username} (ID: {user_id})")
                            
                            # Сохраняем пользователя в БД для будущих операций
                            await save_user_to_db(user_id, admin.user.username, admin.user.first_name, async_session_local, username)
                            return user_id, user_name
                    
                    logger.info(f"🔍 Пользователь @{username} не найден среди администраторов")
                    
                except Exception as e:
                    logger.warning(f"❌ Ошибка при поиске среди участников: {e}")
            
            # Если не удалось найти ни в БД, ни через API
            logger.info(f"⚠️ Пользователь @{username} не найден")
            return None, username
    
    # Способ 2: Reply на сообщение (если @username не найден)
    logger.info(f"🔍 Проверяем reply_to_message: {message.reply_to_message is not None}")
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        logger.info(f"✅ Найден пользователь через reply: {target_user.username or target_user.first_name} (ID: {target_user.id})")
        
        # Сохраняем пользователя в БД
        if target_user.username:
            await save_user_to_db(target_user.id, target_user.username, target_user.first_name, async_session_local, target_user.username)
        
        return target_user.id, target_user.username or target_user.first_name or "Пользователь"
    
    # Если ничего не найдено
    if not message.text:
        logger.info("❌ Текст сообщения отсутствует")
    else:
        logger.info("❌ Username не найден в тексте сообщения")
    
    logger.info("❌ Не удалось извлечь информацию о пользователе")
    return None, None


# Функция is_user_admin теперь импортируется из utils.admin_utils


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register mute plugin handlers."""
    
    async def mute_command(message: Message):
        """Mute user by replying to their message or using @username."""
        
        logger.info(f"🎯 Команда mute вызвана пользователем {message.from_user.username or message.from_user.first_name} (ID: {message.from_user.id})")
        logger.info(f"📝 Текст команды: {message.text}")
        
        # Удаляем команду сразу после обработки
        await delete_command_message(message)
        
        # Get settings for message delete delay
        settings = get_settings()
        
        # Проверяем права администратора для исполнителя команды
        if not await is_user_admin(message, message.from_user.id, async_session_local):
            logger.warning(f"❌ Пользователь {message.from_user.username} не является администратором")
            await send_and_auto_delete(message, "❌ У вас нет прав для выполнения этой команды.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        logger.info("✅ Пользователь является администратором")
        
        # Извлекаем информацию о целевом пользователе
        logger.info("🔍 Извлекаем информацию о целевом пользователе...")
        user_id, username = await extract_user_info(message, bot, async_session_local)
        
        logger.info(f"📊 Результат extract_user_info: user_id={user_id}, username={username}")
        
        if not user_id:
            logger.warning("❌ user_id не найден")
            if username:
                await send_and_auto_delete(message, f"❌ Пользователь @{username} не найден в этом чате.", settings.MUTE_MESSAGE_DELETE_DELAY)
            else:
                await send_and_auto_delete(message, "❌ Укажите пользователя: ответьте на его сообщение или используйте @username.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        # Check if user is admin (can't mute admins)
        if await is_user_admin(message, user_id, async_session_local):
            await send_and_auto_delete(message, "❌ Нельзя замьютить администратора.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        # Parse mute duration
        command_args = message.text.split()
        mute_minutes = 10  # Default 10 minutes
        
        # Ищем время мута в аргументах команды
        for arg in command_args[1:]:  # Пропускаем саму команду
            if not arg.startswith('@'):  # Пропускаем @username
                try:
                    mute_minutes = int(arg)
                    if mute_minutes <= 0:
                        await send_and_auto_delete(message, "❌ Время мута должно быть больше 0 минут.", settings.MUTE_MESSAGE_DELETE_DELAY)
                        return
                    break
                except ValueError:
                    continue  # Пропускаем нечисловые аргументы
        
        # Create restricted permissions (no sending messages)
        restricted_permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        try:
            # Apply mute
            await message.bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=restricted_permissions,
                until_date=None  # Permanent mute
            )
            
            await send_and_auto_delete(message, f"🔇 Пользователь @{username} замьючен на {mute_minutes} минут.", settings.MUTE_MESSAGE_DELETE_DELAY)
            
            # Schedule unmute after specified time
            if mute_minutes > 0:
                # Restore normal permissions after mute time
                normal_permissions = ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False
                )
                
                # Wait for mute duration
                await asyncio.sleep(mute_minutes * 60)
                
                # Unmute user
                try:
                    await message.bot.restrict_chat_member(
                        chat_id=message.chat.id,
                        user_id=user_id,
                        permissions=normal_permissions,
                        until_date=None
                    )
                    await send_and_auto_delete(message, f"🔊 Пользователь @{username} размьючен.", settings.MUTE_MESSAGE_DELETE_DELAY)
                except Exception:
                    pass  # Ignore errors when unmuting
                    
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            await send_and_auto_delete(message, f"❌ Не удалось замьютить пользователя: {e}", settings.MUTE_MESSAGE_DELETE_DELAY)
        except Exception as e:
            await send_and_auto_delete(message, f"❌ Ошибка при муте: {e}", settings.MUTE_MESSAGE_DELETE_DELAY)
    
    async def unmute_command(message: Message):
        """Unmute user by replying to their message or using @username."""
        # Удаляем команду сразу после обработки
        await delete_command_message(message)
        
        # Get settings for message delete delay
        settings = get_settings()
        
        # Проверяем права администратора для исполнителя команды
        if not await is_user_admin(message, message.from_user.id, async_session_local):
            await send_and_auto_delete(message, "❌ У вас нет прав для выполнения этой команды.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        # Извлекаем информацию о целевом пользователе
        user_id, username = await extract_user_info(message, bot, async_session_local)
        
        if not user_id:
            if username:
                await send_and_auto_delete(message, f"❌ Пользователь @{username} не найден в этом чате.", settings.MUTE_MESSAGE_DELETE_DELAY)
            else:
                await send_and_auto_delete(message, "❌ Укажите пользователя: ответьте на его сообщение или используйте @username.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        # Check if user is admin (can't unmute admins)
        if await is_user_admin(message, user_id, async_session_local):
            await send_and_auto_delete(message, "❌ Нельзя размьютить администратора.", settings.MUTE_MESSAGE_DELETE_DELAY)
            return
        
        # Create normal permissions (restore all messaging rights)
        normal_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        try:
            # Apply unmute
            await message.bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=normal_permissions,
                until_date=None
            )
            
            await send_and_auto_delete(message, f"🔊 Пользователь @{username} размьючен.", settings.MUTE_MESSAGE_DELETE_DELAY)
                    
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            await send_and_auto_delete(message, f"❌ Не удалось размьютить пользователя: {e}", settings.MUTE_MESSAGE_DELETE_DELAY)
        except Exception as e:
            await send_and_auto_delete(message, f"❌ Ошибка при размуте: {e}", settings.MUTE_MESSAGE_DELETE_DELAY)
    
    # Регистрируем обработчики команд
    dp.message.register(mute_command, Command("mute"))
    dp.message.register(unmute_command, Command("unmute"))