from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import UserSession

forum_router = Router()

async def _validate_forum_chat(bot:Bot, chat_id:int) -> tuple[bool, str, str]:
    try: 
        chat = await bot.get_chat(chat_id)
    except TelegramAPIError as e: 
        return False, "", f"Не удалось получить данные чата: {e}"
    
    if not getattr(chat, "is_forum", False):
        return False, "", "Этот чат не является форумом"
    

    try:
        member = await bot.get_chat_member(chat_id, bot.id)
    except TelegramAPIError as e:
        return False, "", f"❌ Не удалось проверить права бота в группе: {e}"

    status = getattr(member, "status", None)
    if status not in ("administrator", "creator"):
        return False, "", "❌ Сделай бота администратором группы."

    if status == "administrator" and not getattr(member, "can_manage_topics", False):
        return False, "", "❌ Выдай боту право **Manage Topics (Управление темами)**."

    title = getattr(chat, "title", None) or str(chat_id)
    return True, title, ""


@forum_router.message(Command("setforum"))
async def cmd_set_forum(message: Message, command: CommandObject, bot: Bot):
    owner_id = message.from_user.id if message.from_user else None
    if not owner_id:
        return

    target_chat_id: int | None = None

    if message.chat.type in ("group", "supergroup"):
        target_chat_id = message.chat.id
    elif command.args:
        raw_arg = command.args.strip().split()[0]
        try:
            target_chat_id = int(raw_arg)
        except ValueError:
            await message.reply("❌ Укажи числовой ID форум-группы: <code>/setforum -100...</code>", parse_mode="HTML")
            return
    else:
        await message.reply(
            "Напиши <code>/setforum</code> прямо в своей форум-группе с темами "
            "или передай ID группы: <code>/setforum -100...</code>",
            parse_mode="HTML",
        )
        return

    ok, title, err_text = await _validate_forum_chat(bot, target_chat_id)
    if not ok:
        await message.reply(err_text, parse_mode="HTML")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == owner_id)
        )
        user_session = res.scalar_one_or_none()
        if not user_session:
            user_session = UserSession(
                bot_user_id=owner_id,
                savemod_enabled=True,
                connection_type="business",
                custom_forum_chat_id=target_chat_id,
                custom_forum_enabled=True,
            )
            session.add(user_session)
        else:
            user_session.custom_forum_chat_id = target_chat_id
            user_session.custom_forum_enabled = True

        await session.commit()

    await message.reply(
        f"✅ Форум-группа привязана!\n"
        f"<b>Группа:</b> {title}\n"
        f"<b>ID:</b> <code>{target_chat_id}</code>\n\n"
        f"Топики для пользователей будут создаваться автоматически при первом удалении сообщения.",
        parse_mode="HTML",
    )


@forum_router.message(Command("unsetforum"))
async def cmd_unset_forum(message: Message):
    owner_id = message.from_user.id if message.from_user else None
    if not owner_id:
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == owner_id)
        )
        user_session = res.scalar_one_or_none()
        if user_session:
            user_session.custom_forum_enabled = False
            user_session.custom_forum_chat_id = None
            await session.commit()

    await message.reply("✅ Привязка форум-группы отключена.")