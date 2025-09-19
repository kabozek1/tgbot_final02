from aiogram import Dispatcher
from aiogram.filters import Command
from plugins.admin_panel.main import IsAdmin
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import uuid
from sqlalchemy.ext.asyncio import async_sessionmaker # Added import

# In-memory storage for polls
# TODO: Replace with Redis/DB in production
polls = {}  # {poll_id: {"question": str, "options": [str], "counts": [int], "voted": set}}


async def command_poll(message: Message):
    """Create a poll with the specified question and options."""
    try:
        # Parse command arguments
        if not message.text or len(message.text.split()) < 2:
            await message.answer("❌ Используйте: /poll Вопрос;Вариант1;Вариант2;...")
            return
        
        # Extract poll text (everything after /poll)
        poll_text = message.text[6:].strip()  # Remove "/poll " prefix
        
        # Split by semicolon
        parts = poll_text.split(';')
        if len(parts) < 3:  # At least question + 2 options
            await message.answer("❌ Недостаточно вариантов. Минимум: вопрос + 2 варианта")
            return
        
        question = parts[0].strip()
        options = [option.strip() for option in parts[1:] if option.strip()]
        
        if len(options) < 2:
            await message.answer("❌ Недостаточно вариантов ответа (минимум 2)")
            return
        
        # Generate unique poll ID
        poll_id = str(uuid.uuid4())
        
        # Create inline keyboard with options
        keyboard_buttons = []
        for i, option in enumerate(options):
            callback_data = f"poll:{poll_id}:{i}"
            keyboard_buttons.append([InlineKeyboardButton(text=option, callback_data=callback_data)])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Send poll message
        poll_message = await message.answer(f"📊 {question}", reply_markup=keyboard)
        
        # Store poll data with poll_id as key
        polls[poll_id] = {
            "question": question,
            "options": options,
            "counts": [0] * len(options),
            "voted": set(),
            "message_id": poll_message.message_id
        }
        
        # Delete original command message
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
            
    except Exception as e:
        await message.answer("❌ Ошибка при создании опроса")
        print(f"Poll creation error: {e}")


async def callback_poll_handler(callback: CallbackQuery):
    """Handle poll voting."""
    try:
        # Parse callback data: poll:{poll_id}:{option_index}
        if not callback.data or not callback.data.startswith("poll:"):
            await callback.answer("❌ Неверные данные опроса")
            return
            
        parts = callback.data.split(':')
        if len(parts) != 3:
            await callback.answer("❌ Ошибка в данных опроса")
            return
            
        poll_id = parts[1]
        option_index = int(parts[2])
        
        # Check if poll exists
        if poll_id not in polls:
            await callback.answer("Опрос не найден или устарел", show_alert=True)
            return
        
        poll_data = polls[poll_id]
        user_id = callback.from_user.id
        
        # Check if user already voted
        if user_id in poll_data["voted"]:
            await callback.answer("Вы уже голосовали", show_alert=True)
            return
        
        # Check if option index is valid
        if option_index >= len(poll_data["options"]):
            await callback.answer("❌ Неверный вариант")
            return
        
        # Record vote
        poll_data["counts"][option_index] += 1
        poll_data["voted"].add(user_id)
        
        # Update poll message with results
        result_text = f'📊 {poll_data["question"]}\n\n'
        for i, (option, count) in enumerate(zip(poll_data["options"], poll_data["counts"])):
            result_text += f"{i+1}) {option} — {count} голосов\n"
        
        # Create new keyboard with updated results
        keyboard_buttons = []
        for i, option in enumerate(poll_data["options"]):
            callback_data = f"poll:{poll_id}:{i}"
            count = poll_data['counts'][i]
            button_text = f"{option} ({count})"
            keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Update the poll message
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=poll_data["message_id"],
            text=result_text,
            reply_markup=keyboard
        )
        
        # Confirm vote
        await callback.answer("✅ Голос учтён!")
        
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await callback.answer("❌ Не удалось обновить опрос")
        print(f"Poll update error: {e}")
    except Exception as e:
        await callback.answer("❌ Ошибка при голосовании")
        print(f"Poll voting error: {e}")


def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    """Register poll plugin handlers."""
    dp.message.register(command_poll, Command(commands=["poll"]), IsAdmin())
    dp.callback_query.register(callback_poll_handler, lambda c: c.data and c.data.startswith("poll:"))