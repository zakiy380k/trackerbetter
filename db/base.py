import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

# Принудительно добавляем sslmode=require, если это PostgreSQL
if DATABASE_URL and ("postgresql://" in DATABASE_URL or "postgres://" in DATABASE_URL):
    # Если в URL еще нет параметров, добавляем ?sslmode=require
    if "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"
    else:
        DATABASE_URL += "&sslmode=require"

    # Заменяем префиксы для asyncpg
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # ВАЖНО: проверка соединения перед использованием
    pool_recycle=300,    # Очистка старых соединений
)

Base = declarative_base()