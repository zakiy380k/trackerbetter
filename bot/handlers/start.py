from aiogram import Router, F 
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select

from db.models import UserSession
from db.session import AsyncSessionLocal
from core import tasks

router = Router()

_session_manager = None
_tracker_service = None
_savemod_service = None

def setup_start_handlers(shared_session_manager, tracker_service, savemod_service):
    global _session_manager, _tracker_service, _savemod_service
    _session_manager = shared_session_manager
    _tracker_service = tracker_service
    _savemod_service = savemod_service

def get_profile_keyboard(user_id, savemod_enabled):
    """Формирует кнопки на основе текущих статусов"""
    is_running = tasks.is_tracker_running(user_id)
    buttons = []
    
    # Кнопка SaveMod
    sm_text = "🔴 Выключить SaveMod" if savemod_enabled else "🟢 Включить SaveMod"
    buttons.append([InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])
    
    # Кнопка остановки трекера (только если он работает)
    if is_running:
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])
    
    # Кнопка ручного обновления (на всякий случай)
    # buttons.append([InlineKeyboardButton(text="🔄 Обновить данные", callback_data="refresh_profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def update_profile_message(message: Message, user_id: int):
    """Вспомогательная функция для перерисовки профиля"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserSession).where(UserSession.bot_user_id == user_id))
        user = result.scalar_one_or_none()

    if not user:
        return await message.edit_text("Ошибка: профиль не найден.")

    is_running = tasks.is_tracker_running(user_id)
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"
    tr_status = "🟢 Запущен" if is_running else "🔴 Остановлен"

    text = (
        "👤 <b>Твой профиль:</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💾 SaveMod: {sm_status}\n"
        f"📡 Tracker: {tr_status}\n\n"
        
    )
    
    # Редактируем старое сообщение, заменяя текст и кнопки на новые
    await message.edit_text(text, reply_markup=get_profile_keyboard(user_id, user.savemod_enabled), parse_mode="HTML")

@router.message(F.text == "/start")
async def start_command_handler(message: Message):
    user_id = message.from_user.id

    # Проверка сессии
    if not await _session_manager.has_session(user_id):
        agreement_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="I Agree", callback_data="agree")]])
        await message.answer("Добро пожаловать! Подтвердите соглашение.", reply_markup=agreement_kb)
        return

    # 1. Сначала отправляем НОВОЕ сообщение
    # Мы не вызываем здесь update_profile_message, так как она пытается сделать .edit_text()
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserSession).where(UserSession.bot_user_id == user_id))
        user = result.scalar_one_or_none()

    if not user:
        return await message.answer("Ошибка: профиль не найден.")

    is_running = tasks.is_tracker_running(user_id)
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"
    tr_status = "🟢 Запущен" if is_running else "🔴 Остановлен"

    text = (
        "👤 <b>Твой профиль:</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💾 SaveMod: {sm_status}\n"
        f"📡 Tracker: {tr_status}\n\n"
        f"<b>@TrackerZaki_Bot</b>"
    )

    # 2. Используем .answer(), чтобы создать новое сообщение от бота
    await message.answer(
        text, 
        reply_markup=get_profile_keyboard(user_id, user.savemod_enabled), 
        parse_mode="HTML"
    )
# --- CALLBACKS ---

@router.callback_query(F.data == "toggle_savemod")
async def callback_toggle_savemod(callback: CallbackQuery):
    await callback.answer()  # Чтобы убрать "часики" на кнопке
    user_id = callback.from_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserSession).where(UserSession.bot_user_id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            if user.savemod_enabled:
                await _savemod_service.disable(user_id)
            else:
                await _savemod_service.enable(user_id)

    # СРАЗУ ПОСЛЕ ДЕЙСТВИЯ: обновляем это же сообщение
    await update_profile_message(callback.message, user_id)
    await callback.answer("Настройки SaveMod изменены")

@router.callback_query(F.data == "stop_tracker")
async def callback_stop_tracker(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        await _tracker_service.stop(user_id)
        # ОБНОВЛЯЕМ сообщение: кнопка "Остановить" исчезнет, статус сменится
        await update_profile_message(callback.message, user_id)
        await callback.answer("Трекер остановлен")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == "refresh_profile")
async def callback_refresh(callback: CallbackQuery):
    await update_profile_message(callback.message, callback.from_user.id)
    await callback.answer("Обновлено")