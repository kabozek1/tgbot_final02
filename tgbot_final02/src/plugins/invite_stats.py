"""
Плагин для отслеживания статистики инвайт-ссылок
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Union

from aiogram import Bot, Dispatcher
from aiogram.types import ChatMemberUpdated, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.base import InviteLink, InviteClick
from plugins.admin_panel.message_utils import edit_message
from utils.admin_utils import IsAdmin

logger = logging.getLogger(__name__)


async def handle_invite_chat_member(update: ChatMemberUpdated, async_session_local: async_sessionmaker):
    """
    Обрабатывает изменения участников чата для отслеживания инвайт-ссылок
    """
    try:
        # Processing ChatMemberUpdated silently for performance
        
        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status
        user_id = update.new_chat_member.user.id
        
        # Определяем link_url, name и creator_id
        determined_link_url = None
        determined_link_name = None
        determined_link_creator_id = None

        if update.invite_link:
            determined_link_url = update.invite_link.invite_link
            determined_link_name = update.invite_link.name or f"Ссылка {determined_link_url[-8:]}"
            determined_link_creator_id = update.invite_link.creator.id if update.invite_link.creator else None
            
            # Извлекаем хеш для логирования
            if determined_link_url.startswith('https://t.me/+'):
                hash_part = determined_link_url[len('https://t.me/+'):len('https://t.me/+')+8]
                # Invite link detected
            else:
                hash_part = determined_link_url[-8:] if len(determined_link_url) >= 8 else determined_link_url
                # Invite link detected
        elif update.chat.username:
            determined_link_url = f"virtual_link:{update.chat.username}"
            determined_link_name = f"Публичная группа: @{update.chat.username}"
            determined_link_creator_id = None  # Для виртуальных ссылок нет конкретного создателя
            hash_part = f"@{update.chat.username}"
            # Virtual invite link detected
        else:
            logger.warning(f"⚠️ User {user_id} joined but no invite link or public group username provided. Chat ID: {update.chat.id}")
            return  # Выходим, если не удалось определить ссылку
        
        # User status change tracked silently
        
        async with async_session_local() as session:
            if old_status in ["left", "kicked", "restricted"] and new_status in ["member", "administrator", "creator", "restricted"] and determined_link_url:
                # Пользователь присоединился
                # User joined via invite link
                
                # Извлекаем и логируем хеш для статистики
                if determined_link_url.startswith('https://t.me/+'):
                    display_hash = determined_link_url[len('https://t.me/+'):len('https://t.me/+')+8]
                elif determined_link_url.startswith('virtual_link:'):
                    display_hash = f"@{determined_link_url[13:]}"
                else:
                    display_hash = determined_link_url[-8:] if len(determined_link_url) >= 8 else determined_link_url
                
                # Statistics tracking enabled
                
                now = datetime.utcnow()
                
                # Processing invite link
                
                # Получаем или создаем запись об инвайт-ссылке
                result = await session.execute(
                    select(InviteLink).where(InviteLink.link_url == determined_link_url)
                )
                invite_link_obj = result.scalar_one_or_none()
                
                if not invite_link_obj:
                    # Создаем новую инвайт-ссылку
                    # Creating new invite link record
                    
                    invite_link_obj = InviteLink(
                        link_url=determined_link_url,
                        name=determined_link_name,
                        creator_id=determined_link_creator_id,
                        first_click=now,
                        last_click=now,
                        total_clicks=1
                    )
                    session.add(invite_link_obj)
                    # Added new InviteLink to session
                else:
                    # Обновляем существующую
                    # Updating existing invite link
                    
                    invite_link_obj.last_click = now
                    invite_link_obj.total_clicks += 1
                    # Total clicks updated
                
                # Создаем запись о клике
                # Creating invite click record
                invite_click = InviteClick(
                    user_id=user_id,
                    link_url=determined_link_url,
                    join_date=now
                )
                session.add(invite_click)
                # Added InviteClick to session
                
                try:
                    await session.commit()
                    # Successfully committed to database
                except Exception as commit_error:
                    logger.error(f"❌ Database commit failed: {commit_error}")
                    await session.rollback()
                    raise
                    
            elif old_status in ["member", "administrator"] and new_status in ["left", "kicked"]:
                # Пользователь покинул чат
                # User left the chat
                
                if invite_link and invite_link.invite_link:
                    link_url = invite_link.invite_link
                    now = datetime.utcnow()
                    
                    logger.info(f"🔄 Processing leave for invite link: {link_url}")
                    
                    # Находим запись о клике и обновляем дату выхода
                    result = await session.execute(
                        select(InviteClick).where(
                            and_(
                                InviteClick.user_id == user_id,
                                InviteClick.link_url == link_url,
                                InviteClick.left_date.is_(None)
                            )
                        ).order_by(desc(InviteClick.join_date)).limit(1)
                    )
                    invite_click = result.scalar_one_or_none()
                    
                    if invite_click:
                        logger.info(f"📝 Found invite click record, updating leave date")
                        invite_click.left_date = now
                        
                        # Увеличиваем счетчик ушедших в инвайт-ссылке
                        result = await session.execute(
                            select(InviteLink).where(InviteLink.link_url == link_url)
                        )
                        invite_link_obj = result.scalar_one_or_none()
                        if invite_link_obj:
                            logger.info(f"📊 Incrementing left count for invite link")
                            invite_link_obj.left_count += 1
                        
                        try:
                            await session.commit()
                            logger.info(f"✅ Successfully recorded leave: {link_url} for user {user_id}")
                        except Exception as commit_error:
                            logger.error(f"❌ Database commit failed for leave: {commit_error}")
                            await session.rollback()
                            raise
                    else:
                        logger.warning(f"⚠️ No invite click record found for user {user_id} and link {link_url}")
                else:
                    logger.warning(f"⚠️ User {user_id} left but no invite link provided")
            else:
                logger.debug(f"🔄 Status change not relevant for tracking: {old_status} -> {new_status}")
                        
    except Exception as e:
        logger.error(f"❌ Error in handle_invite_chat_member: {e}")
        logger.exception("Full traceback:")  # Добавляем полный traceback для отладки


def generate_activity_graph(data: List[Tuple[str, int]]) -> str:
    """
    Генерирует график активности в виде ASCII-столбиков
    
    Args:
        data: Список кортежей (дата, количество)
    
    Returns:
        str: Отформатированный график
    """
    if not data:
        return "📊 Нет данных за последние 7 дней"
    
    max_count = max(count for _, count in data) if data else 1
    graph_lines = []
    
    for date_str, count in data:
        # Вычисляем длину столбика (от 1 до 9 символов)
        bar_length = max(1, int((count / max_count) * 9)) if max_count > 0 else 1
        bar = "▇" * bar_length
        graph_lines.append(f"[{date_str}] {bar} {count}")
    
    return "\n".join(graph_lines)


async def build_invite_card(link: InviteLink, session, bot: Bot, page: int, total: int) -> str:
    """
    Строит карточку инвайт-ссылки
    
    Args:
        link: Объект InviteLink
        session: Сессия базы данных
        bot: Экземпляр бота
        page: Номер текущей страницы
        total: Общее количество ссылок
    
    Returns:
        str: Отформатированная карточка
    """
    try:
        # Получаем статистику кликов
        result = await session.execute(
            select(InviteClick).where(InviteClick.link_url == link.link_url)
        )
        clicks = result.scalars().all()
        
        # Подсчитываем метрики
        total_joins = len(clicks)
        current_members = len([c for c in clicks if c.left_date is None])
        left_members = len([c for c in clicks if c.left_date is not None])
        
        # Процент удержания
        retention_rate = (current_members / total_joins * 100) if total_joins > 0 else 0
        
        # Эмодзи статуса
        if retention_rate >= 80:
            status_emoji = "🟢"
        elif retention_rate >= 60:
            status_emoji = "🟡"
        else:
            status_emoji = "🔴"
        
        # Вовлеченность (процент написавших первое сообщение)
        engaged_count = len([c for c in clicks if c.first_message_date is not None])
        engagement_rate = (engaged_count / total_joins * 100) if total_joins > 0 else 0
        
        # Время последнего присоединения
        if link.last_click:
            time_diff = datetime.utcnow() - link.last_click
            if time_diff.days > 0:
                last_activity = f"{time_diff.days} дн. назад"
            elif time_diff.seconds > 3600:
                last_activity = f"{time_diff.seconds // 3600} ч. назад"
            else:
                last_activity = f"{time_diff.seconds // 60} мин. назад"
        else:
            last_activity = "Никогда"
        
        # График активности за последние 7 дней
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        result = await session.execute(
            select(
                func.date(InviteClick.join_date).label('date'),
                func.count(InviteClick.id).label('count')
            ).where(
                and_(
                    InviteClick.link_url == link.link_url,
                    InviteClick.join_date >= seven_days_ago
                )
            ).group_by(func.date(InviteClick.join_date)).order_by('date')
        )
        activity_data = []
        for row in result:
            if isinstance(row.date, str):
                try:
                    # Попытка преобразовать строку в datetime объект
                    dt_obj = datetime.strptime(row.date, "%Y-%m-%d") # Предполагаем формат 'YYYY-MM-DD'
                    activity_data.append((dt_obj.strftime("%d.%m"), row.count))
                except ValueError:
                    logger.warning(f"Could not parse date string: {row.date}")
            elif isinstance(row.date, datetime):
                activity_data.append((row.date.strftime("%d.%m"), row.count))
            else:
                logger.warning(f"Unexpected type for row.date: {type(row.date)}")
        
        activity_graph = generate_activity_graph(activity_data)
        
        # Формируем карточку
        first_click_formatted = "Неизвестно"
        if link.first_click:
            if isinstance(link.first_click, str):
                try:
                    dt_obj = datetime.strptime(link.first_click, "%Y-%m-%d %H:%M:%S.%f") # Примерный формат
                    first_click_formatted = dt_obj.strftime('%d.%m.%Y')
                except ValueError:
                    logger.warning(f"Could not parse first_click string: {link.first_click}")
            elif isinstance(link.first_click, datetime):
                first_click_formatted = link.first_click.strftime('%d.%m.%Y')
            else:
                logger.warning(f"Unexpected type for link.first_click: {type(link.first_click)}")

        # Извлекаем хеш из ссылки
        if link.link_url.startswith('https://t.me/+'):
            hash_part = link.link_url[len('https://t.me/+'):len('https://t.me/+')+8]
            logger.info(f"🏷️ Building card for Telegram link: {link.link_url}")
            logger.info(f"📊 Displaying hash: {hash_part}")
        elif link.link_url.startswith('virtual_link:'):
            hash_part = f"@{link.link_url[13:]}"
            logger.info(f"🏷️ Building card for virtual link: {link.link_url}")
            logger.info(f"📊 Displaying hash: {hash_part}")
        else:
            hash_part = link.link_url[-8:] if len(link.link_url) >= 8 else link.link_url
            logger.info(f"🏷️ Building card for other link: {link.link_url}")
            logger.info(f"📊 Displaying hash: {hash_part}")
        
        card = f"""🔗 <b>{hash_part}</b> — {status_emoji} {retention_rate:.0f}% удержания

