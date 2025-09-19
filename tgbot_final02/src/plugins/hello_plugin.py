from aiogram import Dispatcher
from aiogram.filters import Command
from plugins.admin_panel.main import IsAdmin
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import async_sessionmaker # Added import
from sqlalchemy.future import select
from models.base import ChatInfo


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register hello plugin handlers."""
    
    async def handle_ping_cmd(message: Message):
        """Handle /ping command."""
        try:
            await message.answer("Pong!")
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            print(f"Error sending pong response: {e}")
        except Exception as e:
            print(f"Unexpected error in ping command: {e}")
    
    async def handle_ping_text(message: Message):
        """Handle ping text message."""
        try:
            await message.answer("Pong!")
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            print(f"Error sending pong response: {e}")
        except Exception as e:
            print(f"Unexpected error in ping text: {e}")
    
    async def set_topic_name_command(message: Message):
        """Handle /set_name_topic command to set topic name."""
        try:
            # Проверяем, что команда используется в групповом чате
            if message.chat.id > 0:
                await message.reply("❌ Эта команда работает только в групповых чатах.")
                return
                
            # Check if command is used in a topic (has message_thread_id)
            if not message.message_thread_id:
                await message.reply("❌ Эта команда должна использоваться в топике, а не в основном чате.")
                return
            
            # Parse command arguments
            command_text = message.text.strip()
            if not command_text.startswith('/set_name_topic '):
                await message.reply("❌ Используйте: /set_name_topic Название топика")
                return
            
            # Extract topic name
            topic_name = command_text[16:].strip()  # Remove '/set_name_topic ' prefix
            
            if not topic_name:
                await message.reply("❌ Укажите название топика: /set_name_topic Название топика")
                return
            
            if len(topic_name) > 100:
                await message.reply("❌ Название топика слишком длинное (максимум 100 символов)")
                return
            
            # Update or create ChatInfo record
            async with async_session_local() as session:
                # Check if ChatInfo record exists
                result = await session.execute(
                    select(ChatInfo).filter_by(
                        chat_id=message.chat.id,
                        topic_id=message.message_thread_id
                    )
                )
                chat_info = result.scalar_one_or_none()
                
                if chat_info:
                    # Update existing record
                    chat_info.topic_name = topic_name
                    await session.commit()
                    print(f"Updated topic name for chat {message.chat.id}, topic {message.message_thread_id}: {topic_name}")
                else:
                    # Create new record
                    new_chat_info = ChatInfo(
                        chat_id=message.chat.id,
                        topic_id=message.message_thread_id,
                        topic_name=topic_name
                    )
                    session.add(new_chat_info)
                    await session.commit()
                    print(f"Created new topic name for chat {message.chat.id}, topic {message.message_thread_id}: {topic_name}")
            
            await message.reply(f"✅ Название топика установлено: **{topic_name}**", parse_mode="Markdown")
            
        except Exception as e:
            print(f"Error setting topic name: {e}")
            await message.reply("❌ Ошибка при установке названия топика.")
    
    # Register command handlers
    dp.message.register(handle_ping_cmd, Command(commands=["ping"]))
    dp.message.register(set_topic_name_command, Command(commands=["set_name_topic"]), IsAdmin())
    
    # Register text handler
    dp.message.register(handle_ping_text, lambda m: m.text and m.text.lower().strip() == "ping")
