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

# ИМПОРТИРУЕМ НОВЫЙ БИЗНЕС-СЕРВИС (тот код, что вы кидали выше)
from core.business_savemod import init_business_savemod, router as business_router 

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

# Инициализируем бизнес-сервис
business_savemod_service = init_business_savemod(bot)

# Прокидываем зависимости в dp
dp["tracker_service"] = tracker_service
dp["savemod_service"] = savemod_service
dp["auth_service"] = auth_service
dp["session_manager"] = session_manager
dp["business_savemod_service"] = business_savemod_service

# --- Setup handlers ---
tracker.setup_tracker_handlers(tracker_service, savemod_service)
auth.setup_auth_handlers(auth_service)
start.setup_start_handlers(session_manager, tracker_service, savemod_service)

# --- Подключаем роутеры ---
dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)
dp.include_router(tracker.router)
# ВАЖНО: Подключаем роутер для Telegram Business
dp.include_router(business_router)

# --- FastAPI app ---
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # 1. Инициализация базы данных
    await init_db()
    
    # 2. Устанавливаем webhook ОДИН РАЗ со всеми нужными правами
    # Без этого списка Telegram не пришлет событие подключения!
    await bot.set_webhook(
        url=WEBHOOK_URL + WEBHOOK_PATH,
        allowed_updates=[
            "message", 
            "callback_query", 
            "business_connection",     # Для регистрации связи
            "business_message",        # Для получения сообщений
            "edited_business_message", # Для правок
            "deleted_business_messages" # Для удалений
        ]
    )
    
    # 3. Загружаем реестр бизнес-подключений из БД в память сервиса
    await business_savemod_service.load_registry()
    
    # 4. Восстанавливаем сессии UserBot (Telethon)
    await session_manager.restore_all_sessions()
    
    # 5. Синхронизируем SaveModService (для Telethon)
    for user_id, client in session_manager.clients.items():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(UserSession.savemod_enabled).where(UserSession.bot_user_id == user_id)
            )
            is_enabled = res.scalar()
            
            if is_enabled:
                # Если у вас в SaveModService есть этот метод:
                if hasattr(savemod_service, '_attach_handlers'):
                    savemod_service._attach_handlers(client, user_id)
                    savemod_service._attached_clients.add(user_id)
                    print(f"✅ SaveMod (UserBot) restored for {user_id}")

    me = await bot.get_me()
    print(f"🚀 Бот @{me.username} запущен через Webhook")
    print(f"🔗 URL: {WEBHOOK_URL + WEBHOOK_PATH}")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
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
