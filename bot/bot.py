from email import message
import logging
import os
import asyncio
from tkinter import Message
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis

from config import BOT_TOKEN
from bot.handlers import start, terms, auth, tracker
from core.tracker_service import TrackerService
from core.session_manager import SessionManager
from core.auth_service import AuthService
from core.savemod_service import SaveModService
from core.business_savemod_service import init_business_savemod, router as business_savemod_router
from core.user_bot_service import UserBotService
from db.init_db import init_db
from bot.handlers.start import setup_start_handlers
from bot.handlers.user_bot import router as user_bot_router
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy import select
from db.models import UserSession
from db.session import AsyncSessionLocal

redis_url = os.getenv("REDIS_URL")

if redis_url:
    try:
        redis = Redis.from_url(
            redis_url, 
            decode_responses=True,
            socket_timeout=30,
            socket_connect_timeout=30
        )
        storage = RedisStorage(redis=redis)
        print("✅ RedisStorage успешно подключён (Persistent)")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Redis: {e}")
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
        print("→ Используется MemoryStorage")
else:
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    print("⚠️ REDIS_URL не найден → MemoryStorage")


dp = Dispatcher(storage=storage)

async def main():
    logging.basicConfig(
        level=logging.INFO)
    # 1. Инициализация бота и диспетчера
    main_bot = Bot(BOT_TOKEN)

    from bot.handlers.user_bot import setup_user_bot_handlers

    # 2. Создание экземпляров сервисов
    session_manager = SessionManager()
    savemod_service = SaveModService(main_bot, session_manager)
    user_bot_service = UserBotService(savemod_service, session_manager, dp)
    tracker_service = TrackerService(main_bot, session_manager)
    auth_service = AuthService()
    bc_service = init_business_savemod(main_bot)

    setup_user_bot_handlers(savemod_service, session_manager)
    setup_start_handlers(session_manager, tracker_service, savemod_service, user_bot_service)
    auth.setup_auth_handlers(auth_service)
    tracker.setup_tracker_handlers(tracker_service, savemod_service)

    dp["user_bot_service"] = user_bot_service
    dp["tracker_service"] = tracker_service
    dp["savemod_service"] = savemod_service
    dp["session_manager"] = session_manager
    dp["auth_service"] = auth_service

    # 5. Подключение роутеров
    from core.business_savemod_service import router as bc_router
    dp.include_router(bc_router)     

    dp.include_router(start.router)
    dp.include_router(terms.router)
    dp.include_router(auth.router)
    dp.include_router(tracker.router)

    dp.include_router(user_bot_router)



    # 6. Инициализация БД
    await init_db()

    await user_bot_service.load_all_bots()

    # 7. Восстанавливаем Telethon-сессии и SaveMod хендлеры
    await session_manager.restore_all_sessions()
    for user_id, client in session_manager.clients.items():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(UserSession.savemod_enabled).where(UserSession.bot_user_id == user_id)
            )
            is_enabled = res.scalar()
            if is_enabled:
                savemod_service._attach_handlers(client, user_id)
                savemod_service._attached_clients.add(user_id)
                print(f"✅ SaveMod restored for {user_id}")

    # 8. Загружаем реестр Business Connection подключений
    await bc_service.load_registry()

    # @dp.message()
    # async def global_echo(message: Message):
    #     print(f"🔄 Сработал Глобальный Эхо-Хендлер! Бот ID: {message.bot.id}, Текст: {message.text}")
    print("🚀 Бот запущен...")
    await main_bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        main_bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")