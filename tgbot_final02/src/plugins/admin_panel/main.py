"""
Главное меню админ панели
"""

import logging
from datetime import datetime
from aiogram import Dispatcher, Bot, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import func

from config import get_settings, get_logo_path
from models.base import ScheduledPost
from .keyboards import get_main_menu_keyboard, get_posts_list_keyboard, get_back_to_menu_keyboard, get_post_view_keyboard, get_posts_menu_keyboard, get_post_actions_keyboard, get_buttons_settings_keyboard, get_stats_menu_keyboard
from .message_utils import edit_message
from .post_editor import (
    start_post_creation,
    handle_topic_selection,
    handle_time_selection,
    handle_manual_time_input,
    handle_text_input,
    handle_media_selection,
    handle_media_input,
    confirm_post_creation,
    handle_back_navigation,
    process_user_input,
    PostEditorStates,
    show_buttons_settings,
    handle_buttons_add,
    handle_button_text_input,
    handle_button_url_input,
    handle_button_delete,
    handle_time_edit,
    handle_time_edit_input
)
from .admin_management import AdminManagementStates
from .triggers_management import (
    TriggerStates,
    show_triggers_menu,
    handle_trigger_add,
    handle_trigger_toggle,
    handle_trigger_delete,
    handle_trigger_text_input,
    handle_response_text_input,
    handle_triggers_pagination
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def safe_answer_callback(query: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await query.answer()
    except Exception as e:
        logger.debug(f"Failed to answer callback query: {e}")


async def get_posts_list(async_session_local, post_type: str):
    """Вспомогательная функция для получения списка постов"""
    async with async_session_local() as session:
        result = await session.execute(
            select(ScheduledPost).filter_by(status=post_type).order_by(ScheduledPost.publish_time.desc()).limit(50)
        )
        
        posts = []
        for post in result.scalars():
            # Формируем описание поста с медиа
            post_description = ""
            if post.text:
                post_description = post.text[:50] + '...' if len(post.text) > 50 else post.text
            else:
                post_description = "Без текста"
            
            # Добавляем информацию о медиа
            if post.media_type:
                media_emoji = {
                    'photo': '📷',
                    'video': '🎥', 
                    'document': '📄',
                    'audio': '🎵',
                    'voice': '🎤',
                    'video_note': '📹'
                }
                media_icon = media_emoji.get(post.media_type, '📎')
                post_description = f"{media_icon} {post_description}"
            
            posts.append({
                'id': post.id,
                'publish_time': post.publish_time,
                'status': post.status,
                'text': post_description,
                'media_type': post.media_type,
                'media_file_id': post.media_file_id
            })
    
    return posts


class IsAdmin(BaseFilter):
    """Фильтр для проверки прав администратора"""
    async def __call__(self, obj: types.TelegramObject) -> bool:
        user_id = obj.from_user.id
        
        # Проверяем администраторов из конфига
        is_config_admin = user_id in settings.ADMINS
        if is_config_admin:
            # User is config admin
            return True
        
        # Проверяем администраторов из БД
        # Получаем async_session_local из контекста
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from models.init_db import get_corrected_database_url
        corrected_db_url = get_corrected_database_url(settings.DATABASE_URL)
        async_engine = create_async_engine(corrected_db_url)
        AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
        
        try:
            async with AsyncSessionLocal() as session:
                from models.base import Admin
                result = await session.execute(
                    select(Admin).filter_by(telegram_id=user_id)
                )
                db_admin = result.scalar_one_or_none()
                is_db_admin = db_admin is not None
                
                if is_db_admin:
                    # User is DB admin
                    pass
                else:
                    # User is not admin
                    pass
                
                return is_db_admin
        except Exception as e:
            logger.error(f"ADMIN_FILTER: Error checking DB admin: {e}")
            return False


async def admin_command_handler(message: Message, state: FSMContext, async_session_local, bot: Bot):
    """Обработчик команды /admin"""
    # User accessed admin panel
    
    # Показываем главное меню
    await show_main_menu_from_message(message, state, async_session_local, bot)
    
    # Удаляем команду после отправки ответа
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Failed to delete admin command: {e}")


async def show_main_menu(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Показать главное меню админ панели"""
    # Очищаем состояние при переходе в главное меню
    await state.clear()
    logger.info(f"🧹 SHOW_MAIN_MENU: Cleared FSM state when showing main menu")
    
    keyboard = get_main_menu_keyboard()
    caption = "🔒 <b>Панель администратора</b>\n\nВыберите действие:"
    
    # Удаляем старое сообщение и отправляем новое с логотипом
    try:
        await bot.delete_message(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id
        )
    except Exception as e:
        logger.warning(f"Failed to delete old message: {e}")
    
    # Отправляем фото с логотипом
    try:
        with open(get_logo_path(), "rb") as logo_file:
            photo = BufferedInputFile(logo_file.read(), filename="logo.png")
        await bot.send_photo(
            chat_id=query.message.chat.id,
            photo=photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except FileNotFoundError:
        # Если логотип не найден, отправляем обычное сообщение
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Failed to send logo: {e}")
        # Fallback - отправляем обычное сообщение
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    # Безопасный ответ на callback query
    await safe_answer_callback(query)


async def show_main_menu_from_callback(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Показать главное меню из callback query (универсальная функция)"""
    # Очищаем состояние при переходе в главное меню
    await state.clear()
    logger.info(f"🧹 SHOW_MAIN_MENU_FROM_CALLBACK: Cleared FSM state when showing main menu from callback")
    
    keyboard = get_main_menu_keyboard()
    caption = "🔒 <b>Панель администратора</b>\n\nВыберите действие:"
    
    # Удаляем старое сообщение и отправляем новое с логотипом
    try:
        await bot.delete_message(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id
        )
    except Exception as e:
        logger.warning(f"Failed to delete old message: {e}")
    
    # Отправляем фото с логотипом
    try:
        with open(get_logo_path(), "rb") as logo_file:
            photo = BufferedInputFile(logo_file.read(), filename="logo.png")
        await bot.send_photo(
            chat_id=query.message.chat.id,
            photo=photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except FileNotFoundError:
        # Если логотип не найден, отправляем обычное сообщение
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Failed to send logo: {e}")
        # Fallback - отправляем обычное сообщение
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    # Безопасный ответ на callback query
    await safe_answer_callback(query)


async def show_main_menu_from_message(message: Message, state: FSMContext, async_session_local, bot: Bot):
    """Показать главное меню из сообщения"""
    # Очищаем состояние при переходе в главное меню
    await state.clear()
    logger.info(f"🧹 SHOW_MAIN_MENU_FROM_MESSAGE: Cleared FSM state when showing main menu from message")
    
    keyboard = get_main_menu_keyboard()
    caption = "🔒 <b>Панель администратора</b>\n\nВыберите действие:"
    
    # Отправляем фото с логотипом
    try:
        with open(get_logo_path(), "rb") as logo_file:
            photo = BufferedInputFile(logo_file.read(), filename="logo.png")
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except FileNotFoundError:
        # Если логотип не найден, отправляем обычное сообщение
        await bot.send_message(
            chat_id=message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Failed to send logo: {e}")
        # Fallback - отправляем обычное сообщение
        await bot.send_message(
            chat_id=message.chat.id,
            text=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


async def handle_new_post(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка создания нового поста"""
    await start_post_creation(query, state, async_session_local, bot)


async def handle_posts_list(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка просмотра списка постов"""
    await safe_answer_callback(query)
    
    # Очищаем состояние при переходе к списку постов
    await state.clear()
    logger.info(f"🧹 HANDLE_POSTS_LIST: Cleared FSM state when showing posts list")
    
    # Показываем простое меню выбора
    keyboard = get_posts_menu_keyboard()
    text = "📋 <b>Посты</b>\n\nВыберите тип постов:"
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_posts_type_selection(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка выбора типа постов"""
    await safe_answer_callback(query)
    
    # Очищаем состояние при переходе между типами постов
    await state.clear()
    logger.info(f"🧹 HANDLE_POSTS_TYPE_SELECTION: Cleared FSM state when selecting post type")
    
    # Парсим тип постов
    post_type = query.data.split(":")[1]
    
    # Получаем посты из БД
    posts = await get_posts_list(async_session_local, post_type)
    
    if not posts:
        type_text = "⏳ Запланированные" if post_type == "pending" else "✅ Отправленные"
        text = f"📋 <b>{type_text}</b>\n\nПостов не найдено."
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Показываем первую страницу
    keyboard = get_posts_list_keyboard(posts, page=0, post_type=post_type)
    type_text = "⏳ Запланированные" if post_type == "pending" else "✅ Отправленные"
    text = f"📋 <b>{type_text}</b>\n\nВыберите пост для просмотра:"
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_posts_pagination(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка пагинации списка постов"""
    await safe_answer_callback(query)
    
    # Очищаем состояние при пагинации постов
    await state.clear()
    logger.info(f"🧹 HANDLE_POSTS_PAGINATION: Cleared FSM state when paginating posts")
    
    # Парсим номер страницы и тип постов
    parts = query.data.split(":")
    page = int(parts[2])
    post_type = parts[3] if len(parts) > 3 else "pending"
    
    # Получаем посты из БД
    posts = await get_posts_list(async_session_local, post_type)
    
    # Показываем нужную страницу
    keyboard = get_posts_list_keyboard(posts, page=page, post_type=post_type)
    type_text = "⏳ Запланированные" if post_type == "pending" else "✅ Отправленные"
    text = f"📋 <b>{type_text}</b>\n\nВыберите пост для просмотра:"
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_post_view(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка просмотра отдельного поста"""
    await safe_answer_callback(query)
    
    # Парсим ID поста
    post_id = int(query.data.split(":")[1])
    
    # Проверяем, нужно ли обновить пост в Telegram (если мы возвращаемся из меню настроек кнопок)
    data = await state.get_data()
    if data.get('editing_post_id') == post_id and data.get('buttons_updated'):
        # Обновляем пост в Telegram с новыми кнопками
        await update_post_in_telegram(post_id, async_session_local, bot)
        logger.info(f"🔄 HANDLE_POST_VIEW: Updated post {post_id} in Telegram with new buttons")
    
    # Очищаем состояние FSM при просмотре поста
    await state.clear()
    logger.info(f"🧹 HANDLE_POST_VIEW: Cleared FSM state when viewing post")
    
    # Получаем пост из БД
    async with async_session_local() as session:
        result = await session.execute(
            select(ScheduledPost).filter_by(id=post_id)
        )
        post = result.scalar_one_or_none()
    
    if not post:
        text = "❌ Пост не найден"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Формируем информацию о посте
    status_emoji = {
        'pending': '⏳',
        'published': '✅',
        'failed': '❌',
        'deleted': '🗑️'
    }
    
    # Сначала показываем текст поста (если есть)
    if post.text:
        post_info = f"{post.text}\n\n"
    else:
        post_info = ""
    
    # Затем техническую информацию
    post_info += f"📊 Статус: {status_emoji.get(post.status, '❓')} {post.status}\n"
    
    # Форматируем время без микросекунд
    if post.publish_time:
        if isinstance(post.publish_time, str):
            # Если это строка, парсим и форматируем
            from datetime import datetime
            try:
                publish_time = datetime.fromisoformat(post.publish_time.replace('Z', '+00:00'))
                formatted_time = publish_time.strftime("%d.%m.%Y %H:%M:%S")
            except:
                formatted_time = post.publish_time
        else:
            # Если это datetime объект
            formatted_time = post.publish_time.strftime("%d.%m.%Y %H:%M:%S")
        post_info += f"⏰ Время: {formatted_time}\n"
    
    post_info += f"📍 Топик: {post.topic_id or 'Основной чат'}\n"
    
    if post.media_type:
        media_emoji = {
            "photo": "📷", 
            "video": "🎥", 
            "document": "📄",
            "audio": "🎵",
            "voice": "🎤",
            "video_note": "📹"
        }
        post_info += f"🖼️ Медиа: {media_emoji.get(post.media_type, '📎')} {post.media_type}\n"
    
    # Отображаем информацию о кнопках
    if post.buttons_json:
        try:
            import json
            buttons_data = json.loads(post.buttons_json)
            if buttons_data:
                post_info += f"🔘 Кнопки: {len(buttons_data)} шт.\n"
                for i, button in enumerate(buttons_data, 1):
                    post_info += f"  {i}. {button.get('text', 'Кнопка')}\n"
        except:
            post_info += f"🔘 Кнопки: есть (ошибка парсинга)\n"
    
    if post.published_at:
        # Форматируем время публикации без микросекунд
        if isinstance(post.published_at, str):
            # Если это строка, парсим и форматируем
            from datetime import datetime
            try:
                published_time = datetime.fromisoformat(post.published_at.replace('Z', '+00:00'))
                formatted_published_time = published_time.strftime("%d.%m.%Y %H:%M:%S")
            except:
                formatted_published_time = post.published_at
        else:
            # Если это datetime объект
            formatted_published_time = post.published_at.strftime("%d.%m.%Y %H:%M:%S")
        post_info += f"✅ Опубликован: {formatted_published_time}\n"
    
    # Примечание: Прямые ссылки на сообщения в топиках форумов не поддерживаются Telegram API
    has_media = bool(post.media_type and post.media_file_id)
    keyboard = get_post_actions_keyboard(post_id, post.status, has_media)
    
    # Если есть медиа, отправляем его с подписью
    if post.media_type and post.media_file_id:
        try:
            # Сначала удаляем старое сообщение (если это не первое сообщение)
            if query.message.message_id and query.message.message_id > 0:  # Проверяем, что message_id валидный
                try:
                    await bot.delete_message(
                        chat_id=query.message.chat.id,
                        message_id=query.message.message_id
                    )
                    logger.debug(f"Deleted old message {query.message.message_id} before showing post with media")
                except Exception as delete_error:
                    logger.warning(f"Failed to delete old message: {delete_error}")
            
            # Отправляем медиа с подписью
            if post.media_type == 'photo':
                await bot.send_photo(
                    chat_id=query.message.chat.id,
                    photo=post.media_file_id,
                    caption=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            elif post.media_type == 'video':
                await bot.send_video(
                    chat_id=query.message.chat.id,
                    video=post.media_file_id,
                    caption=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            elif post.media_type == 'document':
                await bot.send_document(
                    chat_id=query.message.chat.id,
                    document=post.media_file_id,
                    caption=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            elif post.media_type == 'audio':
                await bot.send_audio(
                    chat_id=query.message.chat.id,
                    audio=post.media_file_id,
                    caption=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            elif post.media_type == 'voice':
                await bot.send_voice(
                    chat_id=query.message.chat.id,
                    voice=post.media_file_id,
                    caption=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            elif post.media_type == 'video_note':
                await bot.send_video_note(
                    chat_id=query.message.chat.id,
                    video_note=post.media_file_id
                )
                # Для video_note отправляем отдельно текст
                await bot.send_message(
                    chat_id=query.message.chat.id,
                    text=post_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Failed to send media for post {post_id}: {e}")
            # Если не удалось отправить медиа, отправляем только текст
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=post_info,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    else:
        # Если нет медиа, проверяем нужно ли редактировать или отправить новое сообщение
        if query.message.message_id and query.message.message_id > 0:
            # Редактируем существующее сообщение
            await edit_message(query, post_info, keyboard, "HTML", bot)
        else:
            # Отправляем новое сообщение
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=post_info,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


async def handle_post_add_media(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Добавить медиа к запланированному посту"""
    await safe_answer_callback(query)
    
    post_id = int(query.data.split(":")[1])
    
    # Сохраняем ID поста в состоянии
    await state.update_data(editing_post_id=post_id, action="add_media")
    
    text = """📎 <b>Добавление медиа к посту</b>

Отправьте медиа-файл (фото, видео, документ, аудио) для добавления к посту.

<b>Поддерживаемые типы:</b>
📷 Фото
🎥 Видео  
📄 Документы
🎵 Аудио
🎤 Голосовые сообщения
📹 Видео-заметки

<i>Или нажмите "Отмена" для возврата к посту.</i>"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_view:{post_id}")]
    ])
    
    # Редактируем сообщение и сохраняем message_id
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    
    # Сохраняем message_id для последующего удаления
    await state.update_data(media_input_message_id=current_message_id)
    
    # Устанавливаем состояние ожидания медиа
    from .post_editor import PostEditorStates
    await state.set_state(PostEditorStates.MEDIA_INPUT)


async def handle_post_replace_media(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Заменить медиа в запланированном посте"""
    await safe_answer_callback(query)
    
    post_id = int(query.data.split(":")[1])
    
    # Сохраняем ID поста в состоянии
    await state.update_data(editing_post_id=post_id, action="replace_media")
    
    text = """🔄 <b>Замена медиа в посте</b>

Отправьте новое медиа-файл для замены текущего.

<b>Поддерживаемые типы:</b>
📷 Фото
🎥 Видео  
📄 Документы
🎵 Аудио
🎤 Голосовые сообщения
📹 Видео-заметки

<i>Или нажмите "Отмена" для возврата к посту.</i>"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_view:{post_id}")]
    ])
    
    # Редактируем сообщение и сохраняем message_id
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    
    # Сохраняем message_id для последующего удаления
    await state.update_data(media_input_message_id=current_message_id)
    
    # Устанавливаем состояние ожидания медиа
    from .post_editor import PostEditorStates
    await state.set_state(PostEditorStates.MEDIA_INPUT)


async def handle_post_remove_media(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Удалить медиа из запланированного поста"""
    await safe_answer_callback(query)
    
    post_id = int(query.data.split(":")[1])
    
    # Подтверждение удаления
    text = """❌ <b>Удаление медиа</b>

Вы уверены, что хотите удалить медиа из этого поста?

Пост останется только с текстом."""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"post_confirm_remove_media:{post_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_view:{post_id}")]
    ])
    
    await edit_message(query, text, keyboard, "HTML", bot)


async def handle_post_confirm_remove_media(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Подтверждение удаления медиа"""
    await safe_answer_callback(query)
    
    post_id = int(query.data.split(":")[1])
    
    try:
        # Удаляем медиа из поста в БД
        async with async_session_local() as session:
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if post:
                post.media_type = None
                post.media_file_id = None
                await session.commit()
                
                logger.info(f"✅ MEDIA_REMOVED: Removed media from post {post_id}")
                
                # Сразу показываем обновленный пост
                await handle_post_view(query, state, async_session_local, bot)
                return
            else:
                text = "❌ Пост не найден"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ К посту", callback_data=f"post_view:{post_id}")]
                ])
                await edit_message(query, text, keyboard, "HTML", bot)
                
    except Exception as e:
        logger.error(f"❌ MEDIA_REMOVE_ERROR: Failed to remove media from post {post_id}: {e}")
        text = "❌ Ошибка при удалении медиа"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К посту", callback_data=f"post_view:{post_id}")]
        ])
        await edit_message(query, text, keyboard, "HTML", bot)


async def handle_antimat(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка настроек антимата"""
    from .antimat_settings import handle_antimat as antimat_handler
    await antimat_handler(query, state, bot, async_session_local)


async def handle_antispam(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка настроек антиспама"""
    from .antispam_settings import handle_antispam as antispam_handler
    await antispam_handler(query, state, bot, async_session_local)


async def handle_settings(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка настроек"""
    await safe_answer_callback(query)
    
    from .admin_management import handle_settings_menu
    await handle_settings_menu(query, state, async_session_local, bot)


async def handle_status(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка статуса системы"""
    await safe_answer_callback(query)
    
    try:
        # Импортируем модуль мониторинга
        from .system_monitor import get_system_info, get_bot_uptime, get_resource_status_emoji
        
        # Получаем статистику из БД
        async with async_session_local() as session:
            # Количество постов по статусам
            result = await session.execute(
                select(ScheduledPost.status, func.count(ScheduledPost.id)).group_by(ScheduledPost.status)
            )
            post_stats = dict(result.all())
            
            # Статистика модерации из реальных данных
            from models.base import Membership, MessageLog
            
            # Подсчитываем события модерации
            moderation_result = await session.execute(
                select(Membership.event_type, func.count(Membership.event_id)).group_by(Membership.event_type)
            )
            moderation_events = dict(moderation_result.all())
            
            # Подсчитываем общее количество сообщений (для статистики)
            total_messages_result = await session.execute(
                select(func.count(MessageLog.id))
            )
            total_messages = total_messages_result.scalar() or 0
            
            moderation_stats = {
                'deleted_messages': total_messages,  # Общее количество сообщений в логах
                'warned_users': moderation_events.get('warn', 0),
                'banned_users': moderation_events.get('ban', 0),
                'muted_users': moderation_events.get('mute', 0),
                'kicked_users': moderation_events.get('kick', 0),
                'joined_users': moderation_events.get('join', 0),
                'left_users': moderation_events.get('leave', 0),
            }
        
        # Получаем информацию о системе
        system_info = get_system_info()
        uptime = get_bot_uptime()
        
        # Формируем детальный статус
        status_text = "📈 <b>Статус системы</b>\n\n"
        
        # Информация о боте
        status_text += "🤖 <b>Информация о боте</b>\n"
        status_text += f"⏱️ Аптайм: {uptime}\n"
        status_text += f"🐍 Python: {system_info['python_version']}\n"
        status_text += f"💻 ОС: {system_info['platform']} {system_info['platform_version']}\n\n"
        
        # Использование ресурсов
        status_text += "💻 <b>Использование ресурсов</b>\n"
        cpu_emoji = get_resource_status_emoji(system_info['cpu_percent'])
        status_text += f"{cpu_emoji} CPU: {system_info['cpu_percent']:.1f}% ({system_info['cpu_count']} ядер)\n"
        
        memory_emoji = get_resource_status_emoji(system_info['memory_percent'])
        status_text += f"{memory_emoji} RAM: {system_info['memory_percent']:.1f}% "
        status_text += f"({system_info['memory_used_gb']:.1f}/{system_info['memory_total_gb']:.1f} GB)\n"
        
        disk_emoji = get_resource_status_emoji(system_info['disk_percent'])
        status_text += f"{disk_emoji} Диск: {system_info['disk_percent']:.1f}% "
        status_text += f"({system_info['disk_used_gb']:.1f}/{system_info['disk_total_gb']:.1f} GB)\n\n"
        
        # Статистика постинга
        status_text += "📝 <b>Статистика постинга</b>\n"
        status_text += f"⏳ Ожидающих: {post_stats.get('pending', 0)}\n"
        status_text += f"✅ Опубликованных: {post_stats.get('published', 0)}\n"
        status_text += f"❌ Неудачных: {post_stats.get('failed', 0)}\n"
        status_text += f"🗑️ Удаленных: {post_stats.get('deleted', 0)}\n\n"
        
        # Статистика модерации
        status_text += "🛡️ <b>Статистика модерации</b>\n"
        status_text += f"📝 Всего сообщений: {moderation_stats['deleted_messages']}\n"
        status_text += f"⚠️ Предупреждений: {moderation_stats['warned_users']}\n"
        status_text += f"🔇 Мутов: {moderation_stats['muted_users']}\n"
        status_text += f"🚫 Банов: {moderation_stats['banned_users']}\n"
        status_text += f"👢 Киков: {moderation_stats['kicked_users']}\n"
        status_text += f"👥 Присоединилось: {moderation_stats['joined_users']}\n"
        status_text += f"👋 Покинуло: {moderation_stats['left_users']}\n\n"
        
        # Статус модулей
        status_text += "🔧 <b>Статус модулей</b>\n"
        status_text += "🟢 Антиспам: Активен\n"
        status_text += "🟢 Антимат: Активен\n"
        status_text += "🟢 Планировщик: Активен\n"
        status_text += "🟢 Модерация: Активна\n"
        
        # Создаем клавиатуру только с кнопкой "Назад в меню"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
        ])
        await edit_message(query, status_text, keyboard, "HTML", bot)
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        error_text = "❌ <b>Ошибка получения статуса</b>\n\nНе удалось загрузить информацию о системе."
        # Создаем клавиатуру только с кнопкой "Назад в меню"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:main_menu")]
        ])
        await edit_message(query, error_text, keyboard, "HTML", bot)


async def handle_stats_detailed(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Меню статистики: две вкладки."""
    await safe_answer_callback(query)
    # Просто показываем меню вкладок статистики
    text = "📊 <b>Статистика</b>\n\nВыберите раздел:"
    await edit_message(query, text, get_stats_menu_keyboard(), "HTML", bot)

async def handle_post_publish(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка публикации поста сейчас"""
    await safe_answer_callback(query)
    
    # Парсим ID поста
    post_id = int(query.data.split(":")[1])
    
    try:
        async with async_session_local() as session:
            # Получаем пост из БД
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post:
                await edit_message(query, "❌ Пост не найден", get_back_to_menu_keyboard(), "HTML", bot)
                return
            
            if post.status != 'pending':
                error_text = f"❌ Пост уже имеет статус: {post.status}"
                await edit_message(query, error_text, get_back_to_menu_keyboard(), "HTML", bot)
                return
            
            # Публикуем пост в Telegram
            try:
                # Создаем reply_markup если есть кнопки
                reply_markup = None
                if post.buttons_json:
                    try:
                        import json
                        buttons_data = json.loads(post.buttons_json)
                        if buttons_data:
                            keyboard_buttons = []
                            for button_data in buttons_data:
                                keyboard_buttons.append([InlineKeyboardButton(
                                    text=button_data.get('text', 'Кнопка'),
                                    url=button_data.get('url', '#')
                                )])
                            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                            logger.info(f"Post {post_id} has {len(buttons_data)} button(s)")
                    except Exception as e:
                        logger.error(f"Failed to parse buttons for post {post_id}: {e}")
                
                # Определяем параметры отправки
                send_params = {
                    'chat_id': post.chat_id,
                    'reply_markup': reply_markup
                }
                
                # Логируем информацию о посте
                logger.info(f"Publishing post {post_id}: chat_id={post.chat_id}, topic_id={post.topic_id}, chat_id_type={'group' if post.chat_id < 0 else 'private'}")
                
                # Добавляем message_thread_id только если это не личные сообщения
                if post.topic_id and post.chat_id < 0:  # Отрицательный chat_id = группа
                    send_params['message_thread_id'] = post.topic_id
                    logger.info(f"Using message_thread_id={post.topic_id} for group chat")
                
                if post.media_file_id and post.media_type:
                    # Отправляем медиа с текстом
                    send_params['caption'] = post.text
                    
                    if post.media_type == 'photo':
                        sent_message = await bot.send_photo(
                            photo=post.media_file_id,
                            **send_params
                        )
                    elif post.media_type == 'video':
                        sent_message = await bot.send_video(
                            video=post.media_file_id,
                            **send_params
                        )
                    elif post.media_type == 'document':
                        sent_message = await bot.send_document(
                            document=post.media_file_id,
                            **send_params
                        )
                    elif post.media_type == 'audio':
                        sent_message = await bot.send_audio(
                            audio=post.media_file_id,
                            **send_params
                        )
                    elif post.media_type == 'voice':
                        sent_message = await bot.send_voice(
                            voice=post.media_file_id,
                            **send_params
                        )
                    elif post.media_type == 'video_note':
                        sent_message = await bot.send_video_note(
                            video_note=post.media_file_id,
                            **send_params
                        )
                else:
                    # Отправляем только текст
                    send_params['text'] = post.text
                    sent_message = await bot.send_message(**send_params)
                
                # Обновляем статус поста в БД
                post.status = 'published'
                post.published_at = datetime.now()
                post.published_by = query.from_user.id
                post.telegram_message_id = sent_message.message_id
                
                await session.commit()
                
                logger.info(f"Post {post_id} published immediately by admin {query.from_user.id}")
                
                # Показываем подтверждение
                success_text = (f"✅ <b>Пост #{post_id} успешно опубликован!</b>\n\n"
                               f"Пост отправлен в чат и обновлен в базе данных.")
                
                # Показываем подтверждение
                await edit_message(query, success_text, get_back_to_menu_keyboard(), "HTML", bot)
                
            except Exception as e:
                logger.error(f"Failed to publish post {post_id}: {e}")
                # Обновляем статус на failed
                post.status = 'failed'
                await session.commit()
                
                error_text = f"❌ Ошибка при публикации поста: {str(e)}"
                
                # Аналогично для ошибки
                await edit_message(query, error_text, get_back_to_menu_keyboard(), "HTML", bot)
            
    except Exception as e:
        logger.error(f"Error publishing post {post_id}: {e}")
        error_text = "❌ Ошибка при публикации поста. Попробуйте еще раз."
        
        # Аналогично для ошибки
        await edit_message(query, error_text, get_back_to_menu_keyboard(), "HTML", bot)


async def handle_post_delete(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка удаления поста"""
    await safe_answer_callback(query)
    
    # Парсим ID поста
    post_id = int(query.data.split(":")[1])
    
    try:
        async with async_session_local() as session:
            # Получаем пост из БД
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post:
                text = "❌ Пост не найден"
                await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
                return
            
            # Если пост уже опубликован, пытаемся удалить его из Telegram
            if post.status == 'published' and post.telegram_message_id:
                try:
                    await bot.delete_message(
                        chat_id=post.chat_id,
                        message_id=post.telegram_message_id
                    )
                    logger.info(f"Deleted message {post.telegram_message_id} from chat {post.chat_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete message from Telegram: {e}")
            
            # Удаляем пост из БД
            await session.delete(post)
            await session.commit()
            
            logger.info(f"Post {post_id} deleted by admin {query.from_user.id}")
            
            # Показываем подтверждение
            success_text = (f"✅ <b>Пост #{post_id} успешно удален!</b>\n\n"
                           f"Пост удален из базы данных и из чата (если был опубликован).")
            
            # Показываем подтверждение
            await edit_message(query, success_text, get_back_to_menu_keyboard(), "HTML", bot)
            
    except Exception as e:
        logger.error(f"Error deleting post {post_id}: {e}")
        error_text = "❌ Ошибка при удалении поста. Попробуйте еще раз."
        
        # Аналогично для ошибки
        await edit_message(query, error_text, get_back_to_menu_keyboard(), "HTML", bot)


async def update_post_in_telegram(post_id: int, async_session_local, bot: Bot):
    """Обновляет пост в Telegram с новыми кнопками"""
    try:
        async with async_session_local() as session:
            # Получаем пост из БД
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post or post.status != 'published' or not post.telegram_message_id:
                return
            
            # Создаем reply_markup если есть кнопки
            reply_markup = None
            if post.buttons_json:
                try:
                    import json
                    buttons_data = json.loads(post.buttons_json)
                    if buttons_data:
                        keyboard_buttons = []
                        for button_data in buttons_data:
                            keyboard_buttons.append([InlineKeyboardButton(
                                text=button_data.get('text', 'Кнопка'),
                                url=button_data.get('url', '#')
                            )])
                        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                except Exception as e:
                    logger.error(f"Failed to parse buttons for post {post_id}: {e}")
            
            # Обновляем сообщение в Telegram
            if post.media_type and post.media_file_id:
                # Для медиа обновляем подпись
                await bot.edit_message_caption(
                    chat_id=post.chat_id,
                    message_id=post.telegram_message_id,
                    caption=post.text,
                    reply_markup=reply_markup
                )
            else:
                # Для текстовых сообщений обновляем текст
                await bot.edit_message_text(
                    chat_id=post.chat_id,
                    message_id=post.telegram_message_id,
                    text=post.text,
                    reply_markup=reply_markup
                )
            
            logger.info(f"✅ Updated post {post_id} in Telegram with buttons")
            
    except Exception as e:
        logger.error(f"❌ Failed to update post {post_id} in Telegram: {e}")


async def handle_post_edit(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка редактирования поста"""
    await safe_answer_callback(query)
    
    # Парсим ID поста
    post_id = int(query.data.split(":")[1])
    
    # Получаем пост из БД
    async with async_session_local() as session:
        result = await session.execute(
            select(ScheduledPost).filter_by(id=post_id)
        )
        post = result.scalar_one_or_none()
    
    if not post:
        text = "❌ Пост не найден"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Проверяем, можно ли редактировать пост в Telegram
    can_edit_telegram = False
    if post.status == 'published' and post.published_at:
        from datetime import datetime, timedelta
        now = datetime.now()
        if isinstance(post.published_at, str):
            published_at = datetime.fromisoformat(post.published_at.replace('Z', '+00:00'))
        else:
            published_at = post.published_at
        
        # Проверяем, прошло ли менее 48 часов
        if now - published_at.replace(tzinfo=None) < timedelta(hours=48):
            can_edit_telegram = True
    
    # Сохраняем ID поста в состоянии для редактирования
    await state.update_data(editing_post_id=post_id)
    
    # Показываем информацию о посте и запрашиваем новый текст
    post_info = f"✏️ <b>Редактирование поста #{post_id}</b>\n\n"
    post_info += f"📝 Текущий текст: {post.text}\n\n"
    
    # Показываем информацию о возможности редактирования в зависимости от статуса
    if post.status == 'scheduled':
        post_info += "📅 Пост запланирован - будет обновлен при публикации\n\n"
    elif can_edit_telegram:
        post_info += "✅ Пост можно обновить в Telegram (менее 48 часов)\n\n"
    else:
        post_info += "⚠️ Пост старше 48 часов - обновление в Telegram невозможно\n\n"
    
    post_info += "Отправьте новый текст поста:"
    
    # Редактируем сообщение и получаем message_id
    logger.info(f"🔄 START_POST_EDIT: Calling edit_message for post {post_id}")
    current_message_id = await edit_message(query, post_info, get_back_to_menu_keyboard(), "HTML", bot)
    logger.info(f"📝 START_POST_EDIT: edit_message returned message_id: {current_message_id}")
    
    # Сохраняем message_id для последующего удаления
    logger.info(f"💾 START_POST_EDIT: Saving message_id {current_message_id} in FSM state for future deletion")
    await state.update_data(last_message_id=current_message_id)
    
    # Проверяем, что message_id действительно сохранился
    data_check = await state.get_data()
    saved_message_id = data_check.get('last_message_id')
    logger.info(f"✅ START_POST_EDIT: Verified saved message_id in FSM: {saved_message_id}")
    
    # Устанавливаем состояние ожидания нового текста
    from .post_editor import PostEditorStates
    await state.set_state(PostEditorStates.EDITING_TEXT)
    logger.info(f"🏁 START_POST_EDIT: Post edit started for post {post_id}")


async def handle_existing_post_button_add(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка добавления кнопки к существующему посту"""
    await safe_answer_callback(query)
    
    # Получаем post_id из состояния (должен быть сохранен при переходе в настройки кнопок)
    data = await state.get_data()
    post_id = data.get('editing_post_id')
    
    if not post_id:
        text = "❌ Ошибка: не найден ID поста"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Сохраняем post_id в состоянии для последующего использования
    await state.update_data(editing_post_id=post_id)
    
    # Показываем форму добавления кнопки
    text = "📝 <b>Добавление кнопки</b>\n\nВведите название кнопки:"
    keyboard = get_back_to_menu_keyboard()
    
    # Сохраняем message_id для последующего редактирования
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)
    
    from .post_editor import PostEditorStates
    await state.set_state(PostEditorStates.WAITING_BUTTON_TEXT)


async def handle_post_buttons(query: CallbackQuery, state: FSMContext, async_session_local, bot: Bot):
    """Обработка управления кнопками поста"""
    await safe_answer_callback(query)
    
    # Парсим callback_data: post_buttons:{post_id}
    parts = query.data.split(":")
    
    if len(parts) < 2:
        text = "❌ Ошибка: неверный формат команды"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Проверяем, что второй элемент - это число (ID поста)
    if not parts[1].isdigit():
        text = "❌ Ошибка: неверный ID поста"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    try:
        post_id = int(parts[1])
    except ValueError:
        text = "❌ Ошибка: неверный ID поста"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Получаем пост из БД
    async with async_session_local() as session:
        result = await session.execute(
            select(ScheduledPost).filter_by(id=post_id)
        )
        post = result.scalar_one_or_none()
    
    if not post:
        text = "❌ Пост не найден"
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Загружаем кнопки из JSON
    buttons = []
    if post.buttons_json:
        import json
        try:
            buttons = json.loads(post.buttons_json)
        except:
            buttons = []
    
    # Сохраняем данные в состоянии для редактирования
    await state.update_data(
        editing_post_id=post_id,
        buttons=buttons
    )
    
    text = f"⚙️ <b>Настройки кнопок поста #{post_id}</b>\n\n"
    text += f"📊 Кнопок добавлено: {len(buttons)}\n\n"
    
    if buttons:
        text += "Добавленные кнопки:\n"
        for i, button in enumerate(buttons, 1):
            text += f"{i}. {button.get('text', '')}\n"
        text += "\n"
    
    text += "Выберите действие:"
    
    keyboard = get_buttons_settings_keyboard(buttons, post_id)
    await edit_message(query, text, keyboard, "HTML", bot)
    await state.set_state(PostEditorStates.BUTTONS_SETTINGS)




async def handle_text_edit(message: Message, state: FSMContext, async_session_local, bot: Bot):
    """Обработка ввода нового текста для редактирования поста"""
    logger.info(f"🔄 HANDLE_TEXT_EDIT: Starting text edit processing")
    logger.info(f"👤 HANDLE_TEXT_EDIT: User message ID: {message.message_id}, Chat ID: {message.chat.id}")
    logger.info(f"📝 HANDLE_TEXT_EDIT: New text: {message.text[:50]}...")
    
    new_text = message.text
    
    # Получаем ID поста из состояния
    data = await state.get_data()
    post_id = data.get('editing_post_id')
    last_message_id = data.get('last_message_id')
    
    logger.info(f"🔍 HANDLE_TEXT_EDIT: FSM state data: {data}")
    logger.info(f"🔍 HANDLE_TEXT_EDIT: Editing post ID: {post_id}")
    logger.info(f"🔍 HANDLE_TEXT_EDIT: Last message ID from FSM: {last_message_id}")
    
    if not post_id:
        logger.error(f"❌ HANDLE_TEXT_EDIT: No post ID found in state")
        await process_user_input(
            bot, message,
            text="❌ Ошибка: не найден ID поста для редактирования",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
        await state.clear()
        return
    
    try:
        async with async_session_local() as session:
            # Получаем пост из БД
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post:
                logger.error(f"❌ HANDLE_TEXT_EDIT: Post {post_id} not found in database")
                await process_user_input(
                    bot, message,
                    text="❌ Пост не найден",
                    reply_markup=get_back_to_menu_keyboard(),
                    state=state
                )
                await state.clear()
                return
            
            # Обновляем текст в БД
            post.text = new_text
            await session.commit()
            
            # Пытаемся обновить пост в Telegram, если это возможно
            telegram_updated = False
            if post.status == 'published' and post.telegram_message_id:
                try:
                    from datetime import datetime, timedelta
                    now = datetime.now()
                    if isinstance(post.published_at, str):
                        published_at = datetime.fromisoformat(post.published_at.replace('Z', '+00:00'))
                    else:
                        published_at = post.published_at
                    
                    # Проверяем, прошло ли менее 48 часов
                    if now - published_at.replace(tzinfo=None) < timedelta(hours=48):
                        # Создаем reply_markup если есть кнопки
                        reply_markup = None
                        if post.buttons_json:
                            try:
                                import json
                                buttons_data = json.loads(post.buttons_json)
                                if buttons_data:
                                    keyboard_buttons = []
                                    for button_data in buttons_data:
                                        keyboard_buttons.append([InlineKeyboardButton(
                                            text=button_data.get('text', 'Кнопка'),
                                            url=button_data.get('url', '#')
                                        )])
                                    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                                    logger.info(f"🔍 HANDLE_TEXT_EDIT: Post {post_id} has {len(buttons_data)} button(s) for Telegram update")
                            except Exception as e:
                                logger.error(f"❌ HANDLE_TEXT_EDIT: Failed to parse buttons for post {post_id}: {e}")
                        
                        # Обновляем сообщение в Telegram
                        if post.media_type and post.media_file_id:
                            # Для медиа обновляем подпись
                            await bot.edit_message_caption(
                                chat_id=post.chat_id,
                                message_id=post.telegram_message_id,
                                caption=new_text,
                                reply_markup=reply_markup
                            )
                        else:
                            # Для текстовых сообщений обновляем текст
                            await bot.edit_message_text(
                                chat_id=post.chat_id,
                                message_id=post.telegram_message_id,
                                text=new_text,
                                reply_markup=reply_markup
                            )
                        telegram_updated = True
                        logger.info(f"Updated post {post_id} in Telegram")
                except Exception as e:
                    logger.warning(f"Failed to update post {post_id} in Telegram: {e}")
            
            # Показываем результат
            if telegram_updated:
                success_text = (f"✅ <b>Пост #{post_id} успешно обновлен!</b>\n\n"
                               f"Текст обновлен в базе данных и в Telegram.")
                logger.info(f"✅ HANDLE_TEXT_EDIT: Post {post_id} updated in both DB and Telegram")
            else:
                success_text = (f"✅ <b>Пост #{post_id} обновлен в базе данных!</b>\n\n"
                               f"Текст обновлен в БД. Обновление в Telegram невозможно "
                               f"(пост старше 48 часов или не опубликован).")
                logger.info(f"✅ HANDLE_TEXT_EDIT: Post {post_id} updated in DB only")
            
            # Создаем клавиатуру с кнопкой "Назад к посту"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К посту", callback_data=f"post_view:{post_id}")]
            ])
            
            await process_user_input(
                bot, message,
                text=success_text,
                reply_markup=keyboard,
                parse_mode="HTML",
                state=state
            )
            
            logger.info(f"✅ HANDLE_TEXT_EDIT: Post {post_id} text updated by admin {message.from_user.id}")
            
    except Exception as e:
        logger.error(f"❌ HANDLE_TEXT_EDIT: Error editing post {post_id}: {e}")
        await process_user_input(
            bot, message,
            text="❌ Ошибка при редактировании поста. Попробуйте еще раз.",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
    
    logger.info(f"🏁 HANDLE_TEXT_EDIT: Text edit processing completed")
    await state.clear()


def register(dp: Dispatcher, bot: Bot, async_session_local):
    """Регистрация обработчиков админ панели"""
    
    # Проверяем тип async_session_local
    from sqlalchemy.ext.asyncio import async_sessionmaker
    if not isinstance(async_session_local, async_sessionmaker):
        logger.error(f"❌ ERROR: async_session_local is not async_sessionmaker, got {type(async_session_local)}")
        return
    
    # Вспомогательные функции для создания обёрток
    def make_antispam_handler(func):
        async def wrapper(callback: CallbackQuery, state: FSMContext, bot: Bot):
            await func(callback, state, bot, async_session_local)
        return wrapper
    
    def make_antispam_message_handler(func):
        async def wrapper(message: Message, state: FSMContext, bot: Bot):
            await func(message, state, bot, async_session_local)
        return wrapper
    
    def make_antimat_handler(func):
        async def wrapper(callback: CallbackQuery, state: FSMContext, bot: Bot):
            await func(callback, state, bot, async_session_local)
        return wrapper
    
    def make_antimat_message_handler(func):
        async def wrapper(message: Message, state: FSMContext, bot: Bot):
            await func(message, state, bot, async_session_local)
        return wrapper
    
    # Создаем обертки для функций с async_session_local
    async def admin_command_wrapper(message, state):
        return await admin_command_handler(message, state, async_session_local, bot)
    
    # Команда /admin
    dp.message.register(
        admin_command_wrapper,
        Command("admin"),
        IsAdmin()
    )
    
    # Создаем обертки для callback функций
    async def show_main_menu_wrapper(query, state):
        return await show_main_menu_from_callback(query, state, async_session_local, bot)
    
    async def handle_new_post_wrapper(query, state):
        return await handle_new_post(query, state, async_session_local, bot)
    
    async def handle_posts_list_wrapper(query, state):
        return await handle_posts_list(query, state, async_session_local, bot)
    
    async def handle_posts_pagination_wrapper(query, state):
        return await handle_posts_pagination(query, state, async_session_local, bot)
    
    async def handle_post_view_wrapper(query, state):
        return await handle_post_view(query, state, async_session_local, bot)
    
    async def handle_antimat_wrapper(query, state):
        return await handle_antimat(query, state, async_session_local, bot)
    
    async def handle_antispam_wrapper(query, state):
        return await handle_antispam(query, state, async_session_local, bot)
    
    async def handle_settings_wrapper(query, state):
        return await handle_settings(query, state, async_session_local, bot)
    
    async def handle_status_wrapper(query, state):
        return await handle_status(query, state, async_session_local, bot)

    async def handle_stats_detailed_wrapper(query, state):
        return await handle_stats_detailed(query, state, async_session_local, bot)

    async def handle_stats_overall_wrapper(query, state):
        await safe_answer_callback(query)
        try:
            # Определяем целевой чат для статистики
            chat_id = query.message.chat.id
            if chat_id > 0:
                from models.base import MessageLog
                async with async_session_local() as session:
                    result = await session.execute(
                        select(MessageLog.chat_id, func.count(MessageLog.id))
                        .where(MessageLog.chat_id < 0)
                        .group_by(MessageLog.chat_id)
                        .order_by(func.count(MessageLog.id).desc())
                        .limit(1)
                    )
                    row = result.first()
                    if row:
                        chat_id = row[0]
                    else:
                        await edit_message(query, "📊 Нет данных по группам.", get_stats_menu_keyboard(), "HTML", bot)
                        return
            from plugins.stats_plugin import handle_stats_command
            class MsgWrap:
                def __init__(self, chat_id, from_user_id):
                    from types import SimpleNamespace
                    self.chat = SimpleNamespace(id=chat_id)
                    self.from_user = SimpleNamespace(id=from_user_id)
                async def answer(self, text, parse_mode=None):
                    # Показываем отчёт с клавиатурой возврата в раздел статистики
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:stats_detailed")]])
                    await edit_message(query, text, kb, parse_mode or "HTML", bot)
                async def delete(self):
                    # Заглушка для совместимости с delete_command_message
                    pass
            msg = MsgWrap(chat_id, query.from_user.id)
            await handle_stats_command(message=msg, bot=bot, async_session_local=async_session_local)
        except Exception as e:
            logger.error(f"Failed to build overall stats: {e}")
            await edit_message(query, "❌ Не удалось загрузить общую статистику.", get_stats_menu_keyboard(), "HTML", bot)

    async def handle_stats_invites_wrapper(query, state):
        await safe_answer_callback(query)
        try:
            from plugins.invite_stats import show_invite_page
            await show_invite_page(query, bot, async_session_local)
        except Exception as e:
            logger.error(f"Error loading invite stats: {e}")
            text = (
                "🔗 <b>Инвайт ссылки</b>\n\n"
                "❌ Ошибка загрузки статистики инвайт-ссылок."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:stats_detailed")]])
            await edit_message(query, text, kb, "HTML", bot)
    
    async def handle_post_delete_wrapper(query, state):
        return await handle_post_delete(query, state, async_session_local, bot)
    
    async def handle_post_publish_wrapper(query, state):
        return await handle_post_publish(query, state, async_session_local, bot)
    
    async def handle_posts_type_selection_wrapper(query, state):
        return await handle_posts_type_selection(query, state, async_session_local, bot)
    
    async def handle_post_edit_wrapper(query, state):
        return await handle_post_edit(query, state, async_session_local, bot)
    
    async def handle_post_buttons_wrapper(query, state):
        return await handle_post_buttons(query, state, async_session_local, bot)
    
    async def handle_post_add_media_wrapper(query, state):
        return await handle_post_add_media(query, state, async_session_local, bot)
    
    async def handle_post_replace_media_wrapper(query, state):
        return await handle_post_replace_media(query, state, async_session_local, bot)
    
    async def handle_post_remove_media_wrapper(query, state):
        return await handle_post_remove_media(query, state, async_session_local, bot)
    
    async def handle_post_confirm_remove_media_wrapper(query, state):
        return await handle_post_confirm_remove_media(query, state, async_session_local, bot)
    
    
    async def handle_text_edit_wrapper(message, state):
        return await handle_text_edit(message, state, async_session_local, bot)
    
    async def handle_time_edit_wrapper(query, state):
        return await handle_time_edit(query, state, async_session_local, bot)
    
    async def handle_time_edit_input_wrapper(message, state):
        return await handle_time_edit_input(message, state, async_session_local, bot)
    
    # Главное меню
    dp.callback_query.register(
        show_main_menu_wrapper,
        lambda c: c.data == "admin:main_menu"
    )
    
    # Создание нового поста
    dp.callback_query.register(
        handle_new_post_wrapper,
        lambda c: c.data == "admin:new_post"
    )
    
    # Список постов
    dp.callback_query.register(
        handle_posts_list_wrapper,
        lambda c: c.data == "admin:posts"
    )
    
    # Выбор типа постов
    dp.callback_query.register(
        handle_posts_type_selection_wrapper,
        lambda c: c.data.startswith("posts_list:")
    )
    
    # Пагинация постов
    dp.callback_query.register(
        handle_posts_pagination_wrapper,
        lambda c: c.data.startswith("posts_page:")
    )
    
    # Просмотр поста
    dp.callback_query.register(
        handle_post_view_wrapper,
        lambda c: c.data.startswith("post_view:")
    )
    
    # Удаление поста
    dp.callback_query.register(
        handle_post_delete_wrapper,
        lambda c: c.data.startswith("post_delete:")
    )
    
    # Публикация поста
    dp.callback_query.register(
        handle_post_publish_wrapper,
        lambda c: c.data.startswith("post_publish:")
    )
    
    # Редактирование поста
    dp.callback_query.register(
        handle_post_edit_wrapper,
        lambda c: c.data.startswith("post_edit:") and not c.data.startswith("post_edit_time:")
    )
    
    # Изменение времени поста
    dp.callback_query.register(
        handle_time_edit_wrapper,
        lambda c: c.data.startswith("post_edit_time:")
    )
    
    # Управление кнопками поста (только для post_buttons:{id}, не для post_buttons:add)
    dp.callback_query.register(
        handle_post_buttons_wrapper,
        lambda c: c.data.startswith("post_buttons:") and c.data.split(":")[1].isdigit()
    )
    
    # Управление медиа постов
    dp.callback_query.register(
        handle_post_add_media_wrapper,
        lambda c: c.data.startswith("post_add_media:")
    )
    
    dp.callback_query.register(
        handle_post_replace_media_wrapper,
        lambda c: c.data.startswith("post_replace_media:")
    )
    
    dp.callback_query.register(
        handle_post_remove_media_wrapper,
        lambda c: c.data.startswith("post_remove_media:")
    )
    
    dp.callback_query.register(
        handle_post_confirm_remove_media_wrapper,
        lambda c: c.data.startswith("post_confirm_remove_media:")
    )
    
    
    # Другие функции
    dp.callback_query.register(
        handle_antimat_wrapper,
        lambda c: c.data == "admin:antimat"
    )
    
    dp.callback_query.register(
        handle_antispam_wrapper,
        lambda c: c.data == "admin:antispam"
    )
    
    dp.callback_query.register(
        handle_settings_wrapper,
        lambda c: c.data == "admin:settings"
    )
    
    dp.callback_query.register(
        handle_status_wrapper,
        lambda c: c.data == "admin:status"
    )

    dp.callback_query.register(
        handle_stats_detailed_wrapper,
        lambda c: c.data == "admin:stats_detailed"
    )

    dp.callback_query.register(
        handle_stats_overall_wrapper,
        lambda c: c.data == "admin:stats_overall"
    )

    dp.callback_query.register(
        handle_stats_invites_wrapper,
        lambda c: c.data == "admin:stats_invites"
    )
    
    # Создаем обертки для обработчиков триггеров
    async def show_triggers_menu_wrapper(query, state):
        return await show_triggers_menu(query, state, async_session_local, bot)
    
    async def handle_trigger_add_wrapper(query, state):
        return await handle_trigger_add(query, state, async_session_local, bot)
    
    async def handle_trigger_toggle_wrapper(query, state):
        return await handle_trigger_toggle(query, state, async_session_local, bot)
    
    async def handle_trigger_delete_wrapper(query, state):
        return await handle_trigger_delete(query, state, async_session_local, bot)
    
    async def handle_triggers_pagination_wrapper(query, state):
        return await handle_triggers_pagination(query, state, async_session_local, bot)
    
    async def handle_trigger_text_input_wrapper(message, state):
        return await handle_trigger_text_input(message, state, async_session_local, bot)
    
    async def handle_trigger_response_input_wrapper(message, state):
        return await handle_response_text_input(message, state, async_session_local, bot)
    
    # Регистрируем обработчики триггеров
    dp.callback_query.register(
        show_triggers_menu_wrapper,
        lambda c: c.data == "admin:triggers"
    )
    
    dp.callback_query.register(
        handle_trigger_add_wrapper,
        lambda c: c.data == "trigger_add"
    )
    
    dp.callback_query.register(
        handle_trigger_toggle_wrapper,
        lambda c: c.data.startswith("trigger_toggle:")
    )
    
    dp.callback_query.register(
        handle_trigger_delete_wrapper,
        lambda c: c.data.startswith("trigger_delete:")
    )
    
    dp.callback_query.register(
        handle_triggers_pagination_wrapper,
        lambda c: c.data.startswith("triggers_page:")
    )
    
    # Обработчики текстовых сообщений для триггеров
    dp.message.register(
        handle_trigger_text_input_wrapper,
        TriggerStates.waiting_trigger_text,
        IsAdmin()
    )
    
    dp.message.register(
        handle_trigger_response_input_wrapper,
        TriggerStates.waiting_response_text,
        IsAdmin()
    )
    
    # Создаем обертки для обработчиков управления администраторами
    async def handle_admin_management_wrapper(query, state):
        from .admin_management import handle_admin_management
        return await handle_admin_management(query, state, async_session_local, bot)
    
    async def handle_admin_add_wrapper(query, state):
        from .admin_management import handle_admin_add
        return await handle_admin_add(query, state, async_session_local, bot)
    
    async def handle_admin_list_wrapper(query, state):
        from .admin_management import handle_admin_list
        return await handle_admin_list(query, state, async_session_local, bot)
    
    async def handle_admin_list_pagination_wrapper(query, state):
        from .admin_management import handle_admin_list_pagination
        return await handle_admin_list_pagination(query, state, async_session_local, bot)
    
    async def handle_admin_view_wrapper(query, state):
        from .admin_management import handle_admin_view
        return await handle_admin_view(query, state, async_session_local, bot)
    
    async def handle_admin_delete_wrapper(query, state):
        from .admin_management import handle_admin_delete
        return await handle_admin_delete(query, state, async_session_local, bot)
    
    async def handle_role_selection_wrapper(query, state):
        from .admin_management import handle_role_selection
        return await handle_role_selection(query, state, async_session_local, bot)
    
    async def handle_admin_id_input_wrapper(message, state):
        from .admin_management import handle_admin_id_input
        return await handle_admin_id_input(message, state, async_session_local, bot)
    
    # Регистрируем обработчики управления администраторами
    dp.callback_query.register(
        handle_admin_management_wrapper,
        lambda c: c.data == "settings:admins"
    )
    
    dp.callback_query.register(
        handle_admin_add_wrapper,
        lambda c: c.data == "admin_management:add"
    )
    
    dp.callback_query.register(
        handle_admin_list_wrapper,
        lambda c: c.data == "admin_management:list"
    )
    
    dp.callback_query.register(
        handle_admin_list_pagination_wrapper,
        lambda c: c.data.startswith("admin_list_page:")
    )
    
    dp.callback_query.register(
        handle_admin_view_wrapper,
        lambda c: c.data.startswith("admin_view:")
    )
    
    dp.callback_query.register(
        handle_admin_delete_wrapper,
        lambda c: c.data.startswith("admin_delete:")
    )
    
    dp.callback_query.register(
        handle_role_selection_wrapper,
        lambda c: c.data.startswith("admin_role:")
    )
    
    # Обработчик ввода ID администратора
    dp.message.register(
        handle_admin_id_input_wrapper,
        AdminManagementStates.WAITING_ADMIN_ID,
        IsAdmin()
    )
    
    # Создаем обертки для обработчиков редактора постов
    async def handle_topic_selection_wrapper(query, state):
        return await handle_topic_selection(query, state, async_session_local, bot)
    
    async def handle_time_selection_wrapper(query, state):
        return await handle_time_selection(query, state, async_session_local, bot)
    
    async def handle_media_selection_wrapper(query, state):
        return await handle_media_selection(query, state, async_session_local, bot)
    
    async def confirm_post_creation_wrapper(query, state):
        return await confirm_post_creation(query, state, async_session_local, bot)
    
    async def handle_back_navigation_wrapper(query, state):
        return await handle_back_navigation(query, state, async_session_local, bot)
    
    async def handle_manual_time_input_wrapper(message, state):
        return await handle_manual_time_input(message, state, async_session_local, bot)
    
    async def handle_text_input_wrapper(message, state):
        return await handle_text_input(message, state, async_session_local, bot)
    
    async def handle_media_input_wrapper(message, state):
        return await handle_media_input(message, state, async_session_local, bot)
    
    async def handle_media_input_for_existing_post_wrapper(message, state):
        from .post_editor import handle_media_input_for_existing_post
        return await handle_media_input_for_existing_post(message, state, async_session_local, bot)
    
    # Обработчики редактора постов
    dp.callback_query.register(
        handle_topic_selection_wrapper,
        lambda c: c.data.startswith("post_editor:topic:")
    )
    
    dp.callback_query.register(
        handle_time_selection_wrapper,
        lambda c: c.data.startswith("post_editor:time:")
    )
    
    dp.callback_query.register(
        handle_media_selection_wrapper,
        lambda c: c.data.startswith("post_editor:media:")
    )
    
    dp.callback_query.register(
        confirm_post_creation_wrapper,
        lambda c: c.data == "post_editor:confirm"
    )
    
    dp.callback_query.register(
        handle_back_navigation_wrapper,
        lambda c: c.data.startswith("post_editor:back")
    )
    
    # Обработчики ввода текста и медиа
    dp.message.register(
        handle_manual_time_input_wrapper,
        PostEditorStates.CHOOSE_TIME,
        IsAdmin()
    )
    
    dp.message.register(
        handle_text_input_wrapper,
        PostEditorStates.WAITING_TEXT,
        IsAdmin()
    )
    
    dp.message.register(
        handle_media_input_wrapper,
        PostEditorStates.WAITING_MEDIA,
        IsAdmin()
    )
    
    # Обработчик медиа-ввода для существующих постов
    dp.message.register(
        handle_media_input_for_existing_post_wrapper,
        PostEditorStates.MEDIA_INPUT,
        IsAdmin()
    )
    
    # Обработчик редактирования текста
    dp.message.register(
        handle_text_edit_wrapper,
        PostEditorStates.EDITING_TEXT,
        IsAdmin()
    )
    
    # Обработчик редактирования времени
    dp.message.register(
        handle_time_edit_input_wrapper,
        PostEditorStates.EDITING_TIME,
        IsAdmin()
    )
    
    # Обработчики управления кнопками
    
    async def handle_buttons_add_wrapper(query, state):
        return await handle_existing_post_button_add(query, state, async_session_local, bot)
    
    async def handle_button_delete_wrapper(query, state):
        return await handle_button_delete(query, state, async_session_local, bot)
    
    async def handle_button_text_input_wrapper(message, state):
        return await handle_button_text_input(message, state, async_session_local, bot)
    
    async def handle_button_url_input_wrapper(message, state):
        return await handle_button_url_input(message, state, async_session_local, bot)
    
    # Обработчик для кнопок-заглушек (noop)
    async def handle_noop_wrapper(query, state):
        await safe_answer_callback(query)
    
    # Обработчик для кнопок в планировщике поста
    async def handle_post_editor_buttons_wrapper(query, state):
        logger.info(f"🔍 HANDLE_POST_EDITOR_BUTTONS: Starting post editor button handling")
        logger.info(f"🔍 HANDLE_POST_EDITOR_BUTTONS: Callback data: '{query.data}'")
        logger.info(f"🔍 HANDLE_POST_EDITOR_BUTTONS: User ID: {query.from_user.id}, Chat ID: {query.message.chat.id}")
        return await show_buttons_settings(query, state, async_session_local, bot)
    
    # Обработчик для добавления кнопки в планировщике поста
    async def handle_post_editor_add_button_wrapper(query, state):
        logger.info(f"🔍 HANDLE_POST_EDITOR_ADD_BUTTON: Starting add button in post editor")
        logger.info(f"🔍 HANDLE_POST_EDITOR_ADD_BUTTON: Callback data: '{query.data}'")
        return await handle_buttons_add(query, state, async_session_local, bot)
    
    # Регистрация обработчиков кнопок
    dp.callback_query.register(
        handle_post_editor_buttons_wrapper,
        lambda c: c.data == "post_editor:buttons"
    )
    
    dp.callback_query.register(
        handle_post_editor_add_button_wrapper,
        lambda c: c.data == "post_editor:add_button"
    )
    
    dp.callback_query.register(
        handle_buttons_add_wrapper,
        lambda c: c.data == "post_buttons:add"
    )
    
    dp.callback_query.register(
        handle_button_delete_wrapper,
        lambda c: c.data.startswith("post_button:delete:")
    )
    
    dp.callback_query.register(
        handle_noop_wrapper,
        lambda c: c.data == "noop"
    )
    
    # Обработчики текстовых сообщений для кнопок
    dp.message.register(
        handle_button_text_input_wrapper,
        PostEditorStates.WAITING_BUTTON_TEXT,
        IsAdmin()
    )
    
    dp.message.register(
        handle_button_url_input_wrapper,
        PostEditorStates.WAITING_BUTTON_URL,
        IsAdmin()
    )
    
    # Регистрация обработчиков антиспама
    from .antispam_settings import (
        AntispamSettingsStates,
        handle_antispam_toggle,
        handle_antispam_edit_limit,
        handle_antispam_edit_window,
        handle_limit_input,
        handle_window_input,
        show_antispam_settings
    )
    
    # Обработчики callback query для антиспама
    dp.callback_query.register(
        make_antispam_handler(handle_antispam_toggle),
        lambda c: c.data == "antispam:toggle",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antispam_handler(handle_antispam_edit_limit),
        lambda c: c.data == "antispam:edit_limit",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antispam_handler(handle_antispam_edit_window),
        lambda c: c.data == "antispam:edit_window",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antispam_handler(show_antispam_settings),
        lambda c: c.data == "antispam:view",
        IsAdmin()
    )
    
    # Обработчики текстовых сообщений для антиспама
    dp.message.register(
        make_antispam_message_handler(handle_limit_input),
        AntispamSettingsStates.WAITING_LIMIT,
        IsAdmin()
    )
    
    dp.message.register(
        make_antispam_message_handler(handle_window_input),
        AntispamSettingsStates.WAITING_WINDOW,
        IsAdmin()
    )
    
    # Регистрация обработчиков антимата
    from .antimat_settings import (
        AntimatSettingsStates,
        handle_antimat_toggle,
        handle_antimat_toggle_warnings,
        handle_antimat_add_word,
        handle_antimat_remove_word,
        handle_antimat_add_link,
        handle_antimat_remove_link,
        handle_add_word_input,
        handle_add_link_input,
        handle_remove_word_callback,
        handle_remove_link_callback,
        handle_antimat_clear_all,
        show_antimat_settings,
        show_antimat_words,
        show_antimat_links,
        handle_manage_words,
        handle_manage_links,
        handle_remove_word_inline,
        handle_remove_link_inline,
        handle_clear_words,
        handle_clear_links,
        handle_words_pagination,
        handle_links_pagination
    )
    
    # Обработчики callback query для антимата
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_toggle),
        lambda c: c.data == "antimat:toggle",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_toggle_warnings),
        lambda c: c.data == "antimat:toggle_warnings",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_add_word),
        lambda c: c.data == "antimat:add_word",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_remove_word),
        lambda c: c.data == "antimat:remove_word",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_add_link),
        lambda c: c.data == "antimat:add_link",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_remove_link),
        lambda c: c.data == "antimat:remove_link",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_remove_word_callback),
        lambda c: c.data.startswith("antimat:remove_word:"),
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_remove_link_callback),
        lambda c: c.data.startswith("antimat:remove_link:"),
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_antimat_clear_all),
        lambda c: c.data == "antimat:clear_all",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_manage_words),
        lambda c: c.data == "antimat:manage_words",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_manage_links),
        lambda c: c.data == "antimat:manage_links",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_remove_word_inline),
        lambda c: c.data.startswith("antimat:remove_word_inline:"),
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_remove_link_inline),
        lambda c: c.data.startswith("antimat:remove_link_inline:"),
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_clear_words),
        lambda c: c.data == "antimat:clear_words",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_clear_links),
        lambda c: c.data == "antimat:clear_links",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(show_antimat_settings),
        lambda c: c.data == "antimat:view",
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_words_pagination),
        lambda c: c.data.startswith("antimat:words_page:"),
        IsAdmin()
    )
    
    dp.callback_query.register(
        make_antimat_handler(handle_links_pagination),
        lambda c: c.data.startswith("antimat:links_page:"),
        IsAdmin()
    )
    
    # Обработчики текстовых сообщений для антимата
    dp.message.register(
        make_antimat_message_handler(handle_add_word_input),
        AntimatSettingsStates.ADD_WORD,
        IsAdmin()
    )
    
    dp.message.register(
        make_antimat_message_handler(handle_add_link_input),
        AntimatSettingsStates.ADD_LINK,
        IsAdmin()
    )
    
    logger.info("✅ Admin panel handlers registered")
