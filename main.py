from db.init_db import init_db
import asyncio
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from sqlalchemy import select

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH
from bot.handlers import start, terms, auth, tracker

from core.session_manager import SessionManager
from core.tracker_service import TrackerService
from core.auth_service import AuthService
from core.savemod_service import SaveModService

# ВАЖНО: Импорт из твоего файла business_savemod_service.py
from core.business_savemod_service import init_business_savemod, router as business_router

from db.models import UserSession
from db.session import AsyncSessionLocal

# --- Bot & Dispatcher ---
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Services (ЕДИНСТВЕННЫЕ ЭКЗЕМПЛЯРЫ) ---
session_manager = SessionManager()
tracker_service = TrackerService(bot, session_manager)
auth_service = AuthService()
savemod_service = SaveModService(bot, session_manager)

# Инициализируем сервис для Telegram Business
business_service = init_business_savemod(bot)

# Прокидываем сервисы в контекст aiogram
dp["tracker_service"] = tracker_service
dp["savemod_service"] = savemod_service
dp["auth_service"] = auth_service
dp["session_manager"] = session_manager
dp["business_savemod_service"] = business_service

# --- Setup handlers ---
tracker.setup_tracker_handlers(tracker_service, savemod_service)
auth.setup_auth_handlers(auth_service)
start.setup_start_handlers(session_manager, tracker_service, savemod_service)

# --- Регистрация роутеров ---
dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)
dp.include_router(tracker.router)
# ПОДКЛЮЧАЕМ РОУТЕР БИЗНЕС-СЕРВИСА
dp.include_router(business_router)

# --- FastAPI app ---
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # 1. Инициализация БД
    await init_db()
    
    # 2. Устанавливаем Webhook со всеми разрешениями
    # Если не указать business_connection, бот не узнает о подключении!
    await bot.set_webhook(
        url=WEBHOOK_URL + WEBHOOK_PATH,
        allowed_updates=[
            "message", 
            "callback_query", 
            "business_connection", 
            "business_message", 
            "edited_business_message", 
            "deleted_business_messages"
        ]
    )
    
    # 3. Загружаем реестр бизнес-подключений из базы в память
    await business_service.load_registry()
    
    # 4. Восстановление UserBot сессий (Telethon)
    await session_manager.restore_all_sessions()
    
    # 5. Восстановление хендлеров SaveMod для UserBot
    for user_id, client in session_manager.clients.items():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(UserSession.savemod_enabled).where(UserSession.bot_user_id == user_id)
            )
            is_enabled = res.scalar()
            
            if is_enabled and hasattr(savemod_service, '_attach_handlers'):
                savemod_service._attach_handlers(client, user_id)
                savemod_service._attached_clients.add(user_id)

    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print(f"🛠 Business Mode: ACTIVE")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    await dp.feed_raw_update(bot, update_data)
    return {"ok": True}

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "ok"}

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.api_route("/", methods=["GET", "POST"])
async def root():
    return {"status": "alive"}
