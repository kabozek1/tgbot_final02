"""
Утилиты для работы с сообщениями в админ панели
"""

import logging
from aiogram import Bot
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)


async def edit_message(query: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML", bot: Bot = None, preserve_media=False):
    """
    Универсальная функция для редактирования сообщений
    
    Args:
        query: CallbackQuery объект
        text: Новый текст сообщения
        reply_markup: Клавиатура (опционально)
        parse_mode: Режим парсинга (по умолчанию HTML)
        bot: Экземпляр бота
        preserve_media: Если True, не удаляет медиа-сообщения (по умолчанию False)
    
    Returns:
        message_id нового сообщения или None в случае ошибки
    """
    if not query or not query.message:
        logger.error("❌ EDIT_MESSAGE: Invalid query or message")
        return
    
    if not text:
        logger.error("❌ EDIT_MESSAGE: Text is required")
        return
    
    if not bot:
        logger.error("❌ EDIT_MESSAGE: Bot instance is required")
        return
    
    try:
        # Проверяем, есть ли медиа в сообщении
        has_media = (query.message.photo or query.message.video or 
                    query.message.document or query.message.audio or 
                    query.message.voice or query.message.video_note)
        
        if has_media and not preserve_media:
            # Для медиа-сообщений всегда удаляем старое и отправляем новое текстовое
            old_message_id = query.message.message_id
            try:
                await bot.delete_message(
                    chat_id=query.message.chat.id,
                    message_id=old_message_id
                )
            except Exception:
                pass  # Игнорируем ошибки удаления
            
            # Отправляем новое текстовое сообщение
            sent_message = await bot.send_message(
                chat_id=query.message.chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message.message_id
        elif has_media and preserve_media:
            # Если нужно сохранить медиа, пытаемся отредактировать caption
            try:
                await bot.edit_message_caption(
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return query.message.message_id
            except Exception as e:
                logger.warning(f"⚠️ EDIT_MESSAGE: Failed to edit caption, falling back to delete+send: {e}")
                # Если не удалось отредактировать caption, удаляем и отправляем новое
                try:
                    await bot.delete_message(
                        chat_id=query.message.chat.id,
                        message_id=query.message.message_id
                    )
                except Exception:
                    pass
                
                sent_message = await bot.send_message(
                    chat_id=query.message.chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return sent_message.message_id
        else:
            # Для текстовых сообщений используем обычное редактирование
            try:
                await bot.edit_message_text(
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return query.message.message_id
            except Exception as edit_error:
                # Если редактирование не удалось, проверяем причину
                error_msg = str(edit_error).lower()
                if "message is not modified" in error_msg:
                    # Сообщение не изменилось, это нормально
                    logger.debug(f"Message not modified: {edit_error}")
                    return query.message.message_id
                else:
                    # Другая ошибка, логируем и пробуем fallback
                    logger.warning(f"⚠️ EDIT_MESSAGE: Edit failed, trying fallback: {edit_error}")
                    raise edit_error
            
    except Exception as e:
        logger.error(f"❌ EDIT_MESSAGE: Failed to edit message: {e}")
        
        # Fallback: отправляем новое сообщение только в крайнем случае
        try:
            sent_message = await bot.send_message(
                chat_id=query.message.chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message.message_id
        except Exception as send_error:
            logger.error(f"❌ EDIT_MESSAGE: Failed to send fallback message: {send_error}")
            return None


# Обратная совместимость
async def smart_edit_message(query: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML", bot: Bot = None):
    """Обратная совместимость - использует edit_message"""
    await edit_message(query, text, reply_markup, parse_mode, bot)


async def safe_edit_message(query: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML", bot: Bot = None):
    """Обратная совместимость - использует edit_message"""
    await edit_message(query, text, reply_markup, parse_mode, bot)


async def universal_edit_message(query: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML", bot: Bot = None):
    """Обратная совместимость - использует edit_message"""
    await edit_message(query, text, reply_markup, parse_mode, bot)


async def send_message(bot: Bot, chat_id: int, text: str = "", reply_markup=None, parse_mode="HTML", **kwargs):
    """
    Универсальная функция для отправки сообщения с поддержкой медиа
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        text: Текст сообщения
        reply_markup: Клавиатура
        parse_mode: Режим парсинга
        **kwargs: Дополнительные параметры для отправки медиа
    
    Returns:
        Message: Отправленное сообщение
    """
    try:
        if kwargs.get('photo'):
            sent_message = await bot.send_photo(
                chat_id=chat_id,
                photo=kwargs['photo'],
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message
        elif kwargs.get('video'):
            sent_message = await bot.send_video(
                chat_id=chat_id,
                video=kwargs['video'],
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message
        elif kwargs.get('document'):
            sent_message = await bot.send_document(
                chat_id=chat_id,
                document=kwargs['document'],
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message
        else:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message
    except Exception as e:
        logger.error(f"❌ SEND_MESSAGE: Failed to send message: {e}")
        # Fallback - отправляем текстовое сообщение
        try:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return sent_message
        except Exception as send_error:
            logger.error(f"❌ SEND_MESSAGE: Failed to send fallback message: {send_error}")
            return None


# Обратная совместимость
async def send_or_edit_message(bot: Bot, chat_id: int, message_id: int = None, text: str = "", 
                              reply_markup=None, parse_mode="HTML", **kwargs):
    """Обратная совместимость - использует send_message"""
    await send_message(bot, chat_id, text, reply_markup, parse_mode, **kwargs)


async def cleanup_old_messages(bot: Bot, chat_id: int, message_ids: list):
    """
    Удаляет старые сообщения из чата
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_ids: Список ID сообщений для удаления
    """
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"Deleted message {message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete message {message_id}: {e}")


async def process_user_input(bot: Bot, message: Message, text: str, reply_markup=None, parse_mode="HTML", state=None):
    """
    Обработка ввода пользователя с использованием универсальных функций:
    - Удаляет сообщение пользователя
    - ВСЕГДА пытается редактировать предыдущее сообщение бота
    - Только если редактирование невозможно - отправляет новое
    - Сохраняет message_id в состоянии
    
    Args:
        bot: Экземпляр бота
        message: Сообщение пользователя
        text: Текст для отправки
        reply_markup: Клавиатура
        parse_mode: Режим парсинга
        state: Состояние FSM (опционально)
    
    Returns:
        int: message_id отправленного сообщения
    """
    try:
        # Удаляем сообщение пользователя
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass  # Игнорируем ошибки удаления
        
        # ВСЕГДА пытаемся редактировать предыдущее сообщение бота
        if state:
            data = await state.get_data()
            last_bot_message_id = data.get('last_bot_message_id') or data.get('last_message_id')
            if last_bot_message_id:
                try:
                    # Создаем fake_query для использования edit_message
                    fake_query = type('FakeQuery', (), {
                        'message': type('FakeMessage', (), {
                            'chat': message.chat,
                            'message_id': last_bot_message_id,
                            'photo': None, 'video': None, 'document': None,
                            'audio': None, 'voice': None, 'video_note': None
                        })(),
                        'answer': lambda **kwargs: None
                    })()
                    
                    # Используем edit_message для редактирования
                    new_message_id = await edit_message(
                        query=fake_query,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        bot=bot
                    )
                    
                    # Обновляем message_id в состоянии
                    await state.update_data(last_message_id=new_message_id)
                    logger.info(f"✅ PROCESS_USER_INPUT: Successfully edited message {last_bot_message_id} -> {new_message_id}")
                    return new_message_id
                    
                except Exception as e:
                    logger.warning(f"⚠️ PROCESS_USER_INPUT: Failed to edit message {last_bot_message_id}: {e}")
                    # Если редактирование не удалось, удаляем старое сообщение
                    try:
                        await bot.delete_message(chat_id=message.chat.id, message_id=last_bot_message_id)
                    except Exception:
                        pass  # Игнорируем ошибки удаления
        
        # Только если редактирование невозможно - отправляем новое сообщение
        logger.info(f"📤 PROCESS_USER_INPUT: Sending new message (no previous message to edit)")
        sent_message = await send_message(
            bot=bot,
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        if sent_message:
            # Сохраняем message_id в состоянии
            if state:
                await state.update_data(last_message_id=sent_message.message_id)
            
            logger.info(f"✅ PROCESS_USER_INPUT: Sent new message {sent_message.message_id}")
            return sent_message.message_id
        else:
            logger.error(f"❌ PROCESS_USER_INPUT: Failed to send message")
            return None
            
    except Exception as e:
        logger.error(f"❌ PROCESS_USER_INPUT: Error in user input processing: {e}")
        return None