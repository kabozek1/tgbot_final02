import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from config import get_settings
from models.declarative_base import Base
from sqlalchemy import create_engine

# Import all models to ensure they are registered with Base
from models.base import *


def recreate_db():
    settings = get_settings()
    
    # Fix database path to use project root
    database_url = settings.DATABASE_URL
    if database_url.startswith('sqlite'):
        from pathlib import Path
        # Get the project root directory (where this script is located)
        project_root = Path(__file__).parent
        
        # Extract filename from database_url
        if ':///' in database_url:
            filename = database_url.split(':///')[-1]
            filename = filename.replace('%2F', '/').replace('%20', ' ')
            
            # Always use project root for relative paths
            if not filename.startswith('/'):
                db_path = project_root / filename
            else:
                db_path = Path(filename)
            
            database_url = f"sqlite:///{db_path}"
            print(f"Using database at: {db_path}")
    
    # Use synchronous SQLite URL for create_all/drop_all operations
    sync_db_url = database_url.replace('+aiosqlite', '')
    engine = create_engine(sync_db_url)

    print(f"Attempting to drop all tables for database: {sync_db_url}", flush=True)
    try:
        Base.metadata.drop_all(engine)
        print("All tables dropped successfully.", flush=True)
    except Exception as e:
        print(f"Error dropping tables: {e}", flush=True)

    print(f"Attempting to create all tables for database: {sync_db_url}", flush=True)
    try:
        Base.metadata.create_all(engine)
        print("All tables created successfully.", flush=True)
    except Exception as e:
        print(f"Error creating tables: {e}", flush=True)

if __name__ == "__main__":
    recreate_db()