📥 <b>Всего:</b> {total_joins}
✅ <b>Осталось:</b> {current_members} ({(current_members/total_joins*100):.0f}%)
📉 <b>Ушло:</b> {left_members} ({(left_members/total_joins*100):.0f}%)
⏱️ <b>Последний:</b> {last_activity}
📲 <b>Вовлечённость:</b> {engagement_rate:.0f}% (написали после вступления)

📅 <b>Активна с:</b> {first_click_formatted}

📈 <b>Присоединились за 7 дней:</b>
{activity_graph}"""
        
        return card
        
    except Exception as e:
        logger.error(f"Error building invite card: {e}")
        return f"❌ Ошибка при построении карточки: {e}"


async def show_invite_page(obj: Union[Message, CallbackQuery], bot: Bot, session_maker: async_sessionmaker, page: int = 1):
    """Показывает страницу со статистикой инвайт-ссылки"""
    async with session_maker() as session:
        try:
            # Получаем общее количество ссылок
            total_result = await session.execute(
                select(func.count(InviteLink.id)).filter_by(is_archived=False)
            )
            total_links = total_result.scalar_one()
            logger.info(f"📊 Found {total_links} total invite links, showing page {page}")
            
            if total_links == 0:
                logger.info(f"❌ No active invite links found")
                text = "📊 <b>Статистика инвайт-ссылок</b>\n\n❌ Активных инвайт-ссылок не найдено."
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="invite_refresh_1")],
                    [InlineKeyboardButton(text="◀️ Назад к выбору статистики", callback_data="admin:stats_detailed")]
                ])
                
                if isinstance(obj, CallbackQuery):
                    await edit_message(obj, text, keyboard, bot=bot)
                else:
                    await obj.answer(text, reply_markup=keyboard, parse_mode="HTML")
                return
            
            # Получаем ссылку для текущей страницы
            link_result = await session.execute(
                select(InviteLink)
                .filter_by(is_archived=False)
                .order_by(InviteLink.last_click.desc())
                .offset(page - 1)
                .limit(1)
            )
            link = link_result.scalar_one_or_none()
            
            if not link:
                # Если страница не существует, показываем первую
                return await show_invite_page(obj, bot, session_maker, 1)
            
            # Строим карточку
            card_text = await build_invite_card(link, session, bot, page, total_links)
            logger.info(f"✅ Successfully built card for link: {link.link_url[:50]}...")
            
            # Создаем клавиатуру навигации
            keyboard_buttons = []
            nav_row = []
            
            if page > 1:
                nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"invite_prev_{page}"))
            
            nav_row.append(InlineKeyboardButton(text=f"🔗 Ссылка {page} из {total_links}", callback_data="noop"))
            
            if page < total_links:
                nav_row.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"invite_next_{page}"))
            
            keyboard_buttons.append(nav_row)
            keyboard_buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"invite_refresh_{page}")])
            keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад к выбору статистики", callback_data="admin:stats_detailed")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            if isinstance(obj, CallbackQuery):
                await edit_message(obj, card_text, keyboard, bot=bot)
                logger.info(f"📤 Card sent via callback to user {obj.from_user.id}")
            else:
                await obj.answer(card_text, reply_markup=keyboard, parse_mode="HTML")
                logger.info(f"📤 Card sent via message to user {obj.from_user.id}")
                
        except Exception as e:
            logger.error(f"Error in show_invite_page: {e}")
            error_text = "❌ Произошла ошибка при загрузке статистики инвайт-ссылок."
            if isinstance(obj, CallbackQuery):
                await edit_message(obj, error_text, bot=bot)
            else:
                await obj.answer(error_text, parse_mode="HTML")


async def handle_invite_callback(callback: CallbackQuery, bot: Bot, session_maker: async_sessionmaker):
    """
    Обработчик callback-кнопок для навигации по инвайт-ссылкам
    """
    try:
        data = callback.data
        
        if data.startswith("invite_prev_"):
            page = int(data.split("_")[-1])
            new_page = max(1, page - 1)
            await show_invite_page(callback, bot, session_maker, new_page)
            
        elif data.startswith("invite_next_"):
            page = int(data.split("_")[-1])
            new_page = page + 1
            await show_invite_page(callback, bot, session_maker, new_page)
            
        elif data.startswith("invite_refresh_"):
            page = int(data.split("_")[-1])
            await show_invite_page(callback, bot, session_maker, page)
            
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in handle_invite_callback: {e}")
        await callback.answer("❌ Ошибка при обработке")


async def handle_invites_command(message: Message, bot: Bot, session_maker: async_sessionmaker):
    """
    Обработчик команды /invites
    """
    try:
        logger.info(f"📋 User {message.from_user.id} requested /invites command")
        logger.info(f"💬 Chat ID: {message.chat.id}")
        await show_invite_page(message, bot, session_maker, 1)
    except Exception as e:
        logger.error(f"Error in handle_invites_command: {e}")
        await message.answer(f"❌ Ошибка при выполнении команды: {e}")


def register(dp: Dispatcher, bot: Bot, async_session_local: async_sessionmaker):
    logger.debug("Attempting to register invite stats plugin handlers.")
    """Регистрирует обработчики плагина"""
    try:
        # Регистрируем обработчик изменений участников чата
        async def handle_invite_chat_member_wrapper(update: ChatMemberUpdated):
            logger.debug(f"ChatMemberUpdated received: {update}")
            return await handle_invite_chat_member(update, async_session_local)
        
        # Регистрируем для обновлений участников чата (не бота)
        dp.chat_member.register(handle_invite_chat_member_wrapper)
        
        # Также регистрируем для обновлений самого бота (на случай если нужно)
        dp.my_chat_member.register(handle_invite_chat_member_wrapper)
        
        # Регистрируем обработчик callback-кнопок
        async def handle_invite_callback_wrapper(callback: CallbackQuery):
            return await handle_invite_callback(callback, bot, async_session_local)
        
        dp.callback_query.register(
            handle_invite_callback_wrapper,
            lambda c: c.data and c.data.startswith("invite_")
        )
        
        # Регистрируем команду /invites
        async def handle_invites_command_wrapper(message: Message):
            return await handle_invites_command(message, bot, async_session_local)
        
        dp.message.register(
            handle_invites_command_wrapper,
            Command("invites"),
            IsAdmin()
        )
        
        logger.info("✅ Invite stats plugin registered successfully")
        
    except Exception as e:
        logger.error(f"❌ Error registering invite stats plugin: {e}")