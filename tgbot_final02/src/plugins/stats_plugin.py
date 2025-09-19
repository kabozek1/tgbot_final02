import logging
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime, timedelta
from functools import partial
import inspect # Добавил inspect

from aiogram import BaseMiddleware, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatMember, ContentType, ChatMemberUpdated # Import ChatMemberUpdated
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import func, distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker # Removed create_async_engine

from config import get_settings
from models.base import MessageLog, Membership, ChatInfo, InviteClick # Import Membership
from utils.admin_utils import is_user_admin

logger = logging.getLogger(__name__)
settings = get_settings()


async def delete_command_message(message: Message):
    """Удаляет команду после обработки"""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass  # Игнорируем ошибки удаления

# --- Middleware for Data Collection ---
class StatsMiddleware(BaseMiddleware):
    def __init__(self, async_session_local: async_sessionmaker):
        self.async_session_local = async_session_local

    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """Process message for stats logging."""
        logger.info(f"🔍 STATS_MIDDLEWARE: Processing message {event.message_id} from user {event.from_user.id} in chat {event.chat.id}")
        logger.info(f"🔍 STATS_MIDDLEWARE: Message text: '{event.text[:100] if event.text else 'No text'}...'")
        logger.info(f"🔍 STATS_MIDDLEWARE: Is reply: {bool(event.reply_to_message)}")
        
        # Skip non-message events
        if not isinstance(event, Message):
            logger.info(f"🔍 STATS_MIDDLEWARE: Skipping non-message event")
            return await handler(event, data)

        if not event.from_user or event.from_user.is_bot:
            logger.info(f"🔍 STATS_MIDDLEWARE: Skipping bot message or message without user")
            return await handler(event, data)

        # --- Save Chat Info (только для групповых чатов) ---
        try:
            # Пропускаем личные чаты (chat_id > 0)
            if event.chat.id > 0:
                return await handler(event, data)
                
            # Добавляем запись о топике ТОЛЬКО если это реальный форумный топик,
            # созданный через интерфейс тем (а не тред обсуждения поста канала).
            # Признак: в сообщении присутствует service-message forum_topic_created.
            # Для основного чата (topic_id is None) ничего не добавляем.
            is_topic_message = bool(getattr(event, "is_topic_message", False))
            has_forum_topic_created = bool(getattr(event, "forum_topic_created", None))

            if is_topic_message and has_forum_topic_created and event.message_thread_id is not None:
                async with self.async_session_local() as session:
                    existing_chat_info = await session.execute(
                        select(ChatInfo).filter_by(chat_id=event.chat.id, topic_id=event.message_thread_id)
                    )
                    if existing_chat_info.scalar_one_or_none() is None:
                        new_chat_info = ChatInfo(
                            chat_id=event.chat.id,
                            topic_id=event.message_thread_id
                        )
                        session.add(new_chat_info)
                        await session.commit()
        except Exception as e:
            logger.warning(f"Could not save chat info: {e}")
            # await session.rollback() # Rollback is handled by the context manager


        if event.text and event.text.startswith('/'):
            logger.info(f"🔍 STATS_MIDDLEWARE: Processing command message, passing to handlers")
            return await handler(event, data)

        allowed_content_types = [
            ContentType.TEXT, ContentType.VOICE, ContentType.VIDEO_NOTE,
            ContentType.STICKER, ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO
        ]
        if event.content_type not in allowed_content_types:
            return await handler(event, data)

        # logger.info(f"StatsMiddleware: Processing message {event.message_id} from user {event.from_user.id}.")
        async with self.async_session_local() as session:
            try:
                # Check if this message is a reply to another message
                reply_to_message_id = None
                if event.reply_to_message:
                    reply_to_message_id = event.reply_to_message.message_id
                    # logger.info(f"Message {event.message_id} is a reply to message {reply_to_message_id}")

                log_entry = MessageLog(
                    message_id=event.message_id,
                    chat_id=event.chat.id,
                    user_id=event.from_user.id,
                    topic_id=event.message_thread_id,
                    timestamp=event.date,
                    message_type=event.content_type,
                    text=event.text or '', # Ensure text is not None
                    reply_to_message_id=reply_to_message_id,
                    replies_count=0  # New messages start with 0 replies
                )
                session.add(log_entry)
                
                # Безопасное расширение для отслеживания первых сообщений пользователей по инвайт-ссылкам
                try:
                    invite_click_result = await session.execute(
                        select(InviteClick).filter_by(
                            user_id=event.from_user.id,
                            first_message_date=None
                        ).limit(1)
                    )
                    invite_click = invite_click_result.scalar_one_or_none()
                    
                    if invite_click:
                        invite_click.first_message_date = event.date
                        logger.debug(f"Set first_message_date for user {event.from_user.id} from invite link {invite_click.link_url}")
                except Exception as e:
                    logger.warning(f"Failed to update first_message_date for invite click: {e}")
                    # Не прерываем основную логику при ошибке
                
                await session.commit()

                # If this is a reply, increment the reply count for the original message
                if reply_to_message_id:
                    logger.info(f"🔍 STATS_REPLY: Message {event.message_id} is a reply to message {reply_to_message_id}")
                    try:
                        # Find the original message and increment its reply count
                        # Убираем фильтр по topic_id, так как оригинальное сообщение может быть из другого топика
                        original_message_result = await session.execute(
                            select(MessageLog).filter_by(
                                message_id=reply_to_message_id,
                                chat_id=event.chat.id
                            )
                        )
                        original_message = original_message_result.scalar_one_or_none()
                        
                        if original_message:
                            old_count = original_message.replies_count or 0
                            original_message.replies_count = old_count + 1
                            await session.commit()
                            logger.info(f"✅ STATS_REPLY: Incremented reply count for message {reply_to_message_id} from {old_count} to {original_message.replies_count}")
                        else:
                            logger.info(f"⚠️ STATS_REPLY: Could not find original message {reply_to_message_id} in chat {event.chat.id} (message may be from before stats tracking started)")
                    except Exception as e:
                        logger.error(f"❌ STATS_REPLY: Failed to increment reply count for message {reply_to_message_id}: {e}")
                        await session.rollback()

            except Exception as e:
                logger.error(f"Failed to log message to stats DB: {e}")
                await session.rollback()

        return await handler(event, data)

