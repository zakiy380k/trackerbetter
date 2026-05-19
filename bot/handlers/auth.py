from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.states.auth import AuthState
from bot.keyboards.code_keyboard import build_code_keyboard
from core.auth_service import AuthService
import re
from config import BOT_TOKEN

router = Router()

_auth_service: AuthService | None = None

# MAIN_BOT_ID = int(BOT_TOKEN.split(":")[0])

# router.message.filter(F.bot.id == MAIN_BOT_ID)

def setup_auth_handlers(shared_auth_service: AuthService):
    global _auth_service
    _auth_service = shared_auth_service


# ====================== СТАРТ АВТОРИЗАЦИИ ======================
@router.callback_query(F.data == "login")
async def start_login(call: CallbackQuery, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        is_persistent=True
    )

    await call.answer()

    await call.message.answer(
        "🔐 Авторизация\n\n"
        "Нажмите кнопку ниже, чтобы отправить свой номер телефона 👇",
        reply_markup=kb
    )

    await state.set_state(AuthState.phone)


# ====================== ОБРАБОТКА НОМЕРА ======================
@router.message(AuthState.phone, F.contact)
async def process_contact(message: Message, state: FSMContext):
    contact = message.contact
    user_id = message.from_user.id

    if contact.user_id and contact.user_id != user_id:
        await message.answer("❌ Пожалуйста, отправьте **свой** контакт.")
        return

    phone = contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone

    await state.update_data(phone=phone)
    await _send_code(message, state, phone)


@router.message(AuthState.phone)
async def handle_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")

    if not re.match(r'^\+\d{10,15}$', phone):
        await message.answer(
            "⚠️ <b>Неверный формат номера!</b>\n\n"
            "Пример: <code>+380997403928</code>",
            parse_mode="HTML"
        )
        return

    await state.update_data(phone=phone)
    await _send_code(message, state, phone)


async def _send_code(message: Message, state: FSMContext, phone: str):
    try:
        phone_code_hash = await _auth_service.send_code(message.from_user.id, phone)
        await state.update_data(phone_code_hash=phone_code_hash, code="")

        await message.answer(
            f"✅ Номер <b>{phone}</b> принят!\n\n"
            f"📩 Код подтверждения был отправлен в Telegram.\n"
            f"Введите его ниже или используйте клавиатуру:",
            reply_markup=build_code_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(AuthState.code)

    except Exception as e:
        print(f"Ошибка send_code: {e}")
        await message.answer("❌ Не удалось отправить код. Попробуйте позже.")


# ====================== ВВОД КОДА ======================
@router.message(AuthState.code)
async def handle_code_text(message: Message, state: FSMContext):
    code = message.text.strip()
    await process_code_input(message, state, code)


@router.callback_query(AuthState.code, F.data.startswith("digit:"))
async def handle_digit(call: CallbackQuery, state: FSMContext):
    digit = call.data.split(":")[1]
    data = await state.get_data()
    code = data.get("code", "")

    if len(code) >= 6:
        await call.answer("Код уже полный", show_alert=True)
        return

    code += digit
    await state.update_data(code=code)

    await _update_code_message(call, code)
    await call.answer()


@router.callback_query(AuthState.code, F.data == "backspace")
async def handle_backspace(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get("code", "")[:-1]

    await state.update_data(code=code)
    await _update_code_message(call, code)
    await call.answer()


@router.callback_query(AuthState.code, F.data == "confirm")
async def handle_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get("code", "")

    if len(code) < 4:   # обычно 5-6 символов
        await call.answer("Код слишком короткий", show_alert=True)
        return

    await process_code_input(call.message, state, code, is_callback=True)


async def _update_code_message(call: CallbackQuery, code: str):
    try:
        await call.message.edit_text(
            text=f"Введите код: <b>{code}</b>",
            reply_markup=build_code_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass  # сообщение не изменилось


# ====================== ОБРАБОТКА КОДА ======================
async def process_code_input(message_or_call_message, state: FSMContext, code: str,user_id ,is_callback: bool = False):
    data = await state.get_data()
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]

    try:
        result = await _auth_service.sign_in(
            user_id=user_id,
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )

        if result == "OK":
            await state.clear()
            text = "✅ Авторизация прошла успешно!\n\nИспользуйте команды:\n/tracker или /savemod_on"
            if is_callback:
                await message_or_call_message.edit_text(text)
            else:
                await message_or_call_message.answer(text)

        elif result == "PASSWORD_REQUIRED":
            await state.set_state(AuthState.password)
            text = "🔐 Включена двухфакторная аутентификация.\n\nВведите пароль от аккаунта:"
            if is_callback:
                await message_or_call_message.edit_text(text)
            else:
                await message_or_call_message.answer(text)

    except Exception as e:
        print(f"Sign in error: {e}")
        error_text = "❌ Неверный код. Попробуйте ещё раз."
        if is_callback:
            await message_or_call_message.edit_text(error_text, reply_markup=build_code_keyboard())
        else:
            await message_or_call_message.answer(error_text, reply_markup=build_code_keyboard())
        await state.update_data(code="")  # сбрасываем код


@router.message(AuthState.password)
async def handle_password(message: Message, state: FSMContext):
    password = message.text.strip()

    try:
        await _auth_service.sign_in_with_password(message.from_user.id, password)
        await state.clear()
        await message.answer("✅ Авторизация успешно завершена!")
    except Exception as e:
        print(e)
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")