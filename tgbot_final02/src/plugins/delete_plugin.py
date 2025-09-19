from aiogram import Dispatcher
from aiogram.filters import Command
from plugins.admin_panel.main import IsAdmin
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker # Added import

# In-memory cache for last messages per chat
# TODO: Replace with Redis/DB in production
last_message_per_chat = {}


async def on_message_store(message: Message):
    """Store non-command messages for delete cache."""
    if message.text and not message.text.startswith("/"):
        last_message_per_chat[message.chat.id] = {
            'message_id': message.message_id,
            'text': message.text[:50] + '...' if len(message.text) > 50 else message.text
        }


async def command_delete(message: Message):
    """Delete message using reply, argument, or cache."""
    chat_id = message.chat.id
    
    try:
        # Method 1: Delete replied message
        if message.reply_to_message:
            await message.bot.delete_message(chat_id, message.reply_to_message.message_id)
            confirm_msg = await message.answer("Удалено ✅")
            # Auto-delete confirmation after 5 seconds
            await asyncio.sleep(5)
            try:
                await confirm_msg.delete()
            except:
                pass
            return
        
        # Method 2: Delete by message ID argument
        command_args = message.text.split()
        if len(command_args) > 1:
            try:
                target_message_id = int(command_args[1])
                await message.bot.delete_message(chat_id, target_message_id)
                confirm_msg = await message.answer("Удалено ✅")
                # Auto-delete confirmation after 5 seconds
                await asyncio.sleep(5)
                try:
                    await confirm_msg.delete()
                except:
                    pass
                return
            except ValueError:
                await message.answer("❌ Неверный ID сообщения")
                return
        
        # Method 3: Delete last cached message
        if chat_id in last_message_per_chat:
            cached_msg = last_message_per_chat[chat_id]
            await message.bot.delete_message(chat_id, cached_msg['message_id'])
            confirm_msg = await message.answer("Удалено ✅")
            # Remove from cache after successful deletion
            del last_message_per_chat[chat_id]
            # Auto-delete confirmation after 5 seconds
            await asyncio.sleep(5)
            try:
                await confirm_msg.delete()
            except:
                pass
            return
        
        # No target found
        await message.answer("❌ Нет цели для удаления. Используйте:\n" 
                           "• Reply на сообщение + /delete\n" 
                           "• /delete <message_id>\n" 
                           "• /delete (удалит последнее обычное сообщение)")
        
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            await message.answer("❌ Сообщение не найдено или уже удалено")
        elif "message can't be deleted" in str(e).lower():
            await message.answer("❌ Нельзя удалить это сообщение")
        else:
            await message.answer(f"❌ Ошибка: {e}")
        print(f"Delete error (BadRequest): {e}")
            
    except TelegramForbiddenError as e:
        await message.answer("❌ Нет прав для удаления сообщений в этом чате")
        print(f"Delete error (Forbidden): {e}")
        
    except Exception as e:
        await message.answer(f"❌ Неожиданная ошибка: {e}")
        print(f"Delete error (Unexpected): {e}")


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register delete plugin handlers."""
    dp.message.register(on_message_store, lambda m: not (m.text and m.text.startswith("/")))
    dp.message.register(command_delete, Command(commands=["delete"]), IsAdmin())