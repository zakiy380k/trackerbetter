import asyncio
import logging
import time

from sqlalchemy import delete

from db.session import AsyncSessionLocal
from db.models import SavedMessage

logger = logging.getLogger(__name__)

# Сообщения хранятся 14 дней
MESSAGE_RETENTION_DAYS = 14

# Проверяем очистку раз в 24 часа
CLEANUP_INTERVAL = 24 * 60 * 60


async def cleanup_old_saved_messages():
    """
    Удаляет сообщения из saved_messages,
    дата которых старше 14 дней.

    Остальные таблицы БД не затрагиваются.
    """

    cutoff_timestamp = int(
        time.time() - MESSAGE_RETENTION_DAYS * 24 * 60 * 60
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                delete(SavedMessage).where(
                    SavedMessage.date < cutoff_timestamp
                )
            )

            deleted_count = result.rowcount or 0

            await session.commit()

            logger.info(
                "🧹 Очистка saved_messages: удалено %s сообщений старше %s дней",
                deleted_count,
                MESSAGE_RETENTION_DAYS,
            )

        except Exception:
            await session.rollback()
            logger.exception("❌ Ошибка при очистке saved_messages")


async def cleanup_loop():
    """
    Запускает очистку saved_messages каждые 24 часа.
    """

    while True:
        try:
            await cleanup_old_saved_messages()
        except Exception:
            logger.exception("❌ Ошибка cleanup_loop")

        await asyncio.sleep(CLEANUP_INTERVAL)