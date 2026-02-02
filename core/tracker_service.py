from core import tasks
from tracker import run_tracker

class TrackerService:
    def __init__(self, bot, session_manager):
        self.bot = bot
        self.session_manager = session_manager

    async def notify(self, user_id: int, text: str):
        await self.bot.send_message(user_id, text)

    async def start(self, user_id: int, target: str):
        if tasks.is_tracker_running(user_id):
            raise RuntimeError("Tracker already running")

        client = await self.session_manager.get_client(user_id)

        coro = run_tracker(
            client=client,
            target=target,
            owner_id=user_id,
            notify=self.notify
        )

        tasks.start_tracker(user_id, coro)
