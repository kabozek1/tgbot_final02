import logging
import os
from pathlib import Path
from sqlalchemy import create_engine
from models.declarative_base import Base

# Import all model modules here so that their models are registered with the Base metadata
from . import base

logger = logging.getLogger(__name__)

def get_corrected_database_url(database_url: str) -> str:
    """
    Returns the corrected database URL with absolute path for SQLite databases.
    """
    if database_url.startswith('sqlite'):
        # Get the project root directory (where .env file is located)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent  # Go up from src/models/ to project root
        
        # Extract filename from database_url
        if ':///' in database_url:
            filename = database_url.split(':///')[-1]
            filename = filename.replace('%2F', '/').replace('%20', ' ')
            
            # Always use project root for relative paths
            if not filename.startswith('/'):
                db_path = project_root / filename
            else:
                db_path = Path(filename)
            
            return f"sqlite+aiosqlite:///{db_path}"
    
    return database_url

async def init_db(database_url: str):
    """
    Initializes the database. Creates all tables defined in the model modules.
    Returns the corrected database URL.
    """
    # Get the corrected database URL
    corrected_url = get_corrected_database_url(database_url)
    if corrected_url != database_url:
        logger.info(f"SQLite database will be created at: {corrected_url.replace('sqlite+aiosqlite:///', '')}")
    
    # Use a synchronous engine for create_all, as it's not an async operation itself
    # and avoids potential greenlet_spawn issues during startup.
    sync_db_url = corrected_url.replace('+aiosqlite', '')
    engine = create_engine(sync_db_url)

    # In a typical production setup, you would use Alembic for migrations
    # instead of create_all. The drop_all calls are commented out to prevent data loss.
    # logger.debug(f"Dropping all tables for database: {corrected_url}")
    # Base.metadata.drop_all(engine)
    # logger.debug("All tables dropped successfully.")

    logger.debug(f"Calling Base.metadata.create_all for {corrected_url}")
    Base.metadata.create_all(engine)
    logger.debug(f"Tables created successfully for database: {corrected_url}")
    
    return corrected_url
