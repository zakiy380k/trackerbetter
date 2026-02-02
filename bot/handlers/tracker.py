from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

def setup_tracker_handlers(tracker_service):
    @router.message(Command("tracker"))
    async def start_tracker_handler(message: Message):
        user_id = message.from_user.id

        parts = message.text.split(maxsplit=1)
        if len(parts) > 2:
            await message.answer(
                "❗ Укажи цель\n"
                "Пример:\n"
                "/tracker username\n"
                "/tracker 123456789"
            )

            return
        
        target = parts[1].strip()

        try:
            await tracker_service.start(user_id, target)
            await message.answer(f"🛰 Трекер запущен для: {target}")
        except RuntimeError as e:
            await message.answer(str(e))
