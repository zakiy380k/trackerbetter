from telethon import TelegramClient
from config import API_ID, API_HASH

client = TelegramClient("dev_session", API_ID, API_HASH)

async def main():
    await client.start()  # тут Telegram сам спросит код
    print("DEV SESSION READY")

import asyncio
asyncio.run(main())
