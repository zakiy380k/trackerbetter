from db.init_db import init_db

import asyncio
from fastapi import FastAPI, Request, Response

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH

from bot.handlers import start, terms, auth, tracker

from core.session_manager import SessionManager
from core.tracker_service import TrackerService
from core.auth_service import AuthService
from core.savemod_service  import  SaveModService
# если есть SaveModService — подключишь аналогично

# --- Bot & Dispatcher ---
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- Services (ЕДИНСТВЕННЫЕ ЭКЗЕМПЛЯРЫ) ---
session_manager = SessionManager()
tracker_service = TrackerService(bot, session_manager)
auth_service = AuthService()
savemod_service = SaveModService(bot, session_manager)

# --- Setup handlers ---
tracker.setup_tracker_handlers(tracker_service, savemod_service,)
auth.setup_auth_handlers(auth_service)
start.setup_start_handlers(session_manager)

dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)
dp.include_router(tracker.router)

# --- FastAPI app ---
app = FastAPI()


@app.on_event("startup")
async def on_startup():
    # Инициализация базы данных
    await init_db()
    # Устанавливаем webhook
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)
    await session_manager.restore_all_sessions()
    me = await bot.get_me()
    print(f"WEBHOOK SET for @{me.username}: {WEBHOOK_URL + WEBHOOK_PATH}")

@app.head("/health")
async def head_root():
    return Response(status_code=200)    

@app.on_event("shutdown")
async def on_shutdown():
    # Корректно закрываем aiohttp-сессию
    await bot.session.close()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}


# --- Optional health-check ---
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "alive"}

@app.api_route("/", methods=["GET", "POST"])
async def root():
    return {"status": "alive"}

