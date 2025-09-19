import logging
import sys


# Configure logging format
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Set level for all loggers to DEBUG
logging.getLogger().setLevel(logging.DEBUG)

# Ensure plugin loggers also use DEBUG level
for logger_name in ['plugins.mute_plugin', 'plugins.ban_plugin', 'plugins.warn_plugin', 'plugins.reputation_plugin', 'aiogram']:
    logging.getLogger(logger_name).setLevel(logging.DEBUG)

def get_logger(name: str) -> logging.Logger:
    """Get logger instance with specified name."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger
