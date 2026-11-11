from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
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


def get_main_menu_keyboard(web_app_url: str = None) -> InlineKeyboardMarkup:
    """Главное меню с быстрым доступом ко всему"""
    buttons = []
    
    if web_app_url:
        buttons.append([
            InlineKeyboardButton(text="🚀 Открыть Mini App", web_app=WebAppInfo(url=web_app_url))
        ])
    
    buttons.extend([
        [
            InlineKeyboardButton(text="👤 Мой Профиль", callback_data="show_profile"),
            InlineKeyboardButton(text="⚙️ Управление SaveMod", callback_data="toggle_savemod")
        ],
        [
            InlineKeyboardButton(text="🤖 Создать бота", callback_data="create_bot"),
            InlineKeyboardButton(text="📕 Инструкция", url="https://teletype.in/@zakiiq/yJ1Gx4dEEV5")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard(user) -> InlineKeyboardMarkup:
    """Клавиатура профиля со всеми твоими кнопками + возврат в меню"""
    buttons = []

    sm_text = "🔴 Выключить SaveMod" if user.savemod_enabled else "🟢 Включить SaveMod"
    buttons.append([InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить бота", callback_data="create_bot")])

    # Кнопка трекера только для full-режима и только если запущен
    from core import tasks
    if getattr(user, 'connection_type', 'full') == "full" and tasks.is_tracker_running(user.bot_user_id):
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])

    buttons.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_main")]
    ])
