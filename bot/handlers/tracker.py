from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

def setup_tracker_handlers(tracker_service):
    @router.message(Command("tracker"))
    async def start_tracker_handler(message: Message):
        parts = message.text.split(maxsplit=1)
    
        if len(parts) < 2:
            await message.answer(
                "❗ Укажи цель\n"
                "/tracker username\n"
                "/tracker user_id"
            )
            return
    
        target = parts[1].strip()
    
        try:
            await tracker_service.start(message.from_user.id, target)
            await message.answer("✅ Tracker successfully started")
        except RuntimeError as e:
            await message.answer(str(e))

