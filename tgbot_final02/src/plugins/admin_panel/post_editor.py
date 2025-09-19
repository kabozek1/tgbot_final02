"""
FSM для создания и редактирования постов
"""

import logging
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select

from models.base import ChatInfo, ScheduledPost
from .keyboards import (
    get_topic_selection_keyboard,
    get_time_selection_keyboard,
    get_media_selection_keyboard,
    get_confirm_keyboard,
    get_back_to_menu_keyboard,
    get_buttons_settings_keyboard
)
from .message_utils import edit_message, send_message, process_user_input

logger = logging.getLogger(__name__)


async def safe_answer_callback(query: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await query.answer()
    except Exception as e:
        logger.debug(f"Failed to answer callback query: {e}")




class PostEditorStates(StatesGroup):
    """Состояния для создания поста"""
    CHOOSE_TOPIC = State()
    CHOOSE_TIME = State()
    WAITING_TEXT = State()
    WAITING_MEDIA = State()
    MEDIA_INPUT = State()  # Для добавления/замены медиа в существующих постах
    BUTTONS_SETTINGS = State()
    WAITING_BUTTON_TEXT = State()
    WAITING_BUTTON_URL = State()
    CONFIRM = State()
    EDITING_TEXT = State()
    EDITING_TIME = State()  # Для редактирования времени существующего поста


async def start_post_creation(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Начать создание нового поста"""
    await safe_answer_callback(query)
    
    # Очищаем состояние перед началом создания нового поста
    await state.clear()
    logger.debug(f"🧹 START_POST_CREATION: Cleared FSM state before starting new post creation")
    
    # Получаем список топиков только из групповых чатов
    async with async_session_local() as session:
        result = await session.execute(
            select(ChatInfo.chat_id, ChatInfo.topic_id, ChatInfo.topic_name).distinct()
        )
        topics = []
        seen_combinations = set()  # Для избежания дублирования
        
        for row in result:
            # Фильтруем только групповые чаты (chat_id < 0)
            if row.chat_id >= 0:
                continue  # Пропускаем личные чаты
                
            # Создаем уникальный ключ для комбинации chat_id + topic_id
            combination_key = (row.chat_id, row.topic_id)
            if combination_key not in seen_combinations:
                topics.append({
                    'chat_id': row.chat_id,
                    'topic_id': row.topic_id,
                    'topic_name': row.topic_name
                })
                seen_combinations.add(combination_key)
    
    if not topics:
        text = "❌ Не найдено ни одного топика. Отправьте сообщение в нужный топик, чтобы он появился здесь."
        # Проверяем, есть ли медиа в сообщении
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Показываем выбор топика
    keyboard = get_topic_selection_keyboard(topics)
    text = "📍 <b>Выберите топик для публикации:</b>"
    
    await edit_message(query, text, keyboard, "HTML", bot)
    
    await state.set_state(PostEditorStates.CHOOSE_TOPIC)


async def handle_topic_selection(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка выбора топика"""
    await safe_answer_callback(query)
    
    # Парсим callback_data: post_editor:topic:{topic_id}:{chat_id}
    parts = query.data.split(":")
    topic_data = parts[2]
    chat_id = int(parts[3]) if len(parts) > 3 else None
    
    if topic_data == "general":
        topic_id = None
        topic_name = "Основной чат"
    else:
        topic_id = int(topic_data)
        # Получаем название топика из БД
        async with async_session_local() as session:
            result = await session.execute(
                select(ChatInfo.topic_name).filter_by(topic_id=topic_id)
            )
            topic_name = result.scalar_one_or_none() or f"Топик {topic_id}"
    
    if not chat_id:
        text = "❌ Ошибка: не найден чат для выбранного топика"
        # Проверяем, есть ли медиа в сообщении
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Логируем информацию о выбранном топике
    logger.info(f"Selected topic: topic_id={topic_id}, topic_name={topic_name}, chat_id={chat_id}, chat_type={'group' if chat_id < 0 else 'private'}")

    # Сохраняем выбранный топик и чат
    await state.update_data(
        topic_id=topic_id,
        topic_name=topic_name,
        chat_id=chat_id
    )

    # Показываем выбор времени
    keyboard = get_time_selection_keyboard()
    text = f"⏰ <b>Выберите время публикации:</b>\n\nТопик: {topic_name}"
    
    await edit_message(query, text, keyboard, "HTML", bot)
    
    await state.set_state(PostEditorStates.CHOOSE_TIME)


async def handle_time_selection(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка выбора времени"""
    await safe_answer_callback(query)
    
    # Парсим callback_data: post_editor:time:{time_option}
    time_option = query.data.split(":")[2]
    
    if time_option == "now":
        publish_time = datetime.now()
        time_display = "Сейчас"
    elif time_option == "5min":
        publish_time = datetime.now() + timedelta(minutes=5)
        time_display = "Через 5 минут"
    elif time_option == "1hour":
        publish_time = datetime.now() + timedelta(hours=1)
        time_display = "Через 1 час"
    elif time_option == "1day":
        publish_time = datetime.now() + timedelta(days=1)
        time_display = "Через 1 день"
    elif time_option == "manual":
        # Запрашиваем ввод времени вручную
        data = await state.get_data()
        topic_name = data.get('topic_name', 'Неизвестный топик')
        
        text = (f"⏰ <b>Введите время публикации:</b>\n\n"
                f"Топик: {topic_name}\n\n"
                f"Формат: ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ ЧЧ:ММ:СС\n"
                f"Пример: 25.12.2024 15:30 или 25.12.2024 15:30:45")
        
        # Проверяем, есть ли медиа в сообщении
        has_media = (query.message.photo or query.message.video or query.message.document or 
                    query.message.audio or query.message.voice or query.message.video_note)
        
        # Используем универсальную функцию для автоматического определения типа сообщения
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        
        # Сохраняем message_id для последующего редактирования
        await state.update_data(last_message_id=query.message.message_id)
        
        await state.set_state(PostEditorStates.CHOOSE_TIME)
        return
    else:
        await query.answer("❌ Неверный выбор времени", show_alert=True)
        return
    
    # Сохраняем время публикации
    await state.update_data(
        publish_time=publish_time,
        time_display=time_display
    )
    
    # Переходим к вводу текста
    data = await state.get_data()
    topic_name = data.get('topic_name', 'Неизвестный топик')
    
    text = (f"📝 <b>Введите текст поста:</b>\n\n"
            f"Топик: {topic_name}\n"
            f"Время: {time_display}")
    
    logger.debug(f"✏️ HANDLE_TIME_SELECTION: Editing message to show text input prompt")
    await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
    
    # Сохраняем message_id для последующего удаления
    logger.debug(f"💾 HANDLE_TIME_SELECTION: Saving message_id {query.message.message_id} for future deletion")
    await state.update_data(last_message_id=query.message.message_id)
    
    logger.debug(f"🔄 HANDLE_TIME_SELECTION: Setting state to WAITING_TEXT")
    await state.set_state(PostEditorStates.WAITING_TEXT)
    logger.debug(f"🏁 HANDLE_TIME_SELECTION: Time selection processing completed")


async def handle_manual_time_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода времени вручную"""
    logger.info(f"Manual time input: {message.text}")
    try:
        # Парсим время в формате ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ ЧЧ:ММ:СС
        time_str = message.text.strip()
        publish_time = None
        
        # Сначала пробуем формат с секундами
        try:
            publish_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            # Если не получилось, пробуем формат без секунд (автоматически добавляем :00)
            publish_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
            # Обновляем time_str для отображения с секундами
            time_str = publish_time.strftime("%d.%m.%Y %H:%M:%S")
        
        # Проверяем, что время в будущем
        if publish_time <= datetime.now():
            await process_user_input(
                bot, message,
                text="❌ Время публикации должно быть в будущем. Попробуйте еще раз:",
                reply_markup=get_back_to_menu_keyboard(),
                state=state
            )
            return
        
        # Сохраняем время
        await state.update_data(
            publish_time=publish_time,
            time_display=time_str
        )
        
        # Переходим к вводу текста
        data = await state.get_data()
        topic_name = data.get('topic_name', 'Неизвестный топик')
        
        # Сначала меняем состояние на WAITING_TEXT
        await state.set_state(PostEditorStates.WAITING_TEXT)
        
        # Затем используем process_user_input для редактирования сообщения
        await process_user_input(
            bot, message,
            text=f"📝 <b>Введите текст поста:</b>\n\n"
                 f"Топик: {topic_name}\n"
                 f"Время: {time_str}",
            reply_markup=get_back_to_menu_keyboard(),
            parse_mode="HTML",
            state=state
        )
        
    except ValueError:
        await process_user_input(
            bot, message,
            text="❌ Неверный формат времени. Используйте формат:\n"
                 "• ДД.ММ.ГГГГ ЧЧ:ММ (секунды будут :00)\n"
                 "• ДД.ММ.ГГГГ ЧЧ:ММ:СС (с указанием секунд)\n\n"
                 "Примеры:\n"
                 "• 25.12.2024 15:30\n"
                 "• 25.12.2024 15:30:17",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )


async def handle_text_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода текста поста"""
    # Processing text input
    
    text = message.text.strip() if message.text else ""
    
    if not text:
        # Empty text provided
        await process_user_input(
            bot, message,
            text="❌ Текст поста не может быть пустым. Введите текст:",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
        return
    
    # Сохраняем текст
    await state.update_data(text=text)
    
    # Показываем выбор медиа
    data = await state.get_data()
    topic_name = data.get('topic_name', 'Неизвестный топик')
    time_display = data.get('time_display', 'Не указано')
    
    keyboard = get_media_selection_keyboard()
    await process_user_input(
        bot, message,
        text=f"🖼️ <b>Добавить медиа (опционально):</b>\n\n"
             f"Топик: {topic_name}\n"
             f"Время: {time_display}\n"
             f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}",
        reply_markup=keyboard,
        parse_mode="HTML",
        state=state
    )
    
    await state.set_state(PostEditorStates.WAITING_MEDIA)


async def handle_media_selection(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка выбора медиа"""
    await safe_answer_callback(query)
    
    # Парсим callback_data: post_editor:media:{action}
    action = query.data.split(":")[2]
    
    if action == "skip":
        # Пропускаем медиа
        await state.update_data(media_type=None, media_file_id=None)
        await show_buttons_settings(query, state, async_session_local, bot)
    elif action == "add":
        # Запрашиваем любое медиа
        data = await state.get_data()
        topic_name = data.get('topic_name', 'Неизвестный топик')
        time_display = data.get('time_display', 'Не указано')
        text = data.get('text', '')
        
        text_message = (f"📎 <b>Отправьте медиа (фото, видео, документ):</b>\n\n"
                        f"Топик: {topic_name}\n"
                        f"Время: {time_display}\n"
                        f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        await edit_message(query, text_message, get_back_to_menu_keyboard(), "HTML", bot)
        
        await state.set_state(PostEditorStates.WAITING_MEDIA)


async def handle_media_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода медиа"""
    logger.debug(f"🔄 HANDLE_MEDIA_INPUT: Starting media input processing")
    logger.debug(f"👤 HANDLE_MEDIA_INPUT: User message ID: {message.message_id}, Chat ID: {message.chat.id}")
    
    media_file_id = None
    media_type = None
    
    # Проверяем тип медиа (принимаем любой)
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
        # Photo detected
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"
        # Video detected
    elif message.document:
        media_file_id = message.document.file_id
        media_type = "document"
        # Document detected
    elif message.audio:
        media_file_id = message.audio.file_id
        media_type = "audio"
        # Audio detected
    elif message.voice:
        media_file_id = message.voice.file_id
        media_type = "voice"
        # Voice detected
    elif message.video_note:
        media_file_id = message.video_note.file_id
        media_type = "video_note"
        # Video note detected
    else:
        # Unsupported media type
        await process_user_input(
            bot, message,
            text="❌ Неподдерживаемый тип медиа. Отправьте фото, видео, документ, аудио или голосовое сообщение:",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
        return
    
    # Сохраняем медиа
    await state.update_data(
        media_type=media_type,
        media_file_id=media_file_id
    )
    
    # Показываем настройки кнопок (эта функция сама удалит сообщение пользователя)
    await show_buttons_settings_from_message(message, state, async_session_local, bot)


async def show_confirmation(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать подтверждение создания поста"""
    data = await state.get_data()
    
    topic_name = data.get('topic_name', 'Неизвестный топик')
    time_display = data.get('time_display', 'Не указано')
    text = data.get('text', '')
    media_type = data.get('media_type')
    buttons = data.get('buttons', [])
    
    # Формируем текст подтверждения
    confirm_text = f"✅ <b>Подтвердите создание поста:</b>\n\n"
    confirm_text += f"📍 Топик: {topic_name}\n"
    confirm_text += f"⏰ Время: {time_display}\n"
    confirm_text += f"📝 Текст: {text}\n"
    
    if media_type:
        media_emoji = {"photo": "📷", "video": "🎥", "document": "📄"}
        confirm_text += f"🖼️ Медиа: {media_emoji.get(media_type, '📎')} {media_type}\n"
    else:
        confirm_text += "🖼️ Медиа: Нет\n"
    
    if buttons:
        confirm_text += f"🔘 Кнопки: {len(buttons)} шт.\n"
        for i, button in enumerate(buttons, 1):
            confirm_text += f"  {i}. {button.get('text', '')}\n"
    else:
        confirm_text += "🔘 Кнопки: Нет\n"
    
    keyboard = get_confirm_keyboard()
    
    await edit_message(query, confirm_text, keyboard, "HTML", bot)
    
    await state.set_state(PostEditorStates.CONFIRM)


async def show_confirmation_from_message(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать подтверждение создания поста из сообщения"""
    logger.info(f"🔄 SHOW_CONFIRMATION_FROM_MESSAGE: Starting confirmation display")
    logger.info(f"👤 SHOW_CONFIRMATION_FROM_MESSAGE: User message ID: {message.message_id}, Chat ID: {message.chat.id}")
    
    data = await state.get_data()
    
    topic_name = data.get('topic_name', 'Неизвестный топик')
    time_display = data.get('time_display', 'Не указано')
    text = data.get('text', '')
    media_type = data.get('media_type')
    media_file_id = data.get('media_file_id')
    
    logger.info(f"📊 SHOW_CONFIRMATION_FROM_MESSAGE: Topic: {topic_name}, Time: {time_display}, Media: {media_type}")
    
    keyboard = get_confirm_keyboard()
    
    # Отправляем медиа с подписью или только текст
    if media_type and media_file_id:
        # Формируем подпись: сначала текст поста, потом детали
        caption = f"📝 {text}\n\n📍 Топик: {topic_name}\n⏰ Время: {time_display}\n\n✅ <b>Подтвердите создание поста:</b>"
        
        # Удаляем сообщение пользователя с медиа
        logger.info(f"🗑️ SHOW_CONFIRMATION_FROM_MESSAGE: Deleting user media message {message.message_id}")
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Successfully deleted user media message {message.message_id}")
        except Exception as delete_error:
            logger.warning(f"⚠️ SHOW_CONFIRMATION_FROM_MESSAGE: Failed to delete user media message: {delete_error}")
        
        # Сначала удаляем старое сообщение, если есть
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        if last_message_id:
            logger.info(f"🗑️ SHOW_CONFIRMATION_FROM_MESSAGE: Deleting previous bot message {last_message_id}")
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
                logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Successfully deleted previous bot message {last_message_id}")
            except Exception as delete_error:
                logger.warning(f"⚠️ SHOW_CONFIRMATION_FROM_MESSAGE: Failed to delete previous bot message: {delete_error}")
        
        # Отправляем медиа с подписью
        logger.info(f"📤 SHOW_CONFIRMATION_FROM_MESSAGE: Sending {media_type} with caption")
        sent_message = None
        if media_type == 'photo':
            sent_message = await bot.send_photo(
                chat_id=message.chat.id,
                photo=media_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Photo sent successfully {sent_message.message_id}")
        elif media_type == 'video':
            sent_message = await bot.send_video(
                chat_id=message.chat.id,
                video=media_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Video sent successfully {sent_message.message_id}")
        elif media_type == 'document':
            sent_message = await bot.send_document(
                chat_id=message.chat.id,
                document=media_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Document sent successfully {sent_message.message_id}")
        elif media_type == 'audio':
            sent_message = await bot.send_audio(
                chat_id=message.chat.id,
                audio=media_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Audio sent successfully {sent_message.message_id}")
        elif media_type == 'voice':
            sent_message = await bot.send_voice(
                chat_id=message.chat.id,
                voice=media_file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Voice sent successfully {sent_message.message_id}")
        elif media_type == 'video_note':
            sent_message = await bot.send_video_note(
                chat_id=message.chat.id,
                video_note=media_file_id
            )
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Video note sent successfully {sent_message.message_id}")
            # Для video_note отправляем отдельно текст
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        # Сохраняем message_id нового сообщения
        if sent_message:
            logger.info(f"💾 SHOW_CONFIRMATION_FROM_MESSAGE: Saving message_id {sent_message.message_id} in FSM state")
            await state.update_data(last_message_id=sent_message.message_id)
            logger.info(f"✅ SHOW_CONFIRMATION_FROM_MESSAGE: Successfully saved message_id {sent_message.message_id}")
        else:
            logger.warning(f"⚠️ SHOW_CONFIRMATION_FROM_MESSAGE: No message returned from media send")
    else:
        # Отправляем только текст
        logger.info(f"💬 SHOW_CONFIRMATION_FROM_MESSAGE: No media, sending text only")
        text_message = f"📝 {text}\n\n📍 Топик: {topic_name}\n⏰ Время: {time_display}\n🖼️ Медиа: Нет\n\n✅ <b>Подтвердите создание поста:</b>"
        await process_user_input(
            bot, message,
            text=text_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            state=state
        )
    
    logger.info(f"🔄 SHOW_CONFIRMATION_FROM_MESSAGE: Setting state to CONFIRM")
    await state.set_state(PostEditorStates.CONFIRM)
    logger.info(f"🏁 SHOW_CONFIRMATION_FROM_MESSAGE: Confirmation display completed")


async def confirm_post_creation(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Подтвердить создание поста"""
    await safe_answer_callback(query)
    
    data = await state.get_data()
    
    # Получаем данные поста
    topic_id = data.get('topic_id')
    topic_name = data.get('topic_name', 'Неизвестный топик')
    chat_id = data.get('chat_id')
    publish_time = data.get('publish_time')
    text = data.get('text', '')
    media_type = data.get('media_type')
    media_file_id = data.get('media_file_id')
    buttons = data.get('buttons', [])
    
    if not chat_id:
        text = "❌ Ошибка: не найден чат для публикации"
        # Проверяем, есть ли медиа в сообщении
        await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Создаем пост в БД
    try:
        # Подготавливаем кнопки для сохранения
        buttons_json = None
        if buttons:
            import json
            buttons_json = json.dumps(buttons)
        
        async with async_session_local() as session:
            new_post = ScheduledPost(
                chat_id=chat_id,
                topic_id=topic_id,
                publish_time=publish_time,
                text=text,
                media_file_id=media_file_id,
                media_type=media_type,
                buttons_json=buttons_json,
                status='pending'
            )
            session.add(new_post)
            await session.commit()
            
            post_id = new_post.id
        
        # Успешное создание
        success_text = (f"✅ <b>Пост успешно запланирован!</b>\n\n"
                       f"📍 Топик: {topic_name}\n"
                       f"⏰ Время: {data.get('time_display', 'Не указано')}\n"
                       f"🆔 ID поста: {post_id}")
        
        await edit_message(query, success_text, get_back_to_menu_keyboard(), "HTML", bot)
        
        logger.info(f"Post {post_id} scheduled by admin {query.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error creating post: {e}")
        error_text = "❌ Ошибка при создании поста. Попробуйте еще раз."
        
        await edit_message(query, error_text, get_back_to_menu_keyboard(), "HTML", bot)
    
    # Очищаем состояние
    await state.clear()


async def handle_back_navigation(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка навигации назад"""
    await safe_answer_callback(query)
    
    # Обработка возврата к настройкам кнопок (из подтверждения)
    if query.data == "post_editor:back_to_buttons":
        await show_buttons_settings(query, state, async_session_local, bot)
        return
    
    # Обработка возврата к выбору времени (из выбора медиа)
    if query.data == "post_editor:back_to_time":
        data = await state.get_data()
        topic_name = data.get('topic_name', 'Неизвестный топик')
        
        keyboard = get_time_selection_keyboard()
        text = f"⏰ <b>Выберите время публикации:</b>\n\nТопик: {topic_name}"
        
        await edit_message(query, text, keyboard, "HTML", bot)
        await state.set_state(PostEditorStates.CHOOSE_TIME)
        return
    
    current_state = await state.get_state()
    
    if current_state == PostEditorStates.CHOOSE_TIME:
        # Возврат к выбору топика
        await start_post_creation(query, state, async_session_local, bot)
    elif current_state == PostEditorStates.WAITING_MEDIA:
        # Возврат к выбору времени
        data = await state.get_data()
        topic_name = data.get('topic_name', 'Неизвестный топик')
        
        keyboard = get_time_selection_keyboard()
        text = f"⏰ <b>Выберите время публикации:</b>\n\nТопик: {topic_name}"
        
        await edit_message(query, text, keyboard, "HTML", bot)
        
        await state.set_state(PostEditorStates.CHOOSE_TIME)
    else:
        # Возврат в главное меню
        from .keyboards import get_main_menu_keyboard
        text = "🏠 <b>Главное меню админ панели</b>\n\nВыберите действие:"
        keyboard = get_main_menu_keyboard()
        
        await edit_message(query, text, keyboard, "HTML", bot)
        await state.clear()
        logger.info(f"🧹 HANDLE_BACK_NAVIGATION: Cleared FSM state when returning to main menu")


# ===== ФУНКЦИИ УПРАВЛЕНИЯ КНОПКАМИ =====

async def show_buttons_settings(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать настройки кнопок поста"""
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Starting button settings display")
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Callback data: '{query.data}'")
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: User ID: {query.from_user.id}, Chat ID: {query.message.chat.id}")
    
    data = await state.get_data()
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: FSM state data: {data}")
    
    buttons = data.get('buttons', [])
    editing_post_id = data.get('editing_post_id')
    
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Buttons count: {len(buttons)}")
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Editing post ID: {editing_post_id}")
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Buttons data: {buttons}")
    
    text = f"⚙️ <b>Настройки кнопок поста</b>\n\n"
    text += f"📊 Кнопок добавлено: {len(buttons)}\n\n"
    
    if buttons:
        text += "Добавленные кнопки:\n"
        for i, button in enumerate(buttons, 1):
            text += f"{i}. {button.get('text', '')}\n"
        text += "\n"
    
    text += "Выберите действие:"
    
    keyboard = get_buttons_settings_keyboard(buttons, editing_post_id)
    logger.debug(f"🔍 SHOW_BUTTONS_SETTINGS: Generated keyboard with post_id: {editing_post_id}")
    
    await edit_message(query, text, keyboard, "HTML", bot)
    await state.set_state(PostEditorStates.BUTTONS_SETTINGS)
    logger.debug(f"✅ SHOW_BUTTONS_SETTINGS: Button settings displayed successfully")


async def show_buttons_settings_from_message(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Показать настройки кнопок поста из сообщения"""
    data = await state.get_data()
    buttons = data.get('buttons', [])
    editing_post_id = data.get('editing_post_id')
    
    text = f"⚙️ <b>Настройки кнопок поста</b>\n\n"
    text += f"📊 Кнопок добавлено: {len(buttons)}\n\n"
    
    if buttons:
        text += "Добавленные кнопки:\n"
        for i, button in enumerate(buttons, 1):
            text += f"{i}. {button.get('text', '')}\n"
        text += "\n"
    
    text += "Выберите действие:"
    
    keyboard = get_buttons_settings_keyboard(buttons, editing_post_id)
    await process_user_input(bot, message, text, keyboard, "HTML", state)
    await state.set_state(PostEditorStates.BUTTONS_SETTINGS)


async def handle_buttons_add(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка добавления кнопки"""
    await safe_answer_callback(query)
    
    text = "📝 <b>Добавление кнопки</b>\n\nВведите название кнопки:"
    keyboard = get_back_to_menu_keyboard()
    
    # Сохраняем message_id для последующего редактирования
    current_message_id = await edit_message(query, text, keyboard, "HTML", bot)
    await state.update_data(last_message_id=current_message_id)
    
    await state.set_state(PostEditorStates.WAITING_BUTTON_TEXT)


async def handle_button_text_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода текста кнопки"""
    button_text = message.text.strip() if message.text else ""
    
    if not button_text:
        await process_user_input(bot, message, "❌ Название кнопки не может быть пустым. Попробуйте еще раз:", get_back_to_menu_keyboard(), "HTML", state)
        return
    
    # Сохраняем текст кнопки во временном состоянии
    await state.update_data(temp_button_text=button_text)
    
    text = f"🔗 <b>Введите ссылку для кнопки</b>\n\nНазвание: {button_text}\n\nВведите URL:"
    keyboard = get_back_to_menu_keyboard()
    
    await process_user_input(bot, message, text, keyboard, "HTML", state)
    await state.set_state(PostEditorStates.WAITING_BUTTON_URL)


async def handle_button_url_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода URL кнопки"""
    button_url = message.text.strip()
    data = await state.get_data()
    button_text = data.get('temp_button_text', '')
    editing_post_id = data.get('editing_post_id')
    
    if not button_url:
        await process_user_input(bot, message, "❌ URL не может быть пустым. Попробуйте еще раз:", get_back_to_menu_keyboard(), "HTML", state)
        return
    
    # Добавляем кнопку в список
    buttons = data.get('buttons', [])
    new_button = {
        'id': len(buttons) + 1,
        'text': button_text,
        'url': button_url
    }
    buttons.append(new_button)
    
    
    await state.update_data(buttons=buttons)
    await state.update_data(temp_button_text=None)  # Очищаем временные данные
    
    # Если редактируем существующий пост, сохраняем в БД
    if editing_post_id:
        await save_buttons_to_post(editing_post_id, buttons, async_session_local, state)
    
    text = f"✅ <b>Кнопка успешно добавлена!</b>\n\n"
    text += f"🔘 {button_text}\n"
    text += f"🔗 {button_url}\n\n"
    text += f"📊 Всего кнопок: {len(buttons)}\n\n"
    
    if buttons:
        text += "Добавленные кнопки:\n"
        for i, btn in enumerate(buttons, 1):
            text += f"{i}. {btn.get('text', '')}\n"
        text += "\n"
    
    text += "Выберите действие:"
    
    keyboard = get_buttons_settings_keyboard(buttons, editing_post_id)
    await process_user_input(bot, message, text, keyboard, "HTML", state)
    await state.set_state(PostEditorStates.BUTTONS_SETTINGS)




async def handle_button_delete(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка удаления кнопки"""
    await safe_answer_callback(query)
    
    button_id = int(query.data.split(":")[2])
    data = await state.get_data()
    buttons = data.get('buttons', [])
    editing_post_id = data.get('editing_post_id')
    
    # Удаляем кнопку
    buttons = [b for b in buttons if b.get('id') != button_id]
    await state.update_data(buttons=buttons)
    
    # Если редактируем существующий пост, сохраняем в БД
    if editing_post_id:
        await save_buttons_to_post(editing_post_id, buttons, async_session_local, state)
    
    text = f"✅ <b>Кнопка #{button_id} удалена!</b>\n\n"
    text += f"📊 Осталось кнопок: {len(buttons)}\n\n"
    
    if buttons:
        text += "Добавленные кнопки:\n"
        for i, btn in enumerate(buttons, 1):
            text += f"{i}. {btn.get('text', '')}\n"
        text += "\n"
    
    text += "Выберите действие:"
    
    keyboard = get_buttons_settings_keyboard(buttons, editing_post_id)
    await edit_message(query, text, keyboard, "HTML", bot)




async def save_buttons_to_post(post_id: int, buttons: list, async_session_local: async_sessionmaker, state: FSMContext = None):
    """Сохранить кнопки в существующий пост"""
    buttons_json = None
    if buttons:
        import json
        buttons_json = json.dumps(buttons)
    
    async with async_session_local() as session:
        result = await session.execute(
            select(ScheduledPost).filter_by(id=post_id)
        )
        post = result.scalar_one_or_none()
        
        if post:
            post.buttons_json = buttons_json
            await session.commit()
            
            # Устанавливаем флаг, что кнопки были обновлены
            if state:
                await state.update_data(buttons_updated=True)
            
            return True
        return False


async def handle_time_edit(query: CallbackQuery, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка начала редактирования времени поста"""
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
        await edit_message(query, "❌ Пост не найден", get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    if post.status != 'pending':
        await edit_message(query, "❌ Можно изменять время только у запланированных постов", get_back_to_menu_keyboard(), "HTML", bot)
        return
    
    # Показываем текущее время и просим ввести новое
    current_time = post.publish_time.strftime("%d.%m.%Y %H:%M:%S")
    text = (f"⏰ <b>Изменение времени поста</b>\n\n"
            f"Текущее время: {current_time}\n\n"
            f"Введите новое время в формате:\n"
            f"• ДД.ММ.ГГГГ ЧЧ:ММ (секунды будут :00)\n"
            f"• ДД.ММ.ГГГГ ЧЧ:ММ:СС (с указанием секунд)\n\n"
            f"Примеры:\n"
            f"• 25.12.2024 15:30\n"
            f"• 25.12.2024 15:30:17")
    
    # Редактируем сообщение и сохраняем message_id
    message_id = await edit_message(query, text, get_back_to_menu_keyboard(), "HTML", bot)
    
    # Сохраняем ID поста и message_id в состоянии
    await state.update_data(
        editing_post_id=post_id,
        last_message_id=message_id or query.message.message_id
    )
    
    await state.set_state(PostEditorStates.EDITING_TIME)


async def handle_time_edit_input(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка ввода нового времени для поста"""
    logger.info(f"Time edit input: {message.text}")
    
    data = await state.get_data()
    post_id = data.get('editing_post_id')
    
    if not post_id:
        await process_user_input(
            bot, message,
            text="❌ Ошибка: ID поста не найден",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
        await state.clear()
        return
    
    try:
        # Парсим время в формате ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ.ГГГГ ЧЧ:ММ:СС
        time_str = message.text.strip()
        publish_time = None
        
        # Сначала пробуем формат с секундами
        try:
            publish_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            # Если не получилось, пробуем формат без секунд (автоматически добавляем :00)
            publish_time = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
            # Обновляем time_str для отображения с секундами
            time_str = publish_time.strftime("%d.%m.%Y %H:%M:%S")
        
        # Проверяем, что время в будущем
        if publish_time <= datetime.now():
            await process_user_input(
                bot, message,
                text="❌ Время публикации должно быть в будущем. Попробуйте еще раз:",
                reply_markup=get_back_to_menu_keyboard(),
                state=state
            )
            return
        
        # Обновляем время в БД
        async with async_session_local() as session:
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post:
                await process_user_input(
                    bot, message,
                    text="❌ Пост не найден",
                    reply_markup=get_back_to_menu_keyboard(),
                    state=state
                )
                await state.clear()
                return
            
            post.publish_time = publish_time
            await session.commit()
        
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass  # Игнорируем ошибки удаления
        
        # Удаляем сообщение "Изменение времени поста" если есть last_message_id
        data = await state.get_data()
        last_message_id = data.get('last_message_id')
        if last_message_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=last_message_id)
            except Exception:
                pass  # Игнорируем ошибки удаления
        
        # Очищаем состояние
        await state.clear()
        
        # Импортируем и вызываем handle_post_view для показа обновленного поста
        from .main import handle_post_view
        
        # Проверяем наличие медиа в посте
        has_media = bool(post.media_type and post.media_file_id)
        
        if has_media:
            # Если есть медиа - удаляем сообщения и отправляем новое меню
            # Создаем fake query для вызова handle_post_view с отправкой нового сообщения
            fake_query = type('obj', (object,), {
                'data': f"post_view:{post_id}",
                'message': type('obj', (object,), {
                    'chat': message.chat,
                    'message_id': None,  # None означает отправку нового сообщения
                    'photo': None,
                    'video': None,
                    'document': None,
                    'audio': None,
                    'voice': None,
                    'video_note': None
                })(),
                'from_user': message.from_user,
                'id': message.message_id,
                'answer': lambda **kwargs: None
            })()
        else:
            # Если медиа нет - редактируем существующее сообщение
            fake_query = type('obj', (object,), {
                'data': f"post_view:{post_id}",
                'message': type('obj', (object,), {
                    'chat': message.chat,
                    'message_id': last_message_id or message.message_id,
                    'photo': None,
                    'video': None,
                    'document': None,
                    'audio': None,
                    'voice': None,
                    'video_note': None
                })(),
                'from_user': message.from_user,
                'id': message.message_id,
                'answer': lambda **kwargs: None
            })()
        
        # Вызываем handle_post_view для показа обновленного поста
        await handle_post_view(fake_query, state, async_session_local, bot)
        
        logger.info(f"Post {post_id} time updated to {time_str} by admin {message.from_user.id}")
        
    except ValueError:
        await process_user_input(
            bot, message,
            text="❌ Неверный формат времени. Используйте формат:\n"
                 "• ДД.ММ.ГГГГ ЧЧ:ММ (секунды будут :00)\n"
                 "• ДД.ММ.ГГГГ ЧЧ:ММ:СС (с указанием секунд)\n\n"
                 "Примеры:\n"
                 "• 25.12.2024 15:30\n"
                 "• 25.12.2024 15:30:17",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
    except Exception as e:
        logger.error(f"Error updating post time: {e}")
        await process_user_input(
            bot, message,
            text="❌ Ошибка при изменении времени поста. Попробуйте еще раз.",
            reply_markup=get_back_to_menu_keyboard(),
            state=state
        )
        await state.clear()


async def handle_media_input_for_existing_post(message: Message, state: FSMContext, async_session_local: async_sessionmaker, bot: Bot):
    """Обработка медиа-ввода для существующего поста (добавление/замена медиа)"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        post_id = data.get('editing_post_id')
        action = data.get('action')  # 'add_media' или 'replace_media'
        
        if not post_id:
            await message.answer("❌ Ошибка: не найден ID поста")
            return
        
        # Определяем тип медиа и file_id
        media_type = None
        media_file_id = None
        
        if message.photo:
            media_type = 'photo'
            media_file_id = message.photo[-1].file_id
        elif message.video:
            media_type = 'video'
            media_file_id = message.video.file_id
        elif message.document:
            media_type = 'document'
            media_file_id = message.document.file_id
        elif message.audio:
            media_type = 'audio'
            media_file_id = message.audio.file_id
        elif message.voice:
            media_type = 'voice'
            media_file_id = message.voice.file_id
        elif message.video_note:
            media_type = 'video_note'
            media_file_id = message.video_note.file_id
        else:
            await message.answer("❌ Неподдерживаемый тип медиа. Отправьте фото, видео, документ, аудио или голосовое сообщение.")
            return
        
        # Обновляем пост в БД
        async with async_session_local() as session:
            result = await session.execute(
                select(ScheduledPost).filter_by(id=post_id)
            )
            post = result.scalar_one_or_none()
            
            if not post:
                await message.answer("❌ Пост не найден")
                return
            
            # Обновляем медиа
            post.media_type = media_type
            post.media_file_id = media_file_id
            await session.commit()
            
            # Получаем данные из состояния перед очисткой
            data = await state.get_data()
            media_input_message_id = data.get('media_input_message_id')
            
            # Очищаем состояние
            await state.clear()
            
            # Удаляем сообщение пользователя с медиа
            try:
                await bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=message.message_id
                )
                logger.debug(f"Deleted user message {message.message_id} with media")
            except Exception as delete_error:
                logger.warning(f"Failed to delete user message: {delete_error}")
            
            # Удаляем сообщение "Добавление медиа к посту" или "Замена медиа в посте"
            if media_input_message_id:
                try:
                    await bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=media_input_message_id
                    )
                    logger.debug(f"Deleted media input message {media_input_message_id}")
                except Exception as delete_error:
                    logger.warning(f"Failed to delete media input message: {delete_error}")
            
            # Сразу показываем обновленный пост
            from .main import handle_post_view
            
            # Создаем fake query для вызова handle_post_view
            # Используем message_id = 0, чтобы handle_post_view не пытался удалить несуществующее сообщение
            fake_query = type('FakeQuery', (), {
                'data': f"post_view:{post_id}",
                'message': type('FakeMessage', (), {
                    'chat': message.chat,
                    'message_id': 0,  # Несуществующий ID, чтобы не удалять
                    'photo': None, 'video': None, 'document': None,
                    'audio': None, 'voice': None, 'video_note': None
                })(),
                'answer': lambda **kwargs: None
            })()
            
            # Вызываем handle_post_view для показа обновленного поста
            await handle_post_view(fake_query, state, async_session_local, bot)
            
            action_text = "добавлено" if action == "add_media" else "заменено"
            logger.info(f"✅ MEDIA_UPDATED: {action_text} media for post {post_id}: {media_type}")
            
    except Exception as e:
        logger.error(f"❌ MEDIA_INPUT_ERROR: Failed to process media input: {e}")
        await message.answer("❌ Ошибка при обработке медиа. Попробуйте еще раз.")
