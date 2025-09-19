"""
Управление триггерами в админ панели
"""

import logging
from datetime import datetime
from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import func, desc

from models.base import Trigger
from .message_utils import edit_message, process_user_input

logger = logging.getLogger(__name__)


class TriggerStates(StatesGroup):
    """Состояния для управления триггерами"""
    waiting_trigger_text = State()
    waiting_response_text = State()


def get_triggers_menu_keyboard(triggers: list, page: int = 0, per_page: int = 3) -> InlineKeyboardMarkup:
    """Клавиатура меню триггеров с пагинацией"""
    buttons = []
    
    # Заголовок с номером страницы
    total_pages = (len(triggers) + per_page - 1) // per_page if triggers else 1
    current_page = page + 1
    
    # Показываем триггеры для текущей страницы
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_triggers = triggers[start_idx:end_idx]
    
    for trigger in page_triggers:
        # Статус триггера (включен/выключен)
        status_emoji = "🟢" if trigger.is_active else "🔴"
        
        # Обрезаем длинные триггеры и ответы для отображения
        trigger_display = trigger.trigger_text[:20] + "..." if len(trigger.trigger_text) > 20 else trigger.trigger_text
        response_display = trigger.response_text[:20] + "..." if len(trigger.response_text) > 20 else trigger.response_text
        
        # Информация о триггере
        trigger_info = f'{status_emoji} "{trigger_display}" → "{response_display}"'
        buttons.append([InlineKeyboardButton(text=trigger_info, callback_data=f"trigger_view:{trigger.id}")])
        
        # Статистика
        if trigger.trigger_count > 0:
            last_time = "никогда"
            if trigger.last_triggered:
                time_diff = datetime.utcnow() - trigger.last_triggered
                if time_diff.days > 0:
                    last_time = f"{time_diff.days} д. назад"
                elif time_diff.seconds > 3600:
                    last_time = f"{time_diff.seconds // 3600} ч. назад"
                else:
                    last_time = f"{time_diff.seconds // 60} мин. назад"
            
            stats_text = f"📥 {trigger.trigger_count} срабатываний | ⏱ последний: {last_time}"
        else:
            stats_text = "📥 0 срабатываний"
        
        buttons.append([InlineKeyboardButton(text=stats_text, callback_data="noop")])
        
        # Кнопки управления триггером
        toggle_text = "⛔️ Выкл" if trigger.is_active else "✅ Вкл"
        action_buttons = [
            InlineKeyboardButton(text=toggle_text, callback_data=f"trigger_toggle:{trigger.id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"trigger_delete:{trigger.id}")
        ]
        buttons.append(action_buttons)
        
        # Добавляем невидимый разделитель той же ширины что и меню
        if trigger != page_triggers[-1]:  # Не добавляем разделитель после последнего триггера
            buttons.append([InlineKeyboardButton(text="⠀", callback_data="noop")])

    
    # Добавляем разделитель после последнего триггера перед навигацией/кнопками действий
    if page_triggers:  # Если есть триггеры на странице
        buttons.append([InlineKeyboardButton(text="⠀", callback_data="noop")])
    
    # Навигация по страницам
    nav_buttons = []
    if total_pages > 1:
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"triggers_page:{page-1}"))
        
        nav_buttons.append(InlineKeyboardButton(text=f"📋 Страница {current_page} из {total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"triggers_page:{page+1}"))
        
        buttons.append(nav_buttons)
    
    # Кнопки действий
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить триггер", callback_data="trigger_add"),
        InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin:main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_trigger_view_keyboard(trigger_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра конкретного триггера"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"trigger_edit:{trigger_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"trigger_delete:{trigger_id}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к триггерам", callback_data="admin:triggers")]
    ])


async def show_triggers_menu(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot, page: int = 0, answer_callback: bool = True):
    """Показать меню управления триггерами"""
    # Отвечаем на callback query сразу, чтобы убрать индикатор загрузки
    if answer_callback:
        try:
            await query.answer()
        except Exception:
            pass  # Игнорируем ошибки, если callback уже был отвечен
    
    await state.clear()
    
    async with async_session_local() as session:
        # Получаем все триггеры, отсортированные по дате создания
        result = await session.execute(
            select(Trigger).order_by(desc(Trigger.created_at))
        )
        triggers = result.scalars().all()
    
    # Формируем текст заголовка
    total_triggers = len(triggers)
    per_page = 3
    total_pages = (total_triggers + per_page - 1) // per_page if total_triggers > 0 else 1
    current_page = page + 1
    
    if total_triggers == 0:
        text = "🛎 Триггеры\n\n❌ Триггеры не найдены.\n\nДобавьте первый триггер с помощью кнопки ниже."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить триггер", callback_data="trigger_add")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin:main_menu")]
        ])
    else:
        text = f"🛎 Триггеры — Страница {current_page} из {total_pages}\n\n"
        keyboard = get_triggers_menu_keyboard(triggers, page)
    
    # Используем edit_message и сохраняем message_id в состоянии
    message_id = await edit_message(query, text, keyboard, bot=bot)
    if message_id:
        await state.update_data(last_message_id=message_id)


