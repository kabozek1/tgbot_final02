"""
Настройки антимата для админ панели
"""

import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import async_sessionmaker

from .message_utils import edit_message, process_user_input
from utils.plugin_settings import load_plugin_settings, save_plugin_settings, get_plugin_setting, update_plugin_setting
from plugins.blacklist_plugin import sync_antimat_settings

logger = logging.getLogger(__name__)


class AntimatSettingsStates(StatesGroup):
    """Состояния настроек антимата"""
    VIEW = State()
    TOGGLE = State()
    TOGGLE_WARNINGS = State()
    ADD_WORD = State()
    REMOVE_WORD = State()
    ADD_LINK = State()
    REMOVE_LINK = State()


async def safe_answer_callback(query: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await query.answer()
    except Exception as e:
        logger.debug(f"Failed to answer callback query: {e}")


def get_antimat_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Клавиатура настроек антимата"""
    status_emoji = "🟢" if settings.get("enabled", True) else "🔴"
    status_text = "Выключить" if settings.get("enabled", True) else "Включить"
    
    warnings_emoji = "🟢" if settings.get("warnings_enabled", True) else "🔴"
    warnings_text = "Выключить" if settings.get("warnings_enabled", True) else "Включить"
    
    words_count = len(settings.get("blacklist_words", []))
    links_count = len(settings.get("blacklist_links", []))
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{status_emoji} {status_text} фильтр", 
            callback_data="antimat:toggle"
        )],
        [InlineKeyboardButton(
            text=f"{warnings_emoji} {warnings_text} предупреждения", 
            callback_data="antimat:toggle_warnings"
        )],
        [InlineKeyboardButton(
            text=f"📝 Слова ({words_count})", 
            callback_data="antimat:manage_words"
        )],
        [InlineKeyboardButton(
            text=f"🔗 Ссылки ({links_count})", 
            callback_data="antimat:manage_links"
        )],
        [InlineKeyboardButton(
            text="🗑️ Очистить всё", 
            callback_data="antimat:clear_all"
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main_menu")]
    ])


def get_back_to_antimat_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата к настройкам антимата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antimat:view")]
    ])


def get_word_removal_keyboard(words: list) -> InlineKeyboardMarkup:
    """Клавиатура для удаления слов"""
    buttons = []
    for word in words[:10]:  # Показываем максимум 10 слов
        buttons.append([InlineKeyboardButton(
            text=f"🗑️ {word}", 
            callback_data=f"antimat:remove_word:{word}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="antimat:view")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_link_removal_keyboard(links: list) -> InlineKeyboardMarkup:
    """Клавиатура для удаления ссылок"""
    buttons = []
    for link in links[:10]:  # Показываем максимум 10 ссылок
        buttons.append([InlineKeyboardButton(
            text=f"🗑️ {link}", 
            callback_data=f"antimat:remove_link:{link}"
        )])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="antimat:view")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def handle_antimat(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Обработчик кнопки Антимат в главном меню"""
    await safe_answer_callback(query)
    
    # Устанавливаем состояние просмотра
    await state.set_state(AntimatSettingsStates.VIEW)
    
    # Показываем настройки антимата
    await show_antimat_settings(query, state, bot, async_session_local)


async def show_antimat_settings(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Показать настройки антимата"""
    # Загружаем настройки из БД
    settings = await load_plugin_settings("antimat", async_session_local)
    
    status_emoji = "🟢" if settings.get("enabled", True) else "🔴"
    status_text = "Включен" if settings.get("enabled", True) else "Выключен"
    
    warnings_emoji = "🟢" if settings.get("warnings_enabled", True) else "🔴"
    warnings_text = "Включены" if settings.get("warnings_enabled", True) else "Выключены"
    
    words_count = len(settings.get("blacklist_words", []))
    links_count = len(settings.get("blacklist_links", []))
    
    # Показываем первые несколько слов и ссылок
    words_preview = ", ".join(settings.get("blacklist_words", [])[:3])
    if words_count > 3:
        words_preview += f" и еще {words_count - 3}"
    
    links_preview = ", ".join(settings.get("blacklist_links", [])[:3])
    if links_count > 3:
        links_preview += f" и еще {links_count - 3}"
    
    text = f"""🤬 <b>Настройки антимата</b>

{status_emoji} <b>Статус:</b> {status_text}
{warnings_emoji} <b>Автопредупреждения:</b> {warnings_text}

📝 <b>Запрещённые слова:</b> {words_count}
{words_preview if words_preview else "Нет"}

🔗 <b>Запрещённые ссылки:</b> {links_count}
{links_preview if links_preview else "Нет"}

<i>Антимат автоматически удаляет сообщения с запрещёнными словами и ссылками.</i>"""
    
    keyboard = get_antimat_settings_keyboard(settings)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_antimat_toggle(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Переключение статуса антимата"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    
    # Переключаем статус
    new_enabled = not settings.get("enabled", True)
    updated_settings = update_plugin_setting(settings, "enabled", new_enabled)
    
    # Сохраняем в БД
    await save_plugin_settings("antimat", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные
    await sync_antimat_settings(async_session_local)
    
    # Обновляем экран
    await show_antimat_settings(query, state, bot, async_session_local)
    
    logger.info(f"Antimat {'enabled' if new_enabled else 'disabled'} by admin {query.from_user.id}")


async def handle_antimat_toggle_warnings(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Переключение автопредупреждений"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    
    # Переключаем предупреждения
    new_warnings = not settings.get("warnings_enabled", True)
    updated_settings = update_plugin_setting(settings, "warnings_enabled", new_warnings)
    
    # Сохраняем в БД
    await save_plugin_settings("antimat", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные
    await sync_antimat_settings(async_session_local)
    
    # Обновляем экран
    await show_antimat_settings(query, state, bot, async_session_local)
    
    logger.info(f"Antimat warnings {'enabled' if new_warnings else 'disabled'} by admin {query.from_user.id}")


async def handle_antimat_add_word(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Начать добавление слова"""
    await safe_answer_callback(query)
    
    # Устанавливаем состояние ожидания ввода слова
    await state.set_state(AntimatSettingsStates.ADD_WORD)
    
    text = """📝 <b>Добавление запрещённого слова</b>

Введите слово или фразу для добавления в чёрный список:"""
    
    keyboard = get_back_to_antimat_keyboard()
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_add_word_input(message: Message, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Обработка ввода нового слова"""
    try:
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        
        # Получаем message_id последнего сообщения бота из FSM
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        
        word = message.text.strip().lower()
        
        if not word:
            error_text = "❌ <b>Ошибка: Пустая строка</b>\n\nВведите слово или фразу:"
            error_keyboard = get_back_to_antimat_keyboard()
            
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('Message', (), {
                            'message_id': last_message_id,
                            'chat': type('Chat', (), {'id': message.chat.id})()
                        })()
                    })()
                    await edit_message(fake_query, error_text, error_keyboard, "HTML", bot)
                    return
                except Exception:
                    pass
            
            await process_user_input(bot=bot, message=message, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", state=state)
            return
        
        # Загружаем текущие настройки
        settings = await load_plugin_settings("antimat", async_session_local)
        words = settings.get("blacklist_words", [])
        
        if word in words:
            error_text = f"❌ <b>Слово уже в списке</b>\n\nСлово '{word}' уже есть в чёрном списке.\n\nВведите другое слово:"
            error_keyboard = get_back_to_antimat_keyboard()
            
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('Message', (), {
                            'message_id': last_message_id,
                            'chat': type('Chat', (), {'id': message.chat.id})()
                        })()
                    })()
                    await edit_message(fake_query, error_text, error_keyboard, "HTML", bot)
                    return
                except Exception:
                    pass
            
            await process_user_input(bot=bot, message=message, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", state=state)
            return
        
        # Добавляем слово
        words.append(word)
        updated_settings = update_plugin_setting(settings, "blacklist_words", words)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        # Возвращаемся к настройкам
        await state.set_state(AntimatSettingsStates.VIEW)
        
        # Загружаем обновленные настройки для отображения
        settings = await load_plugin_settings("antimat", async_session_local)
        words = settings.get("blacklist_words", [])
        
        # Формируем текст для вкладки слов
        if not words:
            text = """📝 <b>Управление словами</b>

Список запрещённых слов пуст.

Выберите слово для удаления или добавьте новое."""
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить слово", callback_data="antimat:add_word")],
                [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antimat:view")]
            ])
        else:
            # Показываем максимум 10 слов
            display_words = words[:10]
            words_text = "\n".join([f"• {word}" for word in display_words])
            
            if len(words) > 10:
                words_text += f"\n... и еще {len(words) - 10}"
            
            text = f"""📝 <b>Управление словами</b>

Всего слов: <b>{len(words)}</b>

{words_text}

Выберите слово для удаления или добавьте новое."""
            
            # Создаем кнопки для каждого слова
            buttons = []
            for word in display_words:
                # Экранируем спецсимволы в callback_data
                safe_word = word.replace(":", "%3A")
                buttons.append([InlineKeyboardButton(
                    text=f"{word} ❌", 
                    callback_data=f"antimat:remove_word_inline:{safe_word}"
                )])
            
            # Добавляем кнопки управления
            buttons.append([InlineKeyboardButton(
                text="➕ Добавить слово", 
                callback_data="antimat:add_word"
            )])
            buttons.append([InlineKeyboardButton(
                text="🗑️ Удалить все слова", 
                callback_data="antimat:clear_words"
            )])
            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад к настройкам", 
                callback_data="antimat:view"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Используем process_user_input для правильного редактирования
        await process_user_input(bot, message, text, keyboard, "HTML", state)
        
        logger.info(f"Added word '{word}' to antimat blacklist by admin {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in handle_add_word_input: {e}")
        try:
            await process_user_input(bot=bot, message=message, text="❌ Произошла ошибка. Попробуйте еще раз.", parse_mode="HTML", state=state)
        except Exception:
            pass


async def handle_antimat_remove_word(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Показать список слов для удаления"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    words = settings.get("blacklist_words", [])
    
    if not words:
        text = """📝 <b>Удаление запрещённых слов</b>

Список запрещённых слов пуст."""
        keyboard = get_back_to_antimat_keyboard()
    else:
        text = f"""📝 <b>Удаление запрещённых слов</b>

Выберите слово для удаления:"""
        keyboard = get_word_removal_keyboard(words)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_remove_word_callback(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Удаление конкретного слова"""
    await safe_answer_callback(query)
    
    # Извлекаем слово из callback_data
    word = query.data.split(":", 2)[2]
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    words = settings.get("blacklist_words", [])
    
    if word in words:
        words.remove(word)
        updated_settings = update_plugin_setting(settings, "blacklist_words", words)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        logger.info(f"Removed word '{word}' from antimat blacklist by admin {query.from_user.id}")
    
    # Обновляем экран
    await show_antimat_settings(query, state, bot, async_session_local)


async def handle_antimat_add_link(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Начать добавление ссылки"""
    await safe_answer_callback(query)
    
    # Устанавливаем состояние ожидания ввода ссылки
    await state.set_state(AntimatSettingsStates.ADD_LINK)
    
    text = """🔗 <b>Добавление запрещённой ссылки</b>

Введите ссылку или домен для добавления в чёрный список:"""
    
    keyboard = get_back_to_antimat_keyboard()
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_add_link_input(message: Message, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Обработка ввода новой ссылки"""
    try:
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        
        # Получаем message_id последнего сообщения бота из FSM
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        
        link = message.text.strip().lower()
        
        if not link:
            error_text = "❌ <b>Ошибка: Пустая строка</b>\n\nВведите ссылку или домен:"
            error_keyboard = get_back_to_antimat_keyboard()
            
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('Message', (), {
                            'message_id': last_message_id,
                            'chat': type('Chat', (), {'id': message.chat.id})()
                        })()
                    })()
                    await edit_message(fake_query, error_text, error_keyboard, "HTML", bot)
                    return
                except Exception:
                    pass
            
            await process_user_input(bot=bot, message=message, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", state=state)
            return
        
        # Загружаем текущие настройки
        settings = await load_plugin_settings("antimat", async_session_local)
        links = settings.get("blacklist_links", [])
        
        if link in links:
            error_text = f"❌ <b>Ссылка уже в списке</b>\n\nСсылка '{link}' уже есть в чёрном списке.\n\nВведите другую ссылку:"
            error_keyboard = get_back_to_antimat_keyboard()
            
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('Message', (), {
                            'message_id': last_message_id,
                            'chat': type('Chat', (), {'id': message.chat.id})()
                        })()
                    })()
                    await edit_message(fake_query, error_text, error_keyboard, "HTML", bot)
                    return
                except Exception:
                    pass
            
            await process_user_input(bot=bot, message=message, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", state=state)
            return
        
        # Добавляем ссылку
        links.append(link)
        updated_settings = update_plugin_setting(settings, "blacklist_links", links)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        # Возвращаемся к настройкам
        await state.set_state(AntimatSettingsStates.VIEW)
        
        # Загружаем обновленные настройки для отображения
        settings = await load_plugin_settings("antimat", async_session_local)
        links = settings.get("blacklist_links", [])
        
        # Формируем текст для вкладки ссылок
        if not links:
            text = """🔗 <b>Управление ссылками</b>

Список запрещённых ссылок пуст.

Выберите ссылку для удаления или добавьте новую."""
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить ссылку", callback_data="antimat:add_link")],
                [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antimat:view")]
            ])
        else:
            # Показываем максимум 10 ссылок
            display_links = links[:10]
            links_text = "\n".join([f"• {link}" for link in display_links])
            
            if len(links) > 10:
                links_text += f"\n... и еще {len(links) - 10}"
            
            text = f"""🔗 <b>Управление ссылками</b>

Всего ссылок: <b>{len(links)}</b>

{links_text}

Выберите ссылку для удаления или добавьте новую."""
            
            # Создаем кнопки для каждой ссылки
            buttons = []
            for link in display_links:
                # Экранируем спецсимволы в callback_data
                safe_link = link.replace(":", "%3A")
                buttons.append([InlineKeyboardButton(
                    text=f"{link} ❌", 
                    callback_data=f"antimat:remove_link_inline:{safe_link}"
                )])
            
            # Добавляем кнопки управления
            buttons.append([InlineKeyboardButton(
                text="➕ Добавить ссылку", 
                callback_data="antimat:add_link"
            )])
            buttons.append([InlineKeyboardButton(
                text="🗑️ Удалить все ссылки", 
                callback_data="antimat:clear_links"
            )])
            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад к настройкам", 
                callback_data="antimat:view"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Используем process_user_input для правильного редактирования
        await process_user_input(bot, message, text, keyboard, "HTML", state)
        
        logger.info(f"Added link '{link}' to antimat blacklist by admin {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in handle_add_link_input: {e}")
        try:
            await process_user_input(bot=bot, message=message, text="❌ Произошла ошибка. Попробуйте еще раз.", parse_mode="HTML", state=state)
        except Exception:
            pass


async def handle_antimat_remove_link(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Показать список ссылок для удаления"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    links = settings.get("blacklist_links", [])
    
    if not links:
        text = """🔗 <b>Удаление запрещённых ссылок</b>

Список запрещённых ссылок пуст."""
        keyboard = get_back_to_antimat_keyboard()
    else:
        text = f"""🔗 <b>Удаление запрещённых ссылок</b>

Выберите ссылку для удаления:"""
        keyboard = get_link_removal_keyboard(links)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_remove_link_callback(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Удаление конкретной ссылки"""
    await safe_answer_callback(query)
    
    # Извлекаем ссылку из callback_data
    link = query.data.split(":", 2)[2]
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    links = settings.get("blacklist_links", [])
    
    if link in links:
        links.remove(link)
        updated_settings = update_plugin_setting(settings, "blacklist_links", links)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        logger.info(f"Removed link '{link}' from antimat blacklist by admin {query.from_user.id}")
    
    # Обновляем экран
    await show_antimat_settings(query, state, bot, async_session_local)


async def handle_antimat_clear_all(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Очистка всех списков антимата"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    
    # Очищаем списки
    updated_settings = update_plugin_setting(settings, "blacklist_words", [])
    updated_settings = update_plugin_setting(updated_settings, "blacklist_links", [])
    
    # Сохраняем в БД
    await save_plugin_settings("antimat", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные
    await sync_antimat_settings(async_session_local)
    try:
        from plugins.blacklist_plugin import blacklist_words, blacklist_links
        blacklist_words.clear()
        blacklist_links.clear()
        logger.info("✅ Cleared global blacklist variables in blacklist_plugin.py")
    except ImportError:
        logger.warning("⚠️ Could not import blacklist_plugin to clear global variables")
    
    # Обновляем интерфейс
    await show_antimat_settings(query, state, bot, async_session_local)
    
    # Отвечаем на callback
    await query.answer("✅ Списки очищены")
    
    logger.info(f"Antimat lists cleared by admin {query.from_user.id}")


async def show_antimat_words(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker, page: int = 0):
    """Показать список слов для управления"""
    # Загружаем настройки из БД
    settings = await load_plugin_settings("antimat", async_session_local)
    words = settings.get("blacklist_words", [])
    
    if not words:
        text = """📝 <b>Управление словами</b>

Список запрещённых слов пуст.

Выберите слово для удаления или добавьте новое."""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить слово", callback_data="antimat:add_word")],
            [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antimat:view")]
        ])
    else:
        # Пагинация: 5 слов на страницу
        words_per_page = 5
        total_pages = (len(words) + words_per_page - 1) // words_per_page
        current_page = max(0, min(page, total_pages - 1))
        
        start_idx = current_page * words_per_page
        end_idx = start_idx + words_per_page
        display_words = words[start_idx:end_idx]
        
        words_text = "\n".join([f"• {word}" for word in display_words])
        
        text = f"""📝 <b>Управление словами</b>

Всего слов: <b>{len(words)}</b>

{words_text}

Выберите слово для удаления или добавьте новое."""
        
        # Создаем кнопки для каждого слова
        buttons = []
        for word in display_words:
            # Экранируем спецсимволы в callback_data
            safe_word = word.replace(":", "%3A")
            buttons.append([InlineKeyboardButton(
                text=f"{word} ❌", 
                callback_data=f"antimat:remove_word_inline:{safe_word}"
            )])
        
        # Добавляем кнопки пагинации
        if total_pages > 1:
            pagination_buttons = []
            if current_page > 0:
                pagination_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data=f"antimat:words_page:{current_page-1}"
                ))
            pagination_buttons.append(InlineKeyboardButton(
                text=f"📋 Страница {current_page+1} из {total_pages}", 
                callback_data="noop"
            ))
            if current_page < total_pages - 1:
                pagination_buttons.append(InlineKeyboardButton(
                    text="▶️ Вперёд", 
                    callback_data=f"antimat:words_page:{current_page+1}"
                ))
            buttons.append(pagination_buttons)
        
        # Добавляем кнопки управления
        buttons.append([InlineKeyboardButton(
            text="➕ Добавить слово", 
            callback_data="antimat:add_word"
        )])
        buttons.append([InlineKeyboardButton(
            text="🗑️ Удалить все слова", 
            callback_data="antimat:clear_words"
        )])
        buttons.append([InlineKeyboardButton(
            text="⬅️ Назад к настройкам", 
            callback_data="antimat:view"
        )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def show_antimat_links(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker, page: int = 0):
    """Показать список ссылок для управления"""
    # Загружаем настройки из БД
    settings = await load_plugin_settings("antimat", async_session_local)
    links = settings.get("blacklist_links", [])
    
    if not links:
        text = """🔗 <b>Управление ссылками</b>

Список запрещённых ссылок пуст.

Выберите ссылку для удаления или добавьте новую."""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ссылку", callback_data="antimat:add_link")],
            [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antimat:view")]
        ])
    else:
        # Пагинация: 5 ссылок на страницу
        links_per_page = 5
        total_pages = (len(links) + links_per_page - 1) // links_per_page
        current_page = max(0, min(page, total_pages - 1))
        
        start_idx = current_page * links_per_page
        end_idx = start_idx + links_per_page
        display_links = links[start_idx:end_idx]
        
        links_text = "\n".join([f"• {link}" for link in display_links])
        
        text = f"""🔗 <b>Управление ссылками</b>

Всего ссылок: <b>{len(links)}</b>

{links_text}

Выберите ссылку для удаления или добавьте новую."""
        
        # Создаем кнопки для каждой ссылки
        buttons = []
        for link in display_links:
            # Экранируем спецсимволы в callback_data
            safe_link = link.replace(":", "%3A")
            buttons.append([InlineKeyboardButton(
                text=f"{link} ❌", 
                callback_data=f"antimat:remove_link_inline:{safe_link}"
            )])
        
        # Добавляем кнопки пагинации
        if total_pages > 1:
            pagination_buttons = []
            if current_page > 0:
                pagination_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data=f"antimat:links_page:{current_page-1}"
                ))
            pagination_buttons.append(InlineKeyboardButton(
                text=f"📋 Страница {current_page+1} из {total_pages}", 
                callback_data="noop"
            ))
            if current_page < total_pages - 1:
                pagination_buttons.append(InlineKeyboardButton(
                    text="▶️ Вперёд", 
                    callback_data=f"antimat:links_page:{current_page+1}"
                ))
            buttons.append(pagination_buttons)
        
        # Добавляем кнопки управления
        buttons.append([InlineKeyboardButton(
            text="➕ Добавить ссылку", 
            callback_data="antimat:add_link"
        )])
        buttons.append([InlineKeyboardButton(
            text="🗑️ Удалить все ссылки", 
            callback_data="antimat:clear_links"
        )])
        buttons.append([InlineKeyboardButton(
            text="⬅️ Назад к настройкам", 
            callback_data="antimat:view"
        )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_manage_words(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Переход к управлению словами"""
    await safe_answer_callback(query)
    await state.set_state(AntimatSettingsStates.VIEW)
    await show_antimat_words(query, state, bot, async_session_local, page=0)


async def handle_manage_links(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Переход к управлению ссылками"""
    await safe_answer_callback(query)
    await state.set_state(AntimatSettingsStates.VIEW)
    await show_antimat_links(query, state, bot, async_session_local, page=0)


async def handle_remove_word_inline(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Удаление слова через inline кнопку"""
    # Извлекаем слово из callback_data (декодируем спецсимволы)
    word = query.data.split(":", 2)[2].replace("%3A", ":")
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    words = settings.get("blacklist_words", [])
    
    if word in words:
        words.remove(word)
        updated_settings = update_plugin_setting(settings, "blacklist_words", words)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        logger.info(f"Removed word '{word}' from antimat blacklist by admin {query.from_user.id}")
        
        # Обновляем интерфейс (возвращаемся на первую страницу)
        await show_antimat_words(query, state, bot, async_session_local, page=0)
        await query.answer("✅ Слово удалено")
    else:
        await query.answer("❌ Слово не найдено")


async def handle_remove_link_inline(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Удаление ссылки через inline кнопку"""
    # Извлекаем ссылку из callback_data (декодируем спецсимволы)
    link = query.data.split(":", 2)[2].replace("%3A", ":")
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    links = settings.get("blacklist_links", [])
    
    if link in links:
        links.remove(link)
        updated_settings = update_plugin_setting(settings, "blacklist_links", links)
        
        # Сохраняем в БД
        await save_plugin_settings("antimat", updated_settings, async_session_local)
        
        # Синхронизируем глобальные переменные
        await sync_antimat_settings(async_session_local)
        
        logger.info(f"Removed link '{link}' from antimat blacklist by admin {query.from_user.id}")
        
        # Обновляем интерфейс (возвращаемся на первую страницу)
        await show_antimat_links(query, state, bot, async_session_local, page=0)
        await query.answer("✅ Ссылка удалена")
    else:
        await query.answer("❌ Ссылка не найдена")


async def handle_clear_words(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Очистка всех слов"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    
    # Очищаем список слов
    updated_settings = update_plugin_setting(settings, "blacklist_words", [])
    
    # Сохраняем в БД
    await save_plugin_settings("antimat", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные
    await sync_antimat_settings(async_session_local)
    
    # Обновляем интерфейс
    await show_antimat_words(query, state, bot, async_session_local, page=0)
    await query.answer("✅ Все слова удалены")
    
    logger.info(f"All antimat words cleared by admin {query.from_user.id}")


async def handle_clear_links(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Очистка всех ссылок"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antimat", async_session_local)
    
    # Очищаем список ссылок
    updated_settings = update_plugin_setting(settings, "blacklist_links", [])
    
    # Сохраняем в БД
    await save_plugin_settings("antimat", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные
    await sync_antimat_settings(async_session_local)
    
    # Обновляем интерфейс
    await show_antimat_links(query, state, bot, async_session_local, page=0)
    await query.answer("✅ Все ссылки удалены")
    
    logger.info(f"All antimat links cleared by admin {query.from_user.id}")


async def handle_words_pagination(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Обработка пагинации слов"""
    await safe_answer_callback(query)
    
    # Извлекаем номер страницы из callback_data
    page = int(query.data.split(":")[2])
    
    # Показываем нужную страницу
    await show_antimat_words(query, state, bot, async_session_local, page=page)


async def handle_links_pagination(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local: async_sessionmaker):
    """Обработка пагинации ссылок"""
    await safe_answer_callback(query)
    
    # Извлекаем номер страницы из callback_data
    page = int(query.data.split(":")[2])
    
    # Показываем нужную страницу
    await show_antimat_links(query, state, bot, async_session_local, page=page)
