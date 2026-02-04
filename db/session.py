from sqlalchemy.ext.asyncio import async_sessionmaker
from db.base import engine

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)
