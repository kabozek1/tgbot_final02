import logging
from datetime import datetime
from aiogram import Dispatcher, Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update
from models.base import Trigger

logger = logging.getLogger(__name__)


async def migrate_triggers_to_db(async_session_local):
    """Миграция существующих триггеров в базу данных"""
    # Словарь триггеров для миграции
    TRIGGERS = {
        "цена?": "Прайс в закрепе.",
        "расписание?": "Смотри pinned сообщение",
        "контакт?": "Пишите в ЛС @manager"
    }
    
    try:
        async with async_session_local() as session:
            # Проверяем, есть ли уже триггеры в БД
            result = await session.execute(select(Trigger))
            existing_triggers = result.scalars().all()
            
            if not existing_triggers:
                # Добавляем триггеры из словаря
                for trigger_text, response_text in TRIGGERS.items():
                    trigger = Trigger(
                        trigger_text=trigger_text,
                        response_text=response_text,
                        is_active=True,
                        trigger_count=0
                    )
                    session.add(trigger)
                
                await session.commit()
                logger.info(f"Migrated {len(TRIGGERS)} triggers to database")
            else:
                logger.info(f"Database already contains {len(existing_triggers)} triggers")
    except Exception as e:
        logger.error(f"Error migrating triggers to database: {e}")


async def get_active_triggers(async_session_local):
    """Получить все активные триггеры из БД"""
    try:
        async with async_session_local() as session:
            result = await session.execute(
                select(Trigger).where(Trigger.is_active == True)
            )
            return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting active triggers: {e}")
        return []


async def update_trigger_stats(trigger_id: int, async_session_local):
    """Обновить статистику срабатывания триггера"""
    try:
        async with async_session_local() as session:
            await session.execute(
                update(Trigger)
                .where(Trigger.id == trigger_id)
                .values(
                    trigger_count=Trigger.trigger_count + 1,
                    last_triggered=datetime.utcnow()
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error updating trigger stats: {e}")


async def on_trigger_message(message: Message, bot: Bot, async_session_local):
    """Обработчик сообщений с триггерами"""
    if not message.text:
        return
    
    text = message.text.lower()
    triggers = await get_active_triggers(async_session_local)
    
    for trigger in triggers:
        # Разбиваем триггер по символу | для поддержки множественных триггеров
        trigger_variants = [t.strip().lower() for t in trigger.trigger_text.split('|')]
        
        for variant in trigger_variants:
            if variant in text:
                await message.reply(trigger.response_text)
                await update_trigger_stats(trigger.id, async_session_local)
                logger.info(f"Triggered response for '{variant}': {trigger.response_text}")
                return  # Выходим после первого срабатывания


def register(dp: Dispatcher, bot: Bot, async_session_local):
    """Регистрация обработчиков триггеров"""
    
    # Миграция триггеров при запуске
    import asyncio
    asyncio.create_task(migrate_triggers_to_db(async_session_local))
    
    # Обработчик сообщений с триггерами
    async def trigger_handler(message: Message):
        await on_trigger_message(message, bot, async_session_local)
    
    dp.message.register(
        trigger_handler,
        lambda message: message.text is not None and not message.text.startswith('/')
    )