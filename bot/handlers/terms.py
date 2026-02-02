from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()

login_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Войти в аккаунт", callback_data="login")]
    ]
)

@router.callback_query(lambda c: c.data == "agree")
async def accept_terms(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "✅ Соглашение принято.\n\n"
        "Следующий шаг — авторизация в Telegram.\n"
        "Нажмите «Войти в аккаунт».",
        reply_markup=login_kb
    )
