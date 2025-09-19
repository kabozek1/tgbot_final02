import logging
from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

def register(dp: Dispatcher, bot, async_session_local: async_sessionmaker):
    logger.info("✅ Registered post_manager_plugin (placeholder).")