from email.mime import message

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.states.auth import AuthState
from core.auth_service import AuthService
from bot.keyboards.code_keyboard import build_code_keyboard
import re

router = Router()


_auth_service = None

def setup_auth_handlers(shared_auth_service):
    global _auth_service
    # Здесь мы связываем хендлеры с общим менеджером сессий
    _auth_service = shared_auth_service

@router.callback_query(lambda c: c.data == "login")
async def start_login(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📱 Введите номер телефона (+380...)")
    await state.set_state(AuthState.phone)


@router.message(AuthState.phone)
async def handle_phone(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    user_id = message.from_user.id

    if not re.match(r'^\+\d{10,15}$', phone):
        await message.answer(
            "⚠️ <b>Неверный формат номера!</b>\n\n"
            "Пожалуйста, введите номер в международном формате, "
            "начиная с плюса, например: <code>+380997403928</code>",
            parse_mode="HTML"
        )
        return
    try:
        phone_code_hash = await _auth_service.send_code(user_id, phone)

        await state.update_data(phone=phone, phone_code_hash=phone_code_hash)
        await state.set_state(AuthState.code)

        await message.answer("📩 Код отправлен. Введите код из Telegram.", reply_markup=build_code_keyboard())
    except Exception as e:
        error_str = str(e).lower()
        if "phone number is invalid" in error_str or "invalid" in error_str:
            await message.answer("⚠️ Неверный номер телефона. Попробуйте ещё раз.")
        else:
            await message.answer("❌ Ошибка при отправке кода. Попробуйте позже.")

@router.message(AuthState.code)
async def handle_code(message:Message, state: FSMContext):
    data = await state.get_data()
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    code = message.text.strip()
    user_id = message.from_user.id

    await _auth_service.sign_in(user_id,phone, 
                               code, 
                               phone_code_hash)

    await message.answer('Connected')
    await state.clear()



@router.callback_query(AuthState.code, lambda c: c.data.startswith("digit:"))
async def handle_digit(call:CallbackQuery, state: FSMContext):
    digit = call.data.split(":")[1]
    data = await state.get_data()
    code = data.get("code", "")
    if len(code) < 6:
        code += digit

    await state.update_data(code=code)

    await call.message.edit_text(
        text=f"Введите код: {code}",
        reply_markup=build_code_keyboard()
    )

    await call.answer()

@router.callback_query(AuthState.code, lambda c: c.data == "backspace")
async def handle_backspace(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get("code", "")

    code = code[:-1]

    await state.update_data(code=code)

    await call.message.edit_text(
        text=f"Введите код: {code}",
        reply_markup=build_code_keyboard()
    )

    await call.answer()



@router.callback_query(AuthState.code, lambda c: c.data == "confirm")
async def handle_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    code = data.get("code", "")
    user_id = call.from_user.id

    if not code:
        await call.answer("Код пустой", show_alert=True)
        return

    try:
        result = await _auth_service.sign_in(
            user_id=user_id,
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )

        if result == "OK":
            await state.clear()

            await call.message.edit_text(
                "✅ Авторизация успешна!\n" \
                "Начните работу с ботом через /tracker или /savemod_on"
            )
        if result == "PASSWORD_REQUIRED":
            await state.set_state(AuthState.password)
            await call.message.edit_text(
                "🔐 У вас включена двухфакторная защита.\n"
                "Введите пароль от Telegram.\n\n"
                "⚠️ Пароль не сохраняется."
            )
            return    

    except Exception as e:
        await call.answer("❌ Ошибка входа", show_alert=True)
        # можно оставить код, чтобы пользователь исправил
        print(e)

@router.message(AuthState.password)
async def handle_password(message: Message, state: FSMContext):
    password = message.text.strip()
    user_id = message.from_user.id

    try:
        await _auth_service.sign_in_with_password(user_id, password)
        await state.clear()
        await message.answer("✅ Авторизация завершена!\n"\
        "Начните работу с ботом через /tracker или /savemod_on")

    except Exception:
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