async def handle_trigger_add(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Начать добавление нового триггера"""
    await state.set_state(TriggerStates.waiting_trigger_text)
    
    text = (
        "📌 Введите текст триггера...\n\n"
        "💡 Можно использовать несколько вариантов через символ |:\n"
        "Например: <code>цена?|стоимость?|сколько стоит</code>\n\n"
        "❗️ Регистр не учитывается"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:triggers")]
    ])
    
    # Используем edit_message и сохраняем message_id в состоянии
    message_id = await edit_message(query, text, keyboard, bot=bot)
    if message_id:
        await state.update_data(last_message_id=message_id)


async def handle_trigger_text_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода текста триггера"""
    trigger_text = message.text.strip()
    
    if not trigger_text:
        text = "❌ Текст триггера не может быть пустым. Попробуйте еще раз:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:triggers")]
        ])
        await process_user_input(bot, message, text, keyboard, state=state)
        return
    
    # Сохраняем текст триггера в состоянии
    await state.update_data(trigger_text=trigger_text)
    await state.set_state(TriggerStates.waiting_response_text)
    
    text = (
        f"✅ Триггер: <code>{trigger_text}</code>\n\n"
        "💬 Теперь введите ответ бота..."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:triggers")]
    ])
    
    await process_user_input(bot, message, text, keyboard, state=state)


async def handle_response_text_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода ответа триггера"""
    response_text = message.text.strip()
    
    if not response_text:
        text = "❌ Ответ не может быть пустым. Попробуйте еще раз:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:triggers")]
        ])
        await process_user_input(bot, message, text, keyboard, state=state)
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    trigger_text = data.get('trigger_text')
    
    # Создаем новый триггер в БД
    async with async_session_local() as session:
        new_trigger = Trigger(
            trigger_text=trigger_text,
            response_text=response_text,
            is_active=True,
            trigger_count=0
        )
        session.add(new_trigger)
        await session.commit()
    
    # Сохраняем message_id перед очисткой состояния
    data = await state.get_data()
    last_message_id = data.get('last_bot_message_id') or data.get('last_message_id')
    
    await state.clear()
    
    # Восстанавливаем message_id после очистки
    if last_message_id:
        await state.update_data(last_message_id=last_message_id)
    
    text = (
        f"✅ Триггер успешно добавлен и включён!\n\n"
        f"🔤 Триггер: <code>{trigger_text}</code>\n"
        f"💬 Ответ: <code>{response_text}</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к триггерам", callback_data="admin:triggers")]
    ])
    
    await process_user_input(bot, message, text, keyboard, state=state)


async def handle_trigger_toggle(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Переключить состояние триггера (вкл/выкл)"""
    trigger_id = int(query.data.split(':')[1])
    
    async with async_session_local() as session:
        result = await session.execute(select(Trigger).filter_by(id=trigger_id))
        trigger = result.scalar_one_or_none()
        
        if trigger:
            trigger.is_active = not trigger.is_active
            await session.commit()
            
            status = "включён" if trigger.is_active else "выключен"
            await query.answer(f"Триггер {status}")
        else:
            await query.answer("Триггер не найден")
    
    # Обновляем меню триггеров
    await show_triggers_menu(query, state, async_session_local, bot)


async def handle_trigger_delete(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Удалить триггер"""
    trigger_id = int(query.data.split(':')[1])
    
    async with async_session_local() as session:
        result = await session.execute(select(Trigger).filter_by(id=trigger_id))
        trigger = result.scalar_one_or_none()
        
        if trigger:
            await session.delete(trigger)
            await session.commit()
            await query.answer("Триггер удалён")
        else:
            await query.answer("Триггер не найден")
    
    # Обновляем меню триггеров
    await show_triggers_menu(query, state, async_session_local, bot)


async def handle_triggers_pagination(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка пагинации триггеров"""
    # Отвечаем на callback query сразу, чтобы убрать индикатор загрузки
    try:
        await query.answer()
    except Exception:
        pass  # Игнорируем ошибки, если callback уже был отвечен
    
    page = int(query.data.split(':')[1])
    await show_triggers_menu(query, state, async_session_local, bot, page, answer_callback=False)