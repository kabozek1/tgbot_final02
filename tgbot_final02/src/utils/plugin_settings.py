"""
Универсальная система управления настройками плагинов
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update
from models.base import PluginSettings

logger = logging.getLogger(__name__)

# Дефолтные настройки для всех плагинов
DEFAULT_SETTINGS = {
    "antispam": {
        "enabled": True,
        "max_messages": 5,
        "window_seconds": 10
    },
    "antimat": {
        "enabled": True,
        "warnings_enabled": True,
        "blacklist_words": ["дурак", "лох"],
        "blacklist_links": ["t.me/", "http://", "https://"]
    },
    "warn": {
        "max_warnings": 3,
        "warning_expiry_days": 30
    },
    "reputation": {
        "enabled": True,
        "cooldown_seconds": 30,
        "max_daily_actions": 10
    },
    "poll": {
        "enabled": True,
        "max_options": 10,
        "auto_close_hours": 24
    },
    "captcha": {
        "enabled": True,
        "timeout_seconds": 300,
        "max_attempts": 3
    }
}


async def load_plugin_settings(plugin_name: str, async_session_local: async_sessionmaker) -> Dict[str, Any]:
    """
    Загружает настройки плагина из БД.
    Если настройки не найдены, создает дефолтные и сохраняет их.
    
    Args:
        plugin_name: Имя плагина (например, 'antispam', 'antimat')
        async_session_local: Сессия БД
    
    Returns:
        Dict с настройками плагина
    """
    # Отладочная информация (только в debug)
    logger.debug(f"🔍 load_plugin_settings plugin='{plugin_name}', type={type(async_session_local)}")
    
    # Проверяем, что передан правильный тип
    if not hasattr(async_session_local, '__call__'):
        logger.error(f"❌ async_session_local is not callable! Type: {type(async_session_local)}")
        logger.error(f"❌ Looks like a Bot was passed instead of async_sessionmaker")
        # Возвращаем дефолтные настройки
        return DEFAULT_SETTINGS.get(plugin_name, {})
    
    try:
        logger.debug(f"🔍 About to call async_session_local() - type: {type(async_session_local)}")
        async with async_session_local() as session:
            # Пытаемся загрузить настройки из БД
            result = await session.execute(
                select(PluginSettings).where(PluginSettings.plugin_name == plugin_name)
            )
            plugin_settings = result.scalar_one_or_none()
            
            if plugin_settings:
                logger.debug(f"✅ Loaded settings for plugin '{plugin_name}' from DB")
                return plugin_settings.settings
            
            # Если настройки не найдены, создаем дефолтные
            if plugin_name not in DEFAULT_SETTINGS:
                logger.warning(f"⚠️ No default settings found for plugin '{plugin_name}'")
                return {}
            
            default_settings = DEFAULT_SETTINGS[plugin_name].copy()
            
            # Сохраняем дефолтные настройки в БД
            new_settings = PluginSettings(
                plugin_name=plugin_name,
                settings=default_settings
            )
            session.add(new_settings)
            await session.commit()
            
            logger.debug(f"✅ Created default settings for plugin '{plugin_name}' and saved to DB")
            return default_settings
            
    except Exception as e:
        logger.error(f"❌ Error loading settings for plugin '{plugin_name}': {e}")
        # Возвращаем дефолтные настройки в случае ошибки
        return DEFAULT_SETTINGS.get(plugin_name, {})


async def save_plugin_settings(plugin_name: str, settings: Dict[str, Any], async_session_local: async_sessionmaker) -> bool:
    """
    Сохраняет настройки плагина в БД.
    
    Args:
        plugin_name: Имя плагина
        settings: Словарь с настройками
        async_session_local: Сессия БД
    
    Returns:
        True если успешно сохранено, False в случае ошибки
    """
    try:
        async with async_session_local() as session:
            # Проверяем, существуют ли настройки
            result = await session.execute(
                select(PluginSettings).where(PluginSettings.plugin_name == plugin_name)
            )
            plugin_settings = result.scalar_one_or_none()
            
            if plugin_settings:
                # Обновляем существующие настройки
                await session.execute(
                    update(PluginSettings)
                    .where(PluginSettings.plugin_name == plugin_name)
                    .values(settings=settings)
                )
            else:
                # Создаем новые настройки
                new_settings = PluginSettings(
                    plugin_name=plugin_name,
                    settings=settings
                )
                session.add(new_settings)
            
            await session.commit()
            logger.info(f"✅ Settings saved for plugin '{plugin_name}'")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error saving settings for plugin '{plugin_name}': {e}")
        return False


async def load_all_plugin_settings(async_session_local: async_sessionmaker) -> Dict[str, Dict[str, Any]]:
    """
    Загружает настройки всех плагинов при старте бота.
    
    Args:
        async_session_local: Сессия БД
    
    Returns:
        Словарь с настройками всех плагинов
    """
    all_settings = {}
    
    for plugin_name in DEFAULT_SETTINGS.keys():
        settings = await load_plugin_settings(plugin_name, async_session_local)
        all_settings[plugin_name] = settings
        logger.debug(f"✅ Loaded settings for plugin '{plugin_name}'")
    
    logger.info(f"✅ Loaded settings for {len(all_settings)} plugins")
    return all_settings


def get_plugin_setting(settings: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Безопасно получает значение настройки из словаря.
    
    Args:
        settings: Словарь с настройками
        key: Ключ настройки
        default: Значение по умолчанию
    
    Returns:
        Значение настройки или default
    """
    return settings.get(key, default)


def update_plugin_setting(settings: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    """
    Обновляет значение настройки в словаре.
    
    Args:
        settings: Словарь с настройками
        key: Ключ настройки
        value: Новое значение
    
    Returns:
        Обновленный словарь настроек
    """
    settings_copy = settings.copy()
    settings_copy[key] = value
    return settings_copy