async def handle_chat_member_update(update: ChatMemberUpdated, async_session_local: async_sessionmaker):
    """Logs user join/leave/ban events."""
    logger.debug(f"Handling ChatMemberUpdated for user {update.new_chat_member.user.id} in chat {update.chat.id}.")

    event_type = None
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    if new_status == 'member' and old_status not in ['member', 'administrator', 'creator']:
        event_type = 'join'
    elif new_status == 'left' and old_status in ['member', 'administrator']:
        event_type = 'leave'
    elif new_status == 'kicked' and old_status != 'kicked':
        event_type = 'ban'
    elif new_status == 'member' and old_status == 'kicked':
        event_type = 'unban'
    elif new_status == 'restricted' and old_status not in ['restricted', 'kicked']:
        event_type = 'mute'
    elif new_status == 'member' and old_status == 'restricted':
        event_type = 'unmute'

    if event_type:
        async with async_session_local() as session:
            try:
                log_entry = Membership(
                    user_id=update.new_chat_member.user.id,
                    chat_id=update.chat.id,
                    event_type=event_type,
                    date=update.date
                )
                session.add(log_entry)
                await session.commit()
                logger.debug(f"Membership event '{event_type}' logged for user {update.new_chat_member.user.id}.")
            except Exception as e:
                logger.error(f"Failed to log membership event: {e}")
                await session.rollback()

