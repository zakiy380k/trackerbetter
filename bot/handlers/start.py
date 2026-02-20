from aiogram import Router, F 
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton



router = Router()
_session_manager = None

agreement_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="I Agree", callback_data="agree")]
    ]
)


def setup_start_handlers(shared_session_manager):
    global _session_manager
    _session_manager = shared_session_manager
@router.message(F.text == "/start")
async def start_command_handler(message: Message):

    user_id = message.from_user.id

    if not await _session_manager.has_session(user_id):
        await message.answer(
            "Welcome to the Tracker Bot!\n\n"
            "By using this bot, you agree to the terms and conditions of tracking user statuses. "
            "Please ensure you have permission to track the users you are interested in.\n\n"
            "Click 'I Agree' to proceed.",
            reply_markup=agreement_kb
        )
    else:
        await message.answer("✅ Ты уже авторизован. Можно запускать трекер.\n"\
                             "Начните работу с ботом через /tracker или /savemod_on")


