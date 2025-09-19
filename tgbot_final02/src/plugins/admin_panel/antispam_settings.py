"""
Настройки антиспама для админ панели
"""

import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import async_sessionmaker

from .message_utils import edit_message, process_user_input
from utils.plugin_settings import load_plugin_settings, save_plugin_settings, get_plugin_setting, update_plugin_setting
from plugins.antiflood_plugin import sync_antispam_settings

logger = logging.getLogger(__name__)


class AntispamSettingsStates(StatesGroup):
    """Состояния настроек антиспама"""
    VIEW = State()
    WAITING_LIMIT = State()
    WAITING_WINDOW = State()


async def safe_answer_callback(query: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await query.answer()
    except Exception as e:
        logger.debug(f"Failed to answer callback query: {e}")


def get_antispam_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Клавиатура настроек антиспама"""
    status_emoji = "🟢" if settings.get("enabled", True) else "🔴"
    status_text = "Выключить" if settings.get("enabled", True) else "Включить"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{status_emoji} {status_text}", 
            callback_data="antispam:toggle"
        )],
        [InlineKeyboardButton(
            text=f"✏️ Изменить лимит ({settings.get('max_messages', 5)})", 
            callback_data="antispam:edit_limit"
        )],
        [InlineKeyboardButton(
            text=f"✏️ Изменить период ({settings.get('window_seconds', 10)}с)", 
            callback_data="antispam:edit_window"
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main_menu")]
    ])


def get_back_to_antispam_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата к настройкам антиспама"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к настройкам", callback_data="antispam:view")]
    ])


async def handle_antispam(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local):
    """Обработчик кнопки Антиспам в главном меню"""
    await safe_answer_callback(query)
    
    # Устанавливаем состояние просмотра
    await state.set_state(AntispamSettingsStates.VIEW)
    
    # Показываем настройки антиспама
    await show_antispam_settings(query, state, bot, async_session_local)


async def show_antispam_settings(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local):
    """Показать настройки антиспама"""
    # Отладочная информация
    logger.info(f"🔍 DEBUG: show_antispam_settings called with async_session_local type={type(async_session_local)}")
    logger.info(f"🔍 DEBUG: bot type={type(bot)}")
    
    # Загружаем настройки из БД
    settings = await load_plugin_settings("antispam", async_session_local)
    
    status_emoji = "🟢" if settings.get("enabled", True) else "🔴"
    status_text = "Включен" if settings.get("enabled", True) else "Выключен"
    
    text = f"""🔄 <b>Настройки антиспама</b>

{status_emoji} <b>Статус:</b> {status_text}
📊 <b>Лимит:</b> {settings.get('max_messages', 5)} сообщений
⏱️ <b>Период:</b> {settings.get('window_seconds', 10)} секунд

<i>Антиспам автоматически удаляет сообщения пользователей, которые превышают лимит сообщений за указанный период времени.</i>"""
    
    keyboard = get_antispam_settings_keyboard(settings)
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_antispam_toggle(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local):
    """Переключение статуса антиспама"""
    logger.info(f"🔍 DEBUG: handle_antispam_toggle called with async_session_local type={type(async_session_local)}")
    
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antispam", async_session_local)
    
    # Переключаем статус
    new_enabled = not settings.get("enabled", True)
    updated_settings = update_plugin_setting(settings, "enabled", new_enabled)
    
    # Сохраняем в БД
    await save_plugin_settings("antispam", updated_settings, async_session_local)
    
    # Синхронизируем глобальные переменные в плагине
    await sync_antispam_settings(async_session_local)
    
    # Обновляем экран
    await show_antispam_settings(query, state, bot, async_session_local)
    
    logger.info(f"Antispam {'enabled' if new_enabled else 'disabled'} by admin {query.from_user.id}")


async def handle_antispam_edit_limit(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local):
    """Начать редактирование лимита сообщений"""
    await safe_answer_callback(query)
    
    # Загружаем текущие настройки
    settings = await load_plugin_settings("antispam", async_session_local)
    
    # Устанавливаем состояние ожидания ввода лимита
    await state.set_state(AntispamSettingsStates.WAITING_LIMIT)
    
    text = f"""📝 <b>Изменение лимита сообщений</b>

Текущий лимит: <b>{settings.get('max_messages', 5)}</b> сообщений

Введите новый лимит (от 1 до 20):"""
    
    keyboard = get_back_to_antispam_keyboard()
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_limit_input(message: Message, state: FSMContext, bot: Bot, async_session_local):
    """Обработка ввода нового лимита"""
    try:
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass  # Игнорируем ошибки удаления
        
        # Получаем message_id последнего сообщения бота из FSM
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        
        try:
            # Пытаемся преобразовать в число
            new_limit = int(message.text.strip())
            
            # Проверяем диапазон
            if new_limit < 1 or new_limit > 20:
                error_text = "❌ <b>Ошибка: Неверный диапазон</b>\n\nВведите число от 1 до 20:"
                error_keyboard = get_back_to_antispam_keyboard()
                
                # Пытаемся отредактировать последнее сообщение бота
                if last_message_id:
                    try:
                        fake_query = type('FakeQuery', (), {
                            'message': type('FakeMessage', (), {
                                'chat': message.chat,
                                'message_id': last_message_id,
                                'photo': None, 'video': None, 'document': None,
                                'audio': None, 'voice': None, 'video_note': None
                            })(),
                            'answer': lambda **kwargs: None
                        })()
                        await edit_message(query=fake_query, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", bot=bot)
                        return
                    except Exception:
                        # Если редактирование не удалось, удаляем старое сообщение
                        try:
                            await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                        except Exception:
                            pass
                
                # Отправляем новое сообщение с ошибкой
                sent_message = await bot.send_message(
                    chat_id=message.chat.id,
                    text=error_text,
                    reply_markup=error_keyboard,
                    parse_mode="HTML"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                return
            
            # Загружаем текущие настройки и сохраняем новый лимит
            settings = await load_plugin_settings("antispam", async_session_local)
            updated_settings = update_plugin_setting(settings, "max_messages", new_limit)
            await save_plugin_settings("antispam", updated_settings, async_session_local)
            
            # Синхронизируем глобальные переменные в плагине
            await sync_antispam_settings(async_session_local)
            
            # Возвращаемся к настройкам
            await state.set_state(AntispamSettingsStates.VIEW)
            
            # Формируем текст настроек антиспама
            status_emoji = "🟢" if updated_settings.get("enabled", True) else "🔴"
            status_text = "Включен" if updated_settings.get("enabled", True) else "Выключен"
            
            settings_text = f"""🔄 <b>Настройки антиспама</b>

{status_emoji} <b>Статус:</b> {status_text}
📊 <b>Лимит:</b> {updated_settings.get('max_messages', 5)} сообщений
⏱️ <b>Период:</b> {updated_settings.get('window_seconds', 10)} секунд

<i>Антиспам автоматически удаляет сообщения пользователей, которые превышают лимит сообщений за указанный период времени.</i>"""
            
            settings_keyboard = get_antispam_settings_keyboard(updated_settings)
            
            # Пытаемся отредактировать последнее сообщение бота
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('FakeMessage', (), {
                            'chat': message.chat,
                            'message_id': last_message_id,
                            'photo': None, 'video': None, 'document': None,
                            'audio': None, 'voice': None, 'video_note': None
                        })(),
                        'answer': lambda **kwargs: None
                    })()
                    await edit_message(query=fake_query, text=settings_text, reply_markup=settings_keyboard, parse_mode="HTML", bot=bot)
                    logger.info(f"Antispam limit changed to {new_limit} by admin {message.from_user.id}")
                    return
                except Exception:
                    # Если редактирование не удалось, удаляем старое сообщение
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                    except Exception:
                        pass
            
            # Fallback: отправляем новое сообщение
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=settings_text,
                reply_markup=settings_keyboard,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            logger.info(f"Antispam limit changed to {new_limit} by admin {message.from_user.id}")
            
        except ValueError:
            # Не число
            error_text = "❌ <b>Ошибка: Введите число</b>\n\nВведите новый лимит (от 1 до 20):"
            error_keyboard = get_back_to_antispam_keyboard()
            
            # Пытаемся отредактировать последнее сообщение бота
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('FakeMessage', (), {
                            'chat': message.chat,
                            'message_id': last_message_id,
                            'photo': None, 'video': None, 'document': None,
                            'audio': None, 'voice': None, 'video_note': None
                        })(),
                        'answer': lambda **kwargs: None
                    })()
                    await edit_message(query=fake_query, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", bot=bot)
                    return
                except Exception:
                    # Если редактирование не удалось, удаляем старое сообщение
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                    except Exception:
                        pass
            
            # Fallback: отправляем новое сообщение с ошибкой
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=error_text,
                reply_markup=error_keyboard,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            
    except Exception as e:
        logger.error(f"Error in handle_limit_input: {e}")
        # Последний fallback
        try:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Произошла ошибка. Попробуйте еще раз.",
                parse_mode="HTML"
            )
        except Exception:
            pass


async def handle_antispam_edit_window(query: CallbackQuery, state: FSMContext, bot: Bot, async_session_local):
    """Начать редактирование периода времени"""
    await safe_answer_callback(query)
    
    # Загружаем настройки из БД
    settings = await load_plugin_settings("antispam", async_session_local)
    
    # Устанавливаем состояние ожидания ввода периода
    await state.set_state(AntispamSettingsStates.WAITING_WINDOW)
    
    text = f"""⏱️ <b>Изменение периода времени</b>

Текущий период: <b>{settings['window_seconds']}</b> секунд

Введите новый период (от 5 до 300 секунд):"""
    
    keyboard = get_back_to_antispam_keyboard()
    
    # Сохраняем message_id в состоянии
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)


async def handle_window_input(message: Message, state: FSMContext, bot: Bot, async_session_local):
    """Обработка ввода нового периода времени"""
    try:
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass  # Игнорируем ошибки удаления
        
        # Получаем message_id последнего сообщения бота из FSM
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        
        try:
            # Пытаемся преобразовать в число
            new_window = int(message.text.strip())
            
            # Проверяем диапазон
            if new_window < 5 or new_window > 300:
                error_text = "❌ <b>Ошибка: Неверный диапазон</b>\n\nВведите число от 5 до 300 секунд:"
                error_keyboard = get_back_to_antispam_keyboard()
                
                # Пытаемся отредактировать последнее сообщение бота
                if last_message_id:
                    try:
                        fake_query = type('FakeQuery', (), {
                            'message': type('FakeMessage', (), {
                                'chat': message.chat,
                                'message_id': last_message_id,
                                'photo': None, 'video': None, 'document': None,
                                'audio': None, 'voice': None, 'video_note': None
                            })(),
                            'answer': lambda **kwargs: None
                        })()
                        await edit_message(query=fake_query, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", bot=bot)
                        return
                    except Exception:
                        # Если редактирование не удалось, удаляем старое сообщение
                        try:
                            await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                        except Exception:
                            pass
                
                # Отправляем новое сообщение с ошибкой
                sent_message = await bot.send_message(
                    chat_id=message.chat.id,
                    text=error_text,
                    reply_markup=error_keyboard,
                    parse_mode="HTML"
                )
                await state.update_data(last_message_id=sent_message.message_id)
                return
            
            # Загружаем текущие настройки и обновляем период
            settings = await load_plugin_settings("antispam", async_session_local)
            updated_settings = update_plugin_setting(settings, "window_seconds", new_window)
            await save_plugin_settings("antispam", updated_settings, async_session_local)
            
            # Синхронизируем глобальные переменные в плагине
            await sync_antispam_settings(async_session_local)
            
            # Возвращаемся к настройкам
            await state.set_state(AntispamSettingsStates.VIEW)
            
            # Формируем текст настроек антиспама
            status_emoji = "🟢" if updated_settings["enabled"] else "🔴"
            status_text = "Включен" if updated_settings["enabled"] else "Выключен"
            
            settings_text = f"""🔄 <b>Настройки антиспама</b>

{status_emoji} <b>Статус:</b> {status_text}
📊 <b>Лимит:</b> {updated_settings['max_messages']} сообщений
⏱️ <b>Период:</b> {updated_settings['window_seconds']} секунд

<i>Антиспам автоматически удаляет сообщения пользователей, которые превышают лимит сообщений за указанный период времени.</i>"""
            
            settings_keyboard = get_antispam_settings_keyboard(updated_settings)
            
            # Пытаемся отредактировать последнее сообщение бота
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('FakeMessage', (), {
                            'chat': message.chat,
                            'message_id': last_message_id,
                            'photo': None, 'video': None, 'document': None,
                            'audio': None, 'voice': None, 'video_note': None
                        })(),
                        'answer': lambda **kwargs: None
                    })()
                    await edit_message(query=fake_query, text=settings_text, reply_markup=settings_keyboard, parse_mode="HTML", bot=bot)
                    logger.info(f"Antispam window changed to {new_window} seconds by admin {message.from_user.id}")
                    return
                except Exception:
                    # Если редактирование не удалось, удаляем старое сообщение
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                    except Exception:
                        pass
            
            # Fallback: отправляем новое сообщение
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=settings_text,
                reply_markup=settings_keyboard,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            logger.info(f"Antispam window changed to {new_window} seconds by admin {message.from_user.id}")
            
        except ValueError:
            # Не число
            error_text = "❌ <b>Ошибка: Введите число</b>\n\nВведите новый период (от 5 до 300 секунд):"
            error_keyboard = get_back_to_antispam_keyboard()
            
            # Пытаемся отредактировать последнее сообщение бота
            if last_message_id:
                try:
                    fake_query = type('FakeQuery', (), {
                        'message': type('FakeMessage', (), {
                            'chat': message.chat,
                            'message_id': last_message_id,
                            'photo': None, 'video': None, 'document': None,
                            'audio': None, 'voice': None, 'video_note': None
                        })(),
                        'answer': lambda **kwargs: None
                    })()
                    await edit_message(query=fake_query, text=error_text, reply_markup=error_keyboard, parse_mode="HTML", bot=bot)
                    return
                except Exception:
                    # Если редактирование не удалось, удаляем старое сообщение
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                    except Exception:
                        pass
            
            # Fallback: отправляем новое сообщение с ошибкой
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=error_text,
                reply_markup=error_keyboard,
                parse_mode="HTML"
            )
            await state.update_data(last_message_id=sent_message.message_id)
            
    except Exception as e:
        logger.error(f"Error in handle_window_input: {e}")
        # Последний fallback
        try:
            await bot.send_message(
                chat_id=message.chat.id,
                text="❌ Произошла ошибка. Попробуйте еще раз.",
                parse_mode="HTML"
            )
        except Exception:
            pass


# Функции get_antispam_config и update_antispam_config удалены
# Теперь настройки хранятся в БД и загружаются через load_plugin_settings
