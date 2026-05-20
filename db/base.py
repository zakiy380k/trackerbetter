import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///database.db")

connect_args = {}

if "postgresql" in DATABASE_URL or "postgres://" in DATABASE_URL:
    # Убираем sslmode из URL если вдруг есть
    DATABASE_URL = DATABASE_URL.replace("?sslmode=require", "").replace("&sslmode=require", "")

    # Правильный префикс для asyncpg
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

    # SSL передаём через connect_args, не через URL
    connect_args = {"ssl": "require"}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=connect_args,
)

Base = declarative_base()