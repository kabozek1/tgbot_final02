import asyncio
import logging
import uuid
from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.filters import ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker # Added import
from models.base import InviteLink, InviteClick
from sqlalchemy import select

# Хранилище ожидающих подтверждения пользователей
# TODO: Replace with Redis/DB in production
pending_users = {}  # {user_id: {'chat_id': chat_id, 'message_id': message_id, 'task': task, 'join_info': join_info}}

# Timeout for captcha (2 minutes)
CAPTCHA_TIMEOUT = 120

logger = logging.getLogger(__name__)

async def delete_welcome_message_after_delay(message: Message, delay: int):
    """Удаляет приветственное сообщение через указанное время"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления

def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    logger.debug("Attempting to register captcha plugin handlers.")
    """Register captcha plugin handlers."""
    
    @dp.message(lambda m: m.new_chat_members and m.chat.type in ("group", "supergroup"))
    async def on_new_members(message: Message):
        """Handle new members joining the chat."""
        for user in message.new_chat_members:
            # Skip bots
            if user.is_bot:
                continue
                
            chat = message.chat
            
            # Логируем событие
            logger.info(f"👤 New member joined: {user.first_name} ({user.id}) in chat {chat.id}")
            logger.info(f"📝 User details: @{user.username or 'no_username'}, full_name: {user.full_name}")
            logger.info(f"💬 Chat type: {chat.type}, chat title: {chat.title or 'no_title'}")
            
            # Сохраняем информацию о присоединении для последующего использования
            # Пытаемся извлечь информацию о ссылке из различных источников
            invite_link_info = None
            invite_hash = None
            
            # Проверяем, есть ли информация о ссылке в сообщении
            if hasattr(message, 'from_user') and message.from_user:
                logger.debug(f"Message from_user: {message.from_user.id}")
            
            # Попытка извлечь хеш из контекста (если доступен)
            # В некоторых случаях хеш может быть доступен через другие механизмы
            if hasattr(message, 'reply_to_message') and message.reply_to_message:
                logger.debug(f"Reply to message present: {message.reply_to_message.message_id}")
            
            join_info = {
                'user_id': user.id,
                'chat_id': chat.id,
                'join_date': message.date,
                'via_link': getattr(message, 'via_bot', None) is not None,
                'message_id': message.message_id,
                'invite_hash': invite_hash,
                'invite_link_info': invite_link_info
            }

            # Временно убираем пропуск капчи для инвайт-ссылок для отладки
            # if invite_link_info:
            #     logger.info(f"User {user.id} joined via invite link. Skipping captcha restriction.")
            #     continue
            
            # Ограничиваем права пользователя (запрещаем писать сообщения)
            try:
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
                await message.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user.id,
                    permissions=restricted_permissions
                )
                logger.info(f"Restricted permissions for user {user.first_name} ({user.id})")
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logger.error(f"Failed to restrict user {user.first_name}: {e}")
                continue
            
            # Generate unique token for this captcha
            token = str(uuid.uuid4())[:8]
            
            # Создаем кнопку подтверждения
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я человек", callback_data=f"captcha:{chat.id}:{user.id}:{token}")]
            ])
            
            try:
                # Отправляем сообщение с кнопкой
                captcha_message = await message.bot.send_message(
                    chat_id=chat.id,
                    text=f"👋 Добро пожаловать, {user.first_name}!\n\n"
                         f"Подтвердите, что вы человек, нажав кнопку ниже.\n"
                         f"⏰ У вас есть {CAPTCHA_TIMEOUT} секунд.",
                    reply_markup=keyboard
                )
                
                # Сохраняем информацию о пользователе
                pending_users[user.id] = {
                    'chat_id': chat.id,
                    'message_id': captcha_message.message_id,
                    'task': None,
                    'token': token,
                    'join_info': join_info
                }
                
                # Создаем задачу для автоматического кика через CAPTCHA_TIMEOUT секунд
                async def kick_user():
                    await asyncio.sleep(CAPTCHA_TIMEOUT)
                    if user.id in pending_users:
                        try:
                            await message.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
                            await message.bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
                            await message.bot.send_message(
                                chat_id=chat.id,
                                text=f"❌ {user.first_name} был удален за неактивность."
                            )
                        except (TelegramBadRequest, TelegramForbiddenError):
                            pass
                        finally:
                            # Удаляем из ожидающих
                            if user.id in pending_users:
                                del pending_users[user.id]
                
                # Запускаем задачу
                task = asyncio.create_task(kick_user())
                pending_users[user.id]['task'] = task
                
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logger.error(f"Failed to send captcha for user {user.first_name}: {e}")
                continue
    
    @dp.callback_query(lambda c: c.data and c.data.startswith("captcha:"))
    async def on_captcha_callback(callback: CallbackQuery):
        """Handle captcha confirmation button press."""
        try:
            logger.info(f"Captcha callback received: {callback.data} from user {callback.from_user.id}")
            
            # Parse callback data: captcha:{chat_id}:{user_id}:{token}
            parts = callback.data.split(':')
            if len(parts) != 4:
                await callback.answer("❌ Неверные данные капчи", show_alert=True)
                return
                
            chat_id = int(parts[1])
            user_id = int(parts[2])
            token = parts[3]
            
            # Проверяем, что это правильный пользователь
            if callback.from_user.id != user_id:
                await callback.answer("Эту кнопку должен нажать только подтверждаемый пользователь", show_alert=True)
                return
            
            # Проверяем, что пользователь в списке ожидающих
            if user_id not in pending_users:
                await callback.answer("❌ Время истекло!", show_alert=True)
                return
            
            # Проверяем токен
            if pending_users[user_id].get('token') != token:
                await callback.answer("❌ Неверный токен!", show_alert=True)
                return
            
            # Отменяем задачу автоматического кика
            if pending_users[user_id]['task']:
                pending_users[user_id]['task'].cancel()
            
            # Восстанавливаем права пользователя
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
            await callback.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=normal_permissions
            )
            logger.info(f"Restored permissions for user {callback.from_user.first_name} ({user_id})")
            
            # Удаляем сообщение с кнопкой
            try:
                await callback.bot.delete_message(
                    chat_id=chat_id,
                    message_id=pending_users[user_id]['message_id']
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass  # Ignore if can't delete
            
            # Отправляем приветствие
            welcome_message = await callback.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {callback.from_user.first_name} подтвердил, что он человек!\n"
                     f"Добро пожаловать в чат! Теперь вы можете писать сообщения."
            )
            
            # Удаляем приветственное сообщение через 3 секунды
            asyncio.create_task(delete_welcome_message_after_delay(welcome_message, 3))
            
            logger.info(f"✅ User {callback.from_user.first_name} ({callback.from_user.id}) successfully passed captcha in chat {chat_id}")
            logger.info(f"🎉 User is now fully verified and can participate in chat")
            
            # Сохраняем пользователя в БД
            try:
                from models.base import User
                async with async_session_local() as session:
                    # Проверяем, есть ли уже такой пользователь
                    result = await session.execute(
                        select(User).where(User.telegram_id == callback.from_user.id)
                    )
                    existing_user = result.scalar_one_or_none()
                    
                    if not existing_user:
                        # Создаем нового пользователя
                        new_user = User(
                            telegram_id=callback.from_user.id,
                            username=callback.from_user.username,
                            first_name=callback.from_user.first_name
                        )
                        session.add(new_user)
                        await session.commit()
                        logger.info(f"💾 Пользователь {callback.from_user.first_name} (@{callback.from_user.username or 'no_username'}) сохранен в БД")
                    else:
                        # Обновляем данные существующего пользователя
                        existing_user.username = callback.from_user.username
                        existing_user.first_name = callback.from_user.first_name
                        await session.commit()
                        logger.info(f"🔄 Данные пользователя {callback.from_user.first_name} обновлены в БД")
                        
            except Exception as e:
                logger.error(f"❌ Ошибка при сохранении пользователя в БД: {e}")
            
            # Сохраняем информацию о присоединении в invite_stats
            join_info = pending_users[callback.from_user.id].get('join_info')
            if join_info:
                try:
                    async with async_session_local() as session:
                        # Создаем виртуальную ссылку для отслеживания присоединений через капчу
                        virtual_link_url = f"virtual://captcha_join_{chat_id}"
                        
                        # Проверяем, существует ли уже такая ссылка
                        result = await session.execute(
                            select(InviteLink).where(InviteLink.link_url == virtual_link_url)
                        )
                        invite_link = result.scalar_one_or_none()
                        
                        if not invite_link:
                            # Создаем новую виртуальную ссылку
                            invite_link = InviteLink(
                                link_url=virtual_link_url,
                                name="Присоединение через капчу",
                                creator_id=None,  # Системная ссылка
                                source="captcha_verification",
                                created_at=join_info['join_date']
                            )
                            session.add(invite_link)
                            await session.flush()  # Получаем ID
                        
                        # Создаем запись о клике
                        invite_click = InviteClick(
                            user_id=callback.from_user.id,
                            link_url=virtual_link_url,
                            clicked_at=join_info['join_date']
                        )
                        session.add(invite_click)
                        
                        # Обновляем счетчик кликов
                        invite_link.click_count = (invite_link.click_count or 0) + 1
                        
                        await session.commit()
                        logger.info(f"📊 Recorded captcha join for user {callback.from_user.id} via virtual link")
                        
                except Exception as e:
                    logger.error(f"Failed to record captcha join stats: {e}")
            
            # Удаляем из ожидающих
            del pending_users[callback.from_user.id]
            
            # Подтверждаем нажатие кнопки
            await callback.answer("Подтверждено ✅")
            
        except Exception as e:
            logger.error(f"Captcha callback error: {e}")
            await callback.answer("❌ Ошибка при подтверждении", show_alert=True)