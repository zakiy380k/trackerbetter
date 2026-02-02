from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_code_keyboard():
    keyboard = InlineKeyboardBuilder()

    for digit in range(1,10):
        keyboard.button(text=str(digit),
                         callback_data=f"digit:{digit}")
        
    keyboard.button(text="⌫", callback_data="backspace")
    keyboard.button(text="0", callback_data="digit:0")
    keyboard.button(text="✅", callback_data="confirm")
    keyboard.adjust(3,3,3,3,3)
    return keyboard.as_markup()