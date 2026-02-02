from telethon import TelegramClient
from config import API_ID, API_HASH
import os
from pathlib import Path

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

class SessionManager:
    def __init__(self,):
        self.clients: dict[int, TelegramClient] = {}

    def session_path(self, user_id:int) -> Path:
        return SESSIONS_DIR / f"{user_id}.session"
    
    def has_session(self, user_id:int) -> bool:
        return self.session_path(user_id).exists()
    
    async def get_client(self, user_id: int) -> TelegramClient:
        if user_id in self.clients:
            return self.clients[user_id]
        
        session_file = self.session_path(user_id)

        if not session_file.exists():
            return None
        
        client = TelegramClient(
            session=str(session_file),
            api_id=API_ID,
            api_hash=API_HASH,
            flood_sleep_threshold=60
        )

        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        
        self.clients[user_id] = client
        return client


    async def logout(self, user_id:int):
        client = self.clients.pop(user_id, None)

        if client:
            await client.log_out()
            await client._disconnect()

        session_file = self.session_path(user_id)
        if session_file.exists():
            session_file.unlink()