import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from bot.handlers import start, terms, auth, tracker
from core.tracker_service import TrackerService
from core.session_manager import SessionManager
from core.auth_service import AuthService
from db.init_db import *
from core.savemod_service  import  SaveModService

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
session_manager = SessionManager()
tracker_service = TrackerService(bot, session_manager)
auth_service = AuthService()
savemod_service = SaveModService(bot, session_manager)


tracker.setup_tracker_handlers(tracker_service, savemod_service,)
auth.setup_auth_handlers(auth_service)


dp.include_router(tracker.router)
dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())