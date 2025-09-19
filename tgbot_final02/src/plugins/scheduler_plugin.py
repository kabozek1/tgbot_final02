import logging
import json
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from datetime import datetime

from models.base import ScheduledPost

logger = logging.getLogger(__name__)

async def check_and_send_posts(bot: Bot, async_session_local: async_sessionmaker):
    now = datetime.now()
    
    async with async_session_local() as session:
        try:
            result = await session.execute(
                select(ScheduledPost).filter(ScheduledPost.status == 'pending', ScheduledPost.publish_time <= now)
            )
            due_posts = result.scalars().all()

            if not due_posts:
                return

            success_count = 0
            failed_count = 0
            
            for post in due_posts:
                try:
                    # Parse buttons if they exist
                    reply_markup = None
                    if post.buttons_json:
                        try:
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
                            logger.error(f"SCHEDULER: Failed to parse buttons for post #{post.id}: {e}")
                    
                    sent_message = None
                    if post.media_file_id:
                        if post.media_type == 'photo':
                            sent_message = await bot.send_photo(
                                chat_id=post.chat_id, 
                                message_thread_id=post.topic_id, 
                                photo=post.media_file_id, 
                                caption=post.text,
                                reply_markup=reply_markup
                            )
                        elif post.media_type == 'video':
                            sent_message = await bot.send_video(
                                chat_id=post.chat_id, 
                                message_thread_id=post.topic_id, 
                                video=post.media_file_id, 
                                caption=post.text,
                                reply_markup=reply_markup
                            )
                        elif post.media_type == 'document':
                            sent_message = await bot.send_document(
                                chat_id=post.chat_id, 
                                message_thread_id=post.topic_id, 
                                document=post.media_file_id, 
                                caption=post.text,
                                reply_markup=reply_markup
                            )
                    else:
                        sent_message = await bot.send_message(
                            chat_id=post.chat_id, 
                            message_thread_id=post.topic_id, 
                            text=post.text,
                            reply_markup=reply_markup
                        )
                    
                    # Update post status and store Telegram message ID
                    post.status = 'published'
                    post.published_at = now
                    if sent_message:
                        post.telegram_message_id = sent_message.message_id
                    
                    success_count += 1

                except Exception as e:
                    post.status = 'failed'
                    failed_count += 1
                    logger.error(f"SCHEDULER: Failed to send post #{post.id}: {e}")
            
            # Логируем результат в одну строчку
            if success_count > 0 or failed_count > 0:
                logger.info(f"SCHEDULER: {len(due_posts)} posts processed - {success_count} sent, {failed_count} failed")
                
            await session.commit()
        except Exception as e:
            logger.error(f"SCHEDULER: A critical error occurred during the check_and_send_posts job: {e}")
            await session.rollback()

def register(dp, bot: Bot, async_session_local: async_sessionmaker):
    """Register the scheduler plugin and start the job."""
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Setting timezone
    scheduler.add_job(check_and_send_posts, 'interval', seconds=60, args=[bot, async_session_local])
    scheduler.start()
    logger.info("✅ Scheduler plugin registered and started. Job will run every 60 seconds.")