import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base


DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    
    DATABASE_URL = "sqlite+aiosqlite:///database.db"

#марк борисюк вонючий
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,          
    max_overflow=20,       
    pool_pre_ping=True    
)

Base = declarative_base()