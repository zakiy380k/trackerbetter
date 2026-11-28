from html import escape
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from sqlalchemy import select, delete

from db.session import AsyncSessionLocal
from db.models import UserForumTopic

class ForumTopicManager:
    def __init__(self, bot:Bot):
        self.bot = bot
        self._cache: dict[tuple[int, str, int], tuple[int, int]] = {}

    @staticmethod
    def build_topic_name(user_name:str, target_user_id:int)->str:
        clean = (user_name or "").replace("\n", " ").strip()
        id_part = f"ID: {target_user_id}"
        if not clean or clean == f"ID:{target_user_id}":
            return id_part[:128]
        if str(target_user_id) in clean:
            return clean[:128]
        suffix = f" | {id_part}"
        return f"{clean[: 128 - len(suffix)]}{suffix}"
    
    @staticmethod
    def build_user_card(user_name:str, target_user_id:int)-> str:
        safe_name = escape((user_name or "").strip() or f"ID:{target_user_id}")
        return(
            f"👥<b>Карточка Пользователя</b>\n\n"
            f"<blockquote>"
            f"<b>Имя:</b><a href=\"tg://user?id={target_user_id}\">{safe_name}</a>\n"
            f"<b>ID:</b> <code>{target_user_id}</code>"
            f"</blockquote>"
        )
    
    async def _get_from_db(self, owner_bot_id: int, scope: str, target_user_id: int) -> tuple[int, int] | None:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(UserForumTopic).where(
                        UserForumTopic.owner_bot_id == owner_bot_id,
                        UserForumTopic.scope == scope,
                        UserForumTopic.target_user_id == target_user_id,
                    )
                )
                row = res.scalar_one_or_none()
                if row:
                    return (row.forum_chat_id, row.message_thread_id)
            return None

    async def _save_to_db(self, owner_bot_id: int, scope: str, forum_chat_id: int, target_user_id: int, thread_id: int):
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(UserForumTopic).where(
                        UserForumTopic.owner_bot_id == owner_bot_id,
                        UserForumTopic.scope == scope,
                        UserForumTopic.target_user_id == target_user_id,
                    )
                )
                row = res.scalar_one_or_none()
                if row:
                    row.forum_chat_id = forum_chat_id
                    row.message_thread_id = thread_id
                else:
                    session.add(
                        UserForumTopic(
                            owner_bot_id=owner_bot_id,
                            scope=scope,
                            forum_chat_id=forum_chat_id,
                            target_user_id=target_user_id,
                            message_thread_id=thread_id,
                        )
                    )
                await session.commit()

    async def _delete_from_db(self, owner_bot_id: int, scope: str, target_user_id: int):
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(UserForumTopic).where(
                    UserForumTopic.owner_bot_id == owner_bot_id,
                    UserForumTopic.scope == scope,
                    UserForumTopic.target_user_id == target_user_id,
                )
            )
            await session.commit()


    async def _create_topic_with_card(
        self,
        owner_bot_id: int,
        scope: str,
        forum_chat_id: int,
        target_user_id: int,
        user_name: str,
    ) -> int:
        topic_name = self.build_topic_name(user_name, target_user_id)
        topic = await self.bot.create_forum_topic(
            chat_id=forum_chat_id,
            name=topic_name,
        )
        thread_id = topic.message_thread_id

        # Отправляем и закрепляем карточку пользователя вверху топика
        try:
            card_msg = await self.bot.send_message(
                chat_id=forum_chat_id,
                message_thread_id=thread_id,
                text=self.build_user_card(user_name, target_user_id),
                parse_mode="HTML",
            )
            try:
                await self.bot.pin_chat_message(
                    chat_id=forum_chat_id,
                    message_id=card_msg.message_id,
                    disable_notification=True,
                )
            except TelegramAPIError:
                pass
        except TelegramAPIError:
            pass

        self._cache[(owner_bot_id, scope, target_user_id)] = (forum_chat_id, thread_id)
        await self._save_to_db(owner_bot_id, scope, forum_chat_id, target_user_id, thread_id)
        return thread_id

    async def get_or_create_thread(
        self,
        owner_bot_id: int,
        scope: str,
        forum_chat_id: int,
        target_user_id: int,
        user_name: str,
    ) -> int:
        key = (owner_bot_id, scope, target_user_id)
        cached = self._cache.get(key)
        if cached and cached[0] == forum_chat_id:
            return cached[1]

        db_val = await self._get_from_db(owner_bot_id, scope, target_user_id)
        if db_val and db_val[0] == forum_chat_id:
            self._cache[key] = db_val
            return db_val[1]

        return await self._create_topic_with_card(
            owner_bot_id=owner_bot_id,
            scope=scope,
            forum_chat_id=forum_chat_id,
            target_user_id=target_user_id,
            user_name=user_name,
        )

    @staticmethod
    def _is_topic_missing_error(exc: TelegramBadRequest) -> bool:
        msg = exc.message.lower()
        return any(
            token in msg
            for token in ("thread not found", "topic_deleted", "topic deleted", "message thread")
        )

    async def send_to_topic(
        self,
        owner_bot_id: int,
        scope: str,
        forum_chat_id: int,
        target_user_id: int,
        user_name: str,
        send_fn,
    ):
        """
        send_fn(thread_id: int) -> выполняет отправку в forum_chat_id с message_thread_id=thread_id.
        Если топик был удалён — пересоздаёт с карточкой и повторяет отправку.
        """
        thread_id = await self.get_or_create_thread(
            owner_bot_id=owner_bot_id,
            scope=scope,
            forum_chat_id=forum_chat_id,
            target_user_id=target_user_id,
            user_name=user_name,
        )
        try:
            return await send_fn(thread_id)
        except TelegramBadRequest as exc:
            if not self._is_topic_missing_error(exc):
                raise
            self._cache.pop((owner_bot_id, scope, target_user_id), None)
            await self._delete_from_db(owner_bot_id, scope, target_user_id)
            new_thread_id = await self._create_topic_with_card(
                owner_bot_id=owner_bot_id,
                scope=scope,
                forum_chat_id=forum_chat_id,
                target_user_id=target_user_id,
                user_name=user_name,
            )
            return await send_fn(new_thread_id)