# --- Command Handler for Reporting ---
async def handle_stats_command(message: Message, bot: Bot, async_session_local: async_sessionmaker):
    """Handles the /stats command, providing a comprehensive chat report."""
    logger.debug(f"/stats command received in chat {message.chat.id} from user {message.from_user.id}.")
    
    # Проверяем права администратора
    if not await is_user_admin(message, message.from_user.id, async_session_local):
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        # Удаляем команду даже при отсутствии прав
        await delete_command_message(message)
        return
    
    async with async_session_local() as session:
        try:
            chat_id = message.chat.id
            response_parts = []

            # --- 1. Overall Chat Statistics ---
            response_parts.append("📊 <u><b>Общая статистика по всему чату</b></u>\n\n")
            
            total_messages_result = await session.execute(select(func.count(MessageLog.id)).filter(MessageLog.chat_id == chat_id))
            total_messages = total_messages_result.scalar_one()

            if not total_messages:
                await message.answer("📊 Статистика для этого чата пока недоступна. Данные еще не собраны.")
                return

            total_users_result = await session.execute(select(func.count(distinct(MessageLog.user_id))).filter(MessageLog.chat_id == chat_id))
            total_users = total_users_result.scalar_one()

            first_message_date_result = await session.execute(select(func.min(MessageLog.timestamp)).filter(MessageLog.chat_id == chat_id))
            first_message_date = first_message_date_result.scalar_one_or_none()

            now = datetime.utcnow()
            messages_24h_result = await session.execute(select(func.count(MessageLog.id)).filter(MessageLog.chat_id == chat_id, MessageLog.timestamp >= (now - timedelta(hours=24))))
            messages_24h = messages_24h_result.scalar_one()

            messages_7d_result = await session.execute(select(func.count(MessageLog.id)).filter(MessageLog.chat_id == chat_id, MessageLog.timestamp >= (now - timedelta(days=7))))
            messages_7d = messages_7d_result.scalar_one()

            messages_30d_result = await session.execute(select(func.count(MessageLog.id)).filter(MessageLog.chat_id == chat_id, MessageLog.timestamp >= (now - timedelta(days=30))))
            messages_30d = messages_30d_result.scalar_one()

            response_parts.append(f"  <b>Всего сообщений:</b> {total_messages}\n")
            response_parts.append(f"  <b>Уникальных участников:</b> {total_users}\n\n")
            response_parts.append(f"  <u><b>Объем активности:</b></u>\n")
            response_parts.append(f"    - За 24 часа: <b>{messages_24h}</b> сообщений\n")
            response_parts.append(f"    - За 7 дней: <b>{messages_7d}</b> сообщений\n")
            response_parts.append(f"    - За 30 дней: <b>{messages_30d}</b> сообщений\n\n")

            # Peak activity hours
            peak_hours_result = await session.execute(
                select(
                    func.strftime('%H', MessageLog.timestamp).label('hour'),
                    func.count(MessageLog.id).label('message_count')
                )
                .filter(MessageLog.chat_id == chat_id)
                .group_by('hour')
                .order_by(func.count(MessageLog.id).desc())
                .limit(3)
            )
            peak_hours_query = peak_hours_result.all()

            if peak_hours_query:
                response_parts.append("  <u><b>Пиковая активность по часам (UTC):</b></u>\n")
                for hour, count in peak_hours_query:
                    percentage = (count / total_messages) * 100
                    response_parts.append(f"    - <b>{hour}:00-{(int(hour) + 1):02}:00</b>: {count} сообщ. ({percentage:.1f}%)\n")
                response_parts.append("\n")

            # Top users
            top_users_result = await session.execute(
                select(MessageLog.user_id, func.count(MessageLog.user_id).label('message_count'))
                .filter(MessageLog.chat_id == chat_id)
                .group_by(MessageLog.user_id)
                .order_by(func.count(MessageLog.user_id).desc())
                .limit(5)
            )
            top_users_query = top_users_result.all()

            user_names_cache = {}
            for user_id, _ in top_users_query:
                if user_id not in user_names_cache:
                    try:
                        chat_member: ChatMember = await bot.get_chat_member(chat_id, user_id)
                        user_display_name = chat_member.user.username or chat_member.user.full_name
                        user_names_cache[user_id] = user_display_name or f"User {user_id}"
                    except Exception as e:
                        logger.warning(f"Could not fetch user info for {user_id}: {e}")
                        user_names_cache[user_id] = f"User {user_id}"

            response_parts.append("<u><b>Топ-5 активных пользователей (весь чат):</b></u>\n")
            if top_users_query:
                for i, (user_id, count) in enumerate(top_users_query, 1):
                    user_display_name = user_names_cache.get(user_id, f"User {user_id}")
                    user_mention = f"<a href='tg://user?id={user_id}'>{user_display_name}</a>"
                    response_parts.append(f"  {i}. {user_mention}: <b>{count}</b> сообщений\n")
            else:
                response_parts.append("  Нет данных.\n")

            # Content Type Distribution
            content_type_counts_result = await session.execute(
                select(MessageLog.message_type, func.count(MessageLog.id))
                .filter(MessageLog.chat_id == chat_id)
                .group_by(MessageLog.message_type)
                .order_by(func.count(MessageLog.id).desc())
            )
            content_type_counts = content_type_counts_result.all()

            if content_type_counts:
                response_parts.append("\n<u><b>Распределение контента:</b></u>\n")
                for msg_type, count in content_type_counts:
                    percentage = (count / total_messages) * 100
                    response_parts.append(f"  - {str(msg_type).capitalize()}: <b>{count}</b> ({percentage:.1f}%)\n")

            # Top Posts by Replies
            top_posts_by_replies_result = await session.execute(
                select(
                    MessageLog.message_id,
                    MessageLog.text,
                    MessageLog.user_id,
                    MessageLog.timestamp,
                    MessageLog.replies_count
                )
                .filter(
                    MessageLog.chat_id == chat_id,
                    MessageLog.replies_count > 0
                )
                .order_by(MessageLog.replies_count.desc())
                .limit(5)
            )
            top_posts_by_replies = top_posts_by_replies_result.all()

            if top_posts_by_replies:
                response_parts.append("\n<u><b>🔥 Топ-5 постов по количеству ответов:</b></u>\n")
                for i, (msg_id, text, user_id, timestamp, replies_count) in enumerate(top_posts_by_replies, 1):
                    # Get user name
                    try:
                        chat_member: ChatMember = await bot.get_chat_member(chat_id, user_id)
                        user_display_name = chat_member.user.username or chat_member.user.full_name
                        user_display_name = user_display_name or f"User {user_id}"
                    except Exception as e:
                        logger.warning(f"Could not fetch user info for {user_id}: {e}")
                        user_display_name = f"User {user_id}"
                    
                    # Truncate text if too long
                    display_text = text[:50] + "..." if text and len(text) > 50 else (text or "[Медиа]")
                    
                    # Format timestamp
                    time_str = timestamp.strftime("%d.%m %H:%M")
                    
                    response_parts.append(f"  {i}. <b>{replies_count}</b> ответов\n")
                    response_parts.append(f"     👤 {user_display_name} | {time_str}\n")
                    response_parts.append(f"     💬 \"{display_text}\"\n\n")
            else:
                response_parts.append("\n<u><b>🔥 Топ-посты по ответам:</b></u>\n  Пока нет постов с ответами.\n")

            # Silent Users
            joined_users_result = await session.execute(
                select(distinct(Membership.user_id))
                .filter(Membership.chat_id == chat_id, Membership.event_type == 'join')
            )
            joined_users = {user_id for user_id, in joined_users_result.all()}

            messaged_users_result = await session.execute(
                select(distinct(MessageLog.user_id))
                .filter(MessageLog.chat_id == chat_id)
            )
            messaged_users = {user_id for user_id, in messaged_users_result.all()}

            silent_users_ids = joined_users - messaged_users

            if silent_users_ids:
                response_parts.append("\n<u><b>Молчаливые пользователи (присоединились, но не писали):</b></u>\n")
                silent_users_display_names = []
                for user_id in list(silent_users_ids)[:10]: # Limit to 10
                    try:
                        chat_member: ChatMember = await bot.get_chat_member(chat_id, user_id)
                        user_display_name = chat_member.user.username or chat_member.user.full_name
                        silent_users_display_names.append(f"<a href='tg://user?id={user_id}'>{user_display_name or f'User {user_id}'}</a>")
                    except Exception as e:
                        logger.warning(f"Could not fetch info for silent user {user_id}: {e}")
                        silent_users_display_names.append(f"<a href='tg://user?id={user_id}'>User {user_id}</a>")
                
                if silent_users_display_names:
                    response_parts.append("  " + ", ".join(silent_users_display_names) + "\n")
                if len(silent_users_ids) > 10:
                    response_parts.append(f"  ... и еще {len(silent_users_ids) - 10} молчаливых пользователей.\n")
            else:
                response_parts.append("\n<u><b>Молчаливые пользователи:</b></u>\n  Нет (или нет данных о присоединившихся).\n")

            # --- 2. Per-Topic Statistics ---
            response_parts.append("\n📊 <u><b>Статистика по топикам</b></u>\n")

            # Используем только реальные форумные топики из ChatInfo для этого чата
            allowed_topic_ids_result = await session.execute(
                select(ChatInfo.topic_id).filter(ChatInfo.chat_id == chat_id).distinct()
            )
            allowed_topic_ids = [item[0] for item in allowed_topic_ids_result.all()]

            # Добавляем общий чат (None), если по нему есть сообщения
            has_general_messages_result = await session.execute(
                select(func.count(MessageLog.id)).filter(
                    MessageLog.chat_id == chat_id,
                    MessageLog.topic_id.is_(None)
                )
            )
            if (has_general_messages_result.scalar_one() or 0) > 0 and None not in allowed_topic_ids:
                allowed_topic_ids.append(None)

            # Убираем возможные дубликаты (например, двойной None)
            # и сортируем стабильно с учётом None
            unique_topic_ids = []
            seen = set()
            for tid in allowed_topic_ids:
                key = ('__none__' if tid is None else tid)
                if key not in seen:
                    seen.add(key)
                    unique_topic_ids.append(tid)

            if not any(tid is not None for tid in unique_topic_ids) and any(tid is None for tid in unique_topic_ids):
                response_parts.append("  Сообщений в топиках пока нет.\n")
            else:
                response_parts.append("  <i>(Названия топиков отображаются, если установлены командой /set_name_topic)</i>\n")
                for topic_id in sorted(unique_topic_ids, key=lambda x: (x is None, x)):
                    # Correctly filter for the current topic_id, handling the None case
                    if topic_id is None:
                        topic_filter = MessageLog.topic_id.is_(None)
                        topic_name = "Основной чат (General)"
                    else:
                        topic_filter = MessageLog.topic_id == topic_id
                        
                        # Get topic name from database
                        topic_name_result = await session.execute(
                            select(ChatInfo.topic_name).filter_by(
                                chat_id=chat_id,
                                topic_id=topic_id
                            )
                        )
                        topic_name_from_db = topic_name_result.scalar_one_or_none()
                        
                        if topic_name_from_db:
                            topic_name = f"{topic_name_from_db} ({topic_id})"
                        else:
                            topic_name = f"Топик ID: {topic_id}"

                    # Get total messages for the topic
                    topic_total_messages_result = await session.execute(
                        select(func.count(MessageLog.id))
                        .filter(MessageLog.chat_id == chat_id, topic_filter)
                    )
                    topic_total_messages = topic_total_messages_result.scalar_one()

                    # Get total unique users for the topic
                    topic_total_users_result = await session.execute(
                        select(func.count(distinct(MessageLog.user_id)))
                        .filter(MessageLog.chat_id == chat_id, topic_filter)
                    )
                    topic_total_users = topic_total_users_result.scalar_one()
                    
                    if topic_total_messages > 0:
                        response_parts.append(f"\n  <u><b>{topic_name}</b></u>\n")
                        response_parts.append(f"    - <b>Сообщений:</b> {topic_total_messages}\n")
                        response_parts.append(f"    - <b>Участников:</b> {topic_total_users}\n")

                        # Пиковая активность по часам для топика
                        topic_peak_hours_result = await session.execute(
                            select(
                                func.strftime('%H', MessageLog.timestamp).label('hour'),
                                func.count(MessageLog.id).label('message_count')
                            )
                            .filter(MessageLog.chat_id == chat_id, topic_filter)
                            .group_by('hour')
                            .order_by(func.count(MessageLog.id).desc())
                            .limit(3)
                        )
                        topic_peak_hours = topic_peak_hours_result.all()
                        if topic_peak_hours:
                            response_parts.append(f"    - <b>Пик по часам (UTC):</b>\n")
                            for hour, count in topic_peak_hours:
                                percentage = (count / topic_total_messages) * 100
                                response_parts.append(f"      • {hour}:00-{(int(hour)+1):02}:00 — {count} ({percentage:.1f}%)\n")

            if first_message_date:
                response_parts.append(f"\n<i>Статистика ведется с {first_message_date.strftime('%d.%m.%Y')}</i>")

            await message.answer("".join(response_parts), parse_mode="HTML")
            
            # Удаляем команду после обработки
            await delete_command_message(message)

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            await message.answer("❌ Не удалось получить статистику. Произошла ошибка.")
            # Удаляем команду даже при ошибке
            await delete_command_message(message)

# --- Plugin Registration ---
def register(dp: Dispatcher, bot: Bot, async_session_local: async_sessionmaker):
    """Register stats plugin components."""
    dp.message.middleware(StatsMiddleware(async_session_local))
    logger.debug("✅ Registered StatsMiddleware for messages")

    # Register /stats command handler
    stats_command_handler = partial(handle_stats_command, bot=bot, async_session_local=async_session_local)
    dp.message.register(stats_command_handler, Command(commands=["stats"]))
    logger.debug("✅ Registered /stats command handler")

    chat_member_handler_with_session = partial(handle_chat_member_update, async_session_local=async_session_local)
    dp.chat_member.register(chat_member_handler_with_session)
    logger.debug("✅ Registered ChatMemberUpdated handler for stats.")