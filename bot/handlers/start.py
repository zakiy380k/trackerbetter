from aiogram import Router, F 
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from core.session_manager import SessionManager

router = Router()
session_manager = SessionManager()

agreement_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="I Agree", callback_data="agree")]
    ]
)

@router.message(F.text == "/start")
async def start_command_handler(message: Message):
    user_id = message.from_user.id

    if not session_manager.has_session(user_id):
        await message.answer(
            "Welcome to the Tracker Bot!\n\n"
            "By using this bot, you agree to the terms and conditions of tracking user statuses. "
            "Please ensure you have permission to track the users you are interested in.\n\n"
            "Click 'I Agree' to proceed.",
            reply_markup=agreement_kb
        )
    else:
        await message.answer("✅ Ты уже авторизован. Можно запускать трекер. /tracker")


