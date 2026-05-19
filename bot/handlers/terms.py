from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN
router = Router()

# MAIN_BOT_ID = int(BOT_TOKEN.split(":")[0])

# router.message.filter(F.bot.id == MAIN_BOT_ID)

login_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Войти в аккаунт", callback_data="login")]
    ]
)

@router.callback_query(lambda c: c.data == "agree")
async def accept_terms(call: CallbackQuery):
    await call.answer()
    
    await call.message.answer(
        "✅ Полное подключение.\n\n"
        "Следующий шаг — авторизация в Telegram.\n"
        "Нажмите «Войти в аккаунт».",
        reply_markup=login_kb
    )
