from core import tasks
from tracker import run_tracker
from utils.telegram import resolve_target


class TrackerService:
    def __init__(self, bot, session_manager):
        self.bot = bot
        self.session_manager = session_manager

    async def notify(self, user_id: int, text: str):
        await self.bot.send_message(user_id, text, parse_mode ="HTML")

    async def start(self, user_id: int, target: str):
        if tasks.is_tracker_running(user_id):
            raise RuntimeError("❗ Tracker already running")

        client = await self.session_manager.get_client(user_id)

        if not client:
            raise RuntimeError("❌ Сессия не найдена.\n"
                "Сначала авторизуйтесь с помощью команды /start.")

        # 🔥 ПРОВЕРЯЕМ ЦЕЛЬ ДО СТАРТА
        entity = await resolve_target(client, target)
        if not entity:
            raise RuntimeError(
                "❌ Target not found.\n"
                "User must be visible to your account or use valid user ID."
            )

        target_id = entity.id
        target_name = entity.username or entity.first_name or str(target_id)

        coro = run_tracker(
            client=client,
            target_id=target_id,
            target_name=target_name,
            owner_id=user_id,
            notify=self.notify
        )

        tasks.start_tracker(user_id, coro)

    async def stop(self, user_id:int):
        stopped = tasks.stop_tracker(user_id)
        if not stopped:
            raise RuntimeError("❗ У тебя нет запущенного трекера")
