import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from bot.handlers import start, terms, auth, tracker
from core.tracker_service import TrackerService
from core.session_manager import SessionManager
from core.auth_service import AuthService
from core.savemod_service import SaveModService
from core.business_savemod_service import init_business_savemod
from db.init_db import init_db
from bot.handlers.start import setup_start_handlers

from sqlalchemy import select
from db.models import UserSession
from db.session import AsyncSessionLocal


async def main():
    # 1. Инициализация бота и диспетчера
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    # 2. Создание экземпляров сервисов
    session_manager = SessionManager()
    tracker_service = TrackerService(bot, session_manager)
    auth_service = AuthService()
    savemod_service = SaveModService(bot, session_manager)

    # 3. Business SaveMod
    bc_service = init_business_savemod(bot)

    # 4. Настройка обработчиков
    setup_start_handlers(session_manager, tracker_service, savemod_service)
    auth.setup_auth_handlers(auth_service)
    tracker.setup_tracker_handlers(tracker_service, savemod_service)

    dp["tracker_service"] = tracker_service
    dp["savemod_service"] = savemod_service
    dp["session_manager"] = session_manager
    dp["auth_service"] = auth_service

    # 5. Подключение роутеров
    from core.business_savemod_service import router as bc_router
    dp.include_router(bc_router)       # business события — первым
    dp.include_router(start.router)
    dp.include_router(terms.router)
    dp.include_router(auth.router)
    dp.include_router(tracker.router)

    # 6. Инициализация БД
    await init_db()

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

    print("🚀 Бот запущен...")
    await dp.start_polling(
        bot,
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