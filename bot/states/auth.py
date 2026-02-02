from aiogram.fsm.state import StatesGroup, State
class AuthState(StatesGroup):
    phone = State()
    code = State()
    password = State()