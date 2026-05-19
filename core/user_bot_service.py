import asyncio
import logging
from typing import Dict, Optional, List

from aiogram import Bot, Dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserBot
from db.session import AsyncSessionLocal

class UserBotService:
    def __init__(self, savemod_service, session_manager, dp: Dispatcher):
        self.savemod_service = savemod_service
        self.session_manager = session_manager
        self.dp = dp
        self.running_bots: Dict[int, Bot] = {}
    

    def get_bots_list(self) -> List[Bot]:
        return list(self.running_bots.values())

    async def start_bot(self, user_bot: UserBot):
        if user_bot.id in self.running_bots:
            logging.warning(f"Bot for user {user_bot.bot_user_id} is already running.")
            return
        try:
            bot = Bot(token=user_bot.token)
            
            self.running_bots[user_bot.id] = bot

            task = asyncio.create_task(
                self._listen_bot(bot)
            )

            self.dp.workflow_data[
                f"feed_task_{user_bot.id}"
            ] = task
            logging.info(f"✅ UserBot запущен → @{user_bot.username}")
        except Exception as e:
            logging.error(f"❌ Ошибка при запуске UserBot @{user_bot.username}: {e}")

    async def _listen_bot(self, bot: Bot):
            """Слушатель обновлений для динамически добавленного бота"""
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info(f"📡 Запущен сбор обновлений для бота с токеном {bot.token[:10]}...")
            try:
                # Сбрасываем вебхуки, если они были, чтобы заработал getUpdates
                await bot.delete_webhook(drop_pending_updates=True)
                offset = 0

                while True:
                    try:
                        # Запрашиваем новые апдейты
                        updates = await bot.get_updates(
                            offset=offset,
                            timeout=30,
                            allowed_updates=[
                                "message",
                                "edited_message",
                                "callback_query",
                                "business_connection",
                                "business_message",
                                "edited_business_message",
                                "deleted_business_messages",
                            ]
                        )

                        for update in updates:
                            offset = update.update_id + 1
                            # ВАЖНО: передаем инстанс конкретного бота и сам апдейт!
                            await self.dp.feed_update(bot, update)

                    except Exception as e:
                        logging.error(f"Ошибка при получении обновлений для бота {bot.token[:10]}: {e}")
                        await asyncio.sleep(2) # Защита от бесконечного спама ошибками в цикле

                    await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                logging.info(f"🛑 Прослушивание бота {bot.token[:10]} остановлено.")
    async def stop_bot(self, user_bot_id: int):
        if user_bot_id in self.running_bots:
            bot = self.running_bots.pop(user_bot_id)
            task = self.dp.workflow_data.pop(f"feed_task_{user_bot_id}", None)
            if task:
                task.cancel()

            try:
                await bot.session.close()
            except:
                pass
            logging.info(f"🛑 UserBot с ID {user_bot_id} остановлен.")



    async def load_all_bots(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserBot).where(UserBot.is_active == True)
            )

            active_bots = result.scalars().all()

            for user_bot in active_bots:
                try:
                    bot = Bot(token=user_bot.token)

                    self.running_bots[user_bot.id] = bot

                    # запускаем listener
                    task = asyncio.create_task(
                        self._listen_bot(bot)
                    )

                    self.dp.workflow_data[
                        f"feed_task_{user_bot.id}"
                    ] = task

                    logging.info(
                        f"✅ UserBot @{user_bot.username} загружен"
                    )

                except Exception as e:
                    logging.error(
                        f"❌ Ошибка запуска @{user_bot.username}: {e}"
                    )

    async def add_bot(self, owner_id: int, token: str) -> Optional[UserBot]:
        test_bot = Bot(token=token)
        try:
            me = await test_bot.get_me()
            await test_bot.session.close()

            async with AsyncSessionLocal() as session:
                user_bot = UserBot(
                    owner_id=owner_id,
                    token=token,
                    username=me.username,
                    title=me.first_name or me.username,
                    is_active=True
                )
                session.add(user_bot)
                await session.commit()
                await session.refresh(user_bot)

            bot = Bot(token=user_bot.token)
            self.running_bots[user_bot.id] = bot

            self.dp.workflow_data[f"feed_task_{user_bot.id}"] = asyncio.create_task(self._listen_bot(bot))
            

            return user_bot
        except Exception as e:
            logging.error(f"❌ Ошибка при добавлении UserBot: {e}")
            return None