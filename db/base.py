import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base

# Получаем DATABASE_URL из переменных окружения Render
DATABASE_URL = os.getenv("DATABASE_URL")

# Если URL начинается с postgres, приводим его к виду для asyncpg
if DATABASE_URL and (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    # Запасной вариант для локальной разработки
    DATABASE_URL = "sqlite+aiosqlite:///database.db"

# Создаем движок с настройками пула соединений
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,          # Количество соединений в пуле
    max_overflow=20,       # Максимальное количество дополнительных соединений
    pool_pre_ping=True     # Самое важное: проверка соединения перед запросом
)

Base = declarative_base()