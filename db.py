import os

from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

load_dotenv() 

Base = declarative_base()

def get_sync_database_url():
    return f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@" \
           f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"


sync_engine = create_engine(get_sync_database_url())
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def get_db():
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


