from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

def setup_tracker_handlers(tracker_service, savemod_service):
    @router.message(Command("tracker"))
    async def start_tracker_handler(message: Message):
        parts = message.text.split(maxsplit=1)
    
        if len(parts) < 2 or not parts[1].strip:
            await message.answer(
                "❗ Укажи цель\n"
                "/tracker username\n"
                "/tracker user_id"
            )
            return
    
        target = parts[1].strip()
    
        try:
            await tracker_service.start(message.from_user.id, target)
            await message.answer("✅ Трекер запущен")
        except RuntimeError as e:
            await message.answer(str(e))

    @router.message(Command("stop"))
    async def stop_tracker_handler(message:Message):
        user_id = message.from_user.id
        try:
            await tracker_service.stop(user_id)

        except RuntimeError as e:
            await message.answer(str(e))


    @router.message(F.text == "/savemod_on")
    async def savemod_on_handler(message: Message):
        await savemod_service.enable(message.from_user.id)
        await message.answer("✅ SaveMod включён")