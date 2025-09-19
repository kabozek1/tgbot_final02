"""
Мониторинг системы для админ панели
"""

import psutil
import platform
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Глобальная переменная для отслеживания времени запуска бота
_bot_start_time = time.time()


def set_bot_start_time():
    """Устанавливает время запуска бота"""
    global _bot_start_time
    _bot_start_time = time.time()


def get_system_info() -> Dict[str, Any]:
    """Получает информацию о системе"""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Память
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used = memory.used / (1024**3)  # GB
        memory_total = memory.total / (1024**3)  # GB
        
        # Диск
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        disk_used = disk.used / (1024**3)  # GB
        disk_total = disk.total / (1024**3)  # GB
        
        # Система
        system_info = {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'python_version': platform.python_version(),
            'cpu_percent': cpu_percent,
            'cpu_count': cpu_count,
            'memory_percent': memory_percent,
            'memory_used_gb': round(memory_used, 2),
            'memory_total_gb': round(memory_total, 2),
            'disk_percent': round(disk_percent, 2),
            'disk_used_gb': round(disk_used, 2),
            'disk_total_gb': round(disk_total, 2),
        }
        
        return system_info
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return {
            'platform': 'Unknown',
            'platform_version': 'Unknown',
            'python_version': 'Unknown',
            'cpu_percent': 0,
            'cpu_count': 0,
            'memory_percent': 0,
            'memory_used_gb': 0,
            'memory_total_gb': 0,
            'disk_percent': 0,
            'disk_used_gb': 0,
            'disk_total_gb': 0,
        }


def get_bot_uptime() -> str:
    """Получает время работы бота"""
    try:
        uptime_seconds = time.time() - _bot_start_time
        uptime = timedelta(seconds=int(uptime_seconds))
        
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м {seconds}с"
    except Exception as e:
        logger.error(f"Failed to get bot uptime: {e}")
        return "Неизвестно"


def get_resource_status_emoji(percent: float) -> str:
    """Возвращает эмодзи в зависимости от загрузки ресурса"""
    if percent < 50:
        return "🟢"
    elif percent < 80:
        return "🟡"
    else:
        return "🔴"


def format_bytes(bytes_value: int) -> str:
    """Форматирует байты в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"
