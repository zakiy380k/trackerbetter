import os
import asyncio
import logging
from fastapi import FastAPI, Request

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH

from bot.handlers import start, terms, auth, tracker
from core.user_bot_service import UserBotService
from core.session_manager import SessionManager
from core.tracker_service import TrackerService
from core.auth_service import AuthService
from core.savemod_service import SaveModService
from core.business_savemod_service import init_business_savemod, router as business_router

from db.models import UserSession
from db.session import AsyncSessionLocal
from sqlalchemy import select
from db.init_db import init_db   # ← Добавили импорт

# ====================== REDIS STORAGE ======================
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
        print("✅ RedisStorage успешно подключён")
    except Exception as e:
        print(f"⚠️ Ошибка Redis: {e}")
        from aiogram.fsm.storage.memory import MemoryStorage
        storage = MemoryStorage()
else:
    from aiogram.fsm.storage.memory import MemoryStorage
    storage = MemoryStorage()
    print("⚠️ Используется MemoryStorage")

# ====================== BOT ======================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ====================== СЕРВИСЫ ======================
session_manager = SessionManager()
tracker_service = TrackerService(bot, session_manager)
auth_service = AuthService()
savemod_service = SaveModService(bot, session_manager)
business_service = init_business_savemod(bot)
user_bot_service = UserBotService(savemod_service=savemod_service, session_manager=session_manager, dispatcher=dp)  # Инициализируем позже

# Контекст
dp["user_bot_service"] = user_bot_service
dp["tracker_service"] = tracker_service
dp["savemod_service"] = savemod_service
dp["auth_service"] = auth_service
dp["session_manager"] = session_manager
dp["business_savemod_service"] = business_service

# Настройка хендлеров
tracker.setup_tracker_handlers(tracker_service, savemod_service)
auth.setup_auth_handlers(auth_service)
start.setup_start_handlers(session_manager, tracker_service, savemod_service, user_bot_service)

# ====================== РОУТЕРЫ ======================
dp.include_router(business_router)
dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)
dp.include_router(tracker.router)

# ====================== FASTAPI ======================
app = FastAPI(title="TrackerZaki Bot")

@app.on_event("startup")
async def on_startup():
    await init_db()

    await user_bot_service.load_all_bots()

    # Webhook
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1.5)

    await bot.set_webhook(
        url=WEBHOOK_URL + WEBHOOK_PATH,
        allowed_updates=[
            "message", "callback_query", "business_connection",
            "business_message", "edited_business_message", "deleted_business_messages"
        ],
        drop_pending_updates=True
    )

    await business_service.load_registry()
    await session_manager.restore_all_sessions()

    # Восстановление SaveMod
    for user_id, client in session_manager.clients.items():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(UserSession.savemod_enabled)
                .where(UserSession.bot_user_id == user_id)
            )
            if res.scalar():
                savemod_service._attach_handlers(client, user_id)
                savemod_service._attached_clients.add(user_id)

    me = await bot.get_me()
    print(f"✅ @{me.username} запущен на Render (Redis: {'ON' if redis_url else 'OFF'})")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    await dp.feed_raw_update(bot, update_data)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "user_bots": len(user_bot_service.running_bots)}


@app.get("/restart_webhook")
async def restart_webhook():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(1)
    await bot.set_webhook(url=WEBHOOK_URL + WEBHOOK_PATH, allowed_updates=[...])
    return {"status": "webhook restarted"}


@app.on_event("shutdown")
async def on_shutdown():
    for bot_id in list(user_bot_service.running_bots.keys()):
        await user_bot_service.stop_bot(bot_id)
    await bot.session.close()


@app.get("/")
async def root():
    return {"status": "alive"}