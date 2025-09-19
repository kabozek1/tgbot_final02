"""
Управление администраторами
"""

import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import func

from models.base import Admin, User
from .message_utils import edit_message, process_user_input
from .settings_keyboards import (
    get_admin_management_keyboard,
    get_admin_list_keyboard,
    get_admin_actions_keyboard,
    get_admin_add_keyboard
)

logger = logging.getLogger(__name__)


async def safe_answer_callback(query: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await query.answer()
    except Exception as e:
        logger.debug(f"Failed to answer callback query: {e}")


async def get_admins_list(async_session_local: async_sessionmaker):
    """Вспомогательная функция для получения списка администраторов"""
    from config import get_settings
    settings = get_settings()
    
    async with async_session_local() as session:
        # Получаем список администраторов из БД с информацией о пользователях
        result = await session.execute(
            select(Admin, User).join(User, Admin.telegram_id == User.telegram_id, isouter=True)
        )
        
        admins = []
        
        # Добавляем администраторов из БД
        for admin, user in result:
            admins.append({
                'telegram_id': admin.telegram_id,
                'role': admin.role,
                'username': user.username if user else None,
                'first_name': user.first_name if user else None,
                'source': 'db'  # Источник: база данных
            })
        
        # Добавляем администраторов из конфига
        for config_admin_id in settings.ADMINS:
            # Проверяем, не добавлен ли уже этот админ из БД
            if not any(admin['telegram_id'] == config_admin_id for admin in admins):
                # Получаем информацию о пользователе из БД
                user_result = await session.execute(
                    select(User).filter_by(telegram_id=config_admin_id)
                )
                user = user_result.scalar_one_or_none()
                
                admins.append({
                    'telegram_id': config_admin_id,
                    'role': 'super_admin',
                    'username': user.username if user else None,
                    'first_name': user.first_name if user else None,
                    'source': 'config'  # Источник: конфиг
                })
    
    # Сортируем администраторов для стабильного порядка
    # Сначала по источнику (config первые), затем по telegram_id
    admins.sort(key=lambda x: (x['source'] != 'config', x['telegram_id']))
    
    return admins


class AdminManagementStates(StatesGroup):
    """Состояния для управления администраторами"""
    WAITING_ADMIN_ID = State()


async def handle_settings_menu(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать меню настроек"""
    await safe_answer_callback(query)
    
    from .settings_keyboards import get_settings_menu_keyboard
    
    text = "⚙️ <b>Настройки</b>\n\nВыберите раздел для настройки:"
    keyboard = get_settings_menu_keyboard()
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_admin_management(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать меню управления администраторами"""
    await safe_answer_callback(query)
    
    text = "👥 <b>Управление администраторами</b>\n\nВыберите действие:"
    keyboard = get_admin_management_keyboard()
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_admin_add(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Начать добавление администратора"""
    await safe_answer_callback(query)
    
    text = ("➕ <b>Добавление администратора</b>\n\n"
            "Отправьте ID пользователя или его username (например: @username или 123456789)\n\n"
            "Примеры:\n"
            "• 123456789 (ID пользователя)\n"
            "• @username (username пользователя)")
    
    keyboard = get_admin_add_keyboard()
    
    message_id = await edit_message(query, text, keyboard, "HTML", bot)
    if message_id:
        await state.update_data(last_message_id=message_id)
    await state.set_state(AdminManagementStates.WAITING_ADMIN_ID)


async def handle_admin_id_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода ID/username администратора"""
    admin_input = message.text.strip()
    
    try:
        # Пытаемся получить информацию о пользователе
        user_info = None
        telegram_id = None
        
        if admin_input.startswith('@'):
            # Это username - ОБЯЗАТЕЛЬНО проверяем в БД
            username = admin_input[1:]  # Убираем @
            
            # Ищем пользователя в БД по username
            async with async_session_local() as session:
                user_result = await session.execute(
                    select(User).filter_by(username=username)
                )
                user = user_result.scalar_one_or_none()
                
                if not user:
                    await process_user_input(
                        bot=bot,
                        message=message,
                        text=f"❌ <b>Ошибка</b>\n\n"
                             f"Пользователь с username @{username} не найден в базе данных.\n"
                             f"Убедитесь, что пользователь уже проходил капчу в чате.",
                        reply_markup=get_admin_management_keyboard(),
                        state=state
                    )
                    return
                
                telegram_id = user.telegram_id
        else:
            # Это ID - НЕ требуем наличия в БД
            try:
                telegram_id = int(admin_input)
            except ValueError:
                await process_user_input(
                    bot=bot,
                    message=message,
                    text="❌ <b>Ошибка</b>\n\n"
                         "Неверный формат ID. Введите числовой ID пользователя.",
                    reply_markup=get_admin_management_keyboard(),
                    state=state
                )
                return
        
        # Проверяем, не является ли пользователь уже администратором
        async with async_session_local() as session:
            result = await session.execute(
                select(Admin).filter_by(telegram_id=telegram_id)
            )
            existing_admin = result.scalar_one_or_none()
            
            if existing_admin:
                await process_user_input(
                    bot=bot,
                    message=message,
                    text=f"❌ <b>Ошибка</b>\n\n"
                         f"Пользователь с ID {telegram_id} уже является администратором с ролью '{existing_admin.role}'.",
                    reply_markup=get_admin_management_keyboard(),
                    state=state
                )
                return
            
            # Пытаемся получить информацию о пользователе из БД (но не требуем её наличия для ID)
            user = None
            if not admin_input.startswith('@'):
                user_result = await session.execute(
                    select(User).filter_by(telegram_id=telegram_id)
                )
                user = user_result.scalar_one_or_none()
                # Для ID не требуем наличия пользователя в БД
        
        # Сразу добавляем администратора с ролью 'admin'
        try:
            async with async_session_local() as session:
                new_admin = Admin(
                    telegram_id=telegram_id,
                    role='admin'
                )
                session.add(new_admin)
                await session.commit()
            
            # Формируем сообщение об успехе
            if user and user.username:
                username_display = f"@{user.username}"
            elif user and user.first_name:
                username_display = user.first_name
            else:
                username_display = "Не указан (будет обновлен автоматически)"
            
            success_text = (f"✅ <b>Администратор успешно добавлен!</b>\n\n"
                           f"👤 ID: {telegram_id}\n"
                           f"👤 Username: {username_display}\n"
                           f"🎭 Роль: Администратор\n\n"
                           f"<i>Информация о пользователе будет автоматически обновлена при его активности в боте.</i>")
            
            await process_user_input(
                bot=bot,
                message=message,
                text=success_text,
                reply_markup=get_admin_management_keyboard(),
                state=state
            )
            
            logger.info(f"Admin {telegram_id} added with role admin by {message.from_user.id}")
            
        except Exception as add_error:
            logger.error(f"Error adding admin: {add_error}")
            await process_user_input(
                bot=bot,
                message=message,
                text="❌ <b>Ошибка</b>\n\nНе удалось добавить администратора.",
                reply_markup=get_admin_management_keyboard(),
                state=state
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error processing admin ID input: {e}")
        await process_user_input(
            bot=bot,
            message=message,
            text="❌ <b>Ошибка</b>\n\nПроизошла ошибка при обработке запроса.",
            reply_markup=get_admin_management_keyboard(),
            state=state
        )






async def handle_admin_list(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать список администраторов"""
    await safe_answer_callback(query)
    
    try:
        # Получаем список администраторов
        admins = await get_admins_list(async_session_local)
        
        if not admins:
            text = "👥 <b>Список администраторов</b>\n\nАдминистраторы не найдены."
            keyboard = get_admin_management_keyboard()
        else:
            text = f"👥 <b>Список администраторов</b>\n\nНайдено: {len(admins)} администраторов"
            keyboard = get_admin_list_keyboard(admins, page=0)
        
        await edit_message(query, text, keyboard, "HTML", bot)
        
    except Exception as e:
        logger.error(f"Error getting admin list: {e}")
        error_text = "❌ <b>Ошибка</b>\n\nНе удалось загрузить список администраторов."
        await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)


async def handle_admin_list_pagination(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка пагинации списка администраторов"""
    await safe_answer_callback(query)
    
    # Парсим номер страницы
    page = int(query.data.split(":")[1])
    
    try:
        # Получаем список администраторов
        admins = await get_admins_list(async_session_local)
        
        text = f"👥 <b>Список администраторов</b>\n\nНайдено: {len(admins)} администраторов"
        keyboard = get_admin_list_keyboard(admins, page=page)
        
        await edit_message(query, text, keyboard, "HTML", bot)
        
    except Exception as e:
        logger.error(f"Error paginating admin list: {e}")
        error_text = "❌ <b>Ошибка</b>\n\nНе удалось загрузить список администраторов."
        await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)


async def handle_admin_view(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать информацию об администраторе"""
    await safe_answer_callback(query)
    
    # Парсим ID администратора
    admin_id = int(query.data.split(":")[1])
    
    try:
        from config import get_settings
        settings = get_settings()
        
        async with async_session_local() as session:
            # Проверяем, является ли это администратор из конфига
            is_config_admin = admin_id in settings.ADMINS
            
            if is_config_admin:
                # Администратор из конфига
                user_result = await session.execute(
                    select(User).filter_by(telegram_id=admin_id)
                )
                user = user_result.scalar_one_or_none()
                
                admin_text = (f"👑 <b>Информация об администраторе</b>\n\n"
                             f"🆔 ID: {admin_id}\n"
                             f"👤 Username: @{user.username if user and user.username else 'Не указан'}\n"
                             f"📝 Имя: {user.first_name if user and user.first_name else 'Не указано'}\n"
                             f"🎭 Роль: Супер-админ (из конфига)\n"
                             f"🔒 Статус: Нельзя удалить")
                
                # Для суперадминов из конфига не показываем кнопку удаления
                keyboard = get_admin_actions_keyboard(admin_id, query.from_user.id, can_delete=False)
                
            else:
                # Администратор из БД
                result = await session.execute(
                    select(Admin, User).join(User, Admin.telegram_id == User.telegram_id, isouter=True)
                    .filter(Admin.telegram_id == admin_id)
                )
                
                admin_data = result.first()
                if not admin_data:
                    error_text = "❌ <b>Ошибка</b>\n\nАдминистратор не найден."
                    await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)
                    return
                
                admin, user = admin_data
                
                # Формируем информацию об администраторе
                role_names = {
                    'super_admin': 'Супер-админ',
                    'admin': 'Администратор',
                    'moderator': 'Модератор'
                }
                
                role_emojis = {
                    'super_admin': '👑',
                    'admin': '👤',
                    'moderator': '🛡️'
                }
                
                # Определяем статус информации о пользователе
                if user:
                    username_display = f"@{user.username}" if user.username else "Не указан"
                    name_display = user.first_name if user.first_name else "Не указано"
                    info_status = "✅ Информация актуальна"
                else:
                    username_display = "Не указан (будет обновлен автоматически)"
                    name_display = "Не указано (будет обновлено автоматически)"
                    info_status = "⏳ Ожидает активности пользователя"
                
                admin_text = (f"{role_emojis.get(admin.role, '👤')} <b>Информация об администраторе</b>\n\n"
                             f"🆔 ID: {admin.telegram_id}\n"
                             f"👤 Username: {username_display}\n"
                             f"📝 Имя: {name_display}\n"
                             f"🎭 Роль: {role_names.get(admin.role, admin.role)}\n"
                             f"📊 Источник: База данных\n"
                             f"ℹ️ Статус: {info_status}")
                
                keyboard = get_admin_actions_keyboard(admin_id, query.from_user.id, can_delete=True)
            
            await edit_message(query, admin_text, keyboard, "HTML", bot)
            
    except Exception as e:
        logger.error(f"Error viewing admin: {e}")
        error_text = "❌ <b>Ошибка</b>\n\nНе удалось загрузить информацию об администраторе."
        await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)


async def handle_admin_delete(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Удалить администратора"""
    await safe_answer_callback(query)
    
    # Парсим ID администратора
    admin_id = int(query.data.split(":")[1])
    
    try:
        from config import get_settings
        settings = get_settings()
        
        # Проверяем, не является ли это суперадмин из конфига
        if admin_id in settings.ADMINS:
            error_text = "❌ <b>Ошибка</b>\n\nНельзя удалить суперадминистратора из конфига."
            await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)
            return
        
        async with async_session_local() as session:
            # Получаем информацию об администраторе
            result = await session.execute(
                select(Admin).filter_by(telegram_id=admin_id)
            )
            admin = result.scalar_one_or_none()
            
            if not admin:
                error_text = "❌ <b>Ошибка</b>\n\nАдминистратор не найден."
                await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)
                return
            
            # Удаляем администратора
            await session.delete(admin)
            await session.commit()
            
            success_text = (f"✅ <b>Администратор удален!</b>\n\n"
                           f"ID: {admin_id}\n"
                           f"Роль: {admin.role}")
            
            await edit_message(query, success_text, get_admin_management_keyboard(), "HTML", bot)
            
            logger.info(f"Admin {admin_id} deleted by {query.from_user.id}")
            
    except Exception as e:
        logger.error(f"Error deleting admin: {e}")
        error_text = "❌ <b>Ошибка</b>\n\nНе удалось удалить администратора."
        await edit_message(query, error_text, get_admin_management_keyboard(), "HTML", bot)
