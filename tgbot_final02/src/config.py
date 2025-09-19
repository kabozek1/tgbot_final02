import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv, dotenv_values



class Settings:
    def __init__(self, config_values):

        self.DATABASE_URL: str = config_values.get("DATABASE_URL", "")
        self.REDIS_URL: str = config_values.get("REDIS_URL", "")

        # Parse ADMINS string to list of integers
        admins_str = config_values.get("ADMINS", "")
        self.ADMINS: list[int] = [int(admin.strip()) for admin in admins_str.split(",") if admin.strip()]
        
        # Настройки времени удаления сообщений для плагинов
        self.WARN_MESSAGE_DELETE_DELAY: int = int(config_values.get("WARN_MESSAGE_DELETE_DELAY", "3"))
        self.KICK_MESSAGE_DELETE_DELAY: int = int(config_values.get("KICK_MESSAGE_DELETE_DELAY", "3"))
        self.BAN_MESSAGE_DELETE_DELAY: int = int(config_values.get("BAN_MESSAGE_DELETE_DELAY", "3"))
        self.REP_MESSAGE_DELETE_DELAY: int = int(config_values.get("REP_MESSAGE_DELETE_DELAY", "3"))
        self.MUTE_MESSAGE_DELETE_DELAY: int = int(config_values.get("MUTE_MESSAGE_DELETE_DELAY", "3"))
        
        # Настройки для будущих плагинов
        self.ANTIFLOOD_MESSAGE_DELETE_DELAY: int = int(config_values.get("ANTIFLOOD_MESSAGE_DELETE_DELAY", "5"))
        self.ANTIMAT_MESSAGE_DELETE_DELAY: int = int(config_values.get("ANTIMAT_MESSAGE_DELETE_DELAY", "5"))


# Singleton instance
_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        dotenv_path = find_dotenv()
        load_dotenv(dotenv_path=dotenv_path)
        print(f"DEBUG: Loading .env from: {dotenv_path}", flush=True)
        config_values = dotenv_values(dotenv_path=dotenv_path)
        print(f"DEBUG: DATABASE_URL from config_values: {config_values.get('DATABASE_URL')}", flush=True)
        _settings = Settings(config_values)
    return _settings


def get_logo_path() -> str:
    """Возвращает абсолютный путь к логотипу относительно корня проекта"""
    # Получаем путь к корню проекта (на уровень выше src)
    project_root = Path(__file__).parent.parent
    logo_path = project_root / "logo.png"
    return str(logo_path.absolute())
