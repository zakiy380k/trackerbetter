import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from config import WEBHOOK_URL, WEBHOOK_PATH


router = Router()


# Обязательные переменные Render
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


@router.message(Command("restart_webhook"))
async def restart_webhook_command(message: Message):
    # Только личные сообщения
    if message.chat.type != ChatType.PRIVATE:
        return

    # Только администратор
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_ID:
        return

    try:
        await message.bot.set_webhook(
            url=WEBHOOK_URL + WEBHOOK_PATH,
            allowed_updates=ALLOWED_UPDATES,
            secret_token=WEBHOOK_SECRET,
        )

        webhook_info = await message.bot.get_webhook_info()

        await message.answer(
            "✅ Webhook обновлён\n\n"
            f"URL: {webhook_info.url}\n"
            f"Pending updates: {webhook_info.pending_update_count}"
        )

    except Exception:
        await message.answer(
            "❌ Не удалось обновить webhook. "
            "Подробности смотри в логах Render."
        )