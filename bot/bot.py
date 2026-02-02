import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from bot.handlers import start, terms, auth, tracker
from core.tracker_service import TrackerService
from core.session_manager import SessionManager

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
session_manager = SessionManager()
tracker_service = TrackerService(bot, session_manager)

tracker.setup_tracker_handlers(tracker_service)

dp.include_router(tracker.router)
dp.include_router(start.router)
dp.include_router(terms.router)
dp.include_router(auth.router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())