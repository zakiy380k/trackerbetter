import os
from telethon import TelegramClient
from config import API_HASH, API_ID
from telethon.errors import SessionPasswordNeededError


class AuthService():
    def __init__(self):
        os.makedirs("sessions", exist_ok=True)   

    async def send_code(self, user_id: int, phone: str):
        print(f"SEND CODE: {phone}")
        client = TelegramClient(
            f"sessions/{user_id}",
            API_ID,
            API_HASH
        )
        await client.connect()

        result = await client.send_code_request(phone=phone)

        await client.disconnect()
        return result.phone_code_hash

    async def sign_in(self, user_id: int,phone:str,code:str, phone_code_hash):
        client = TelegramClient(
            f"sessions/{user_id}",
            API_ID,
            API_HASH
        )

        await client.connect()

        try:

            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            return "OK"
        except SessionPasswordNeededError:
            return "PASSWORD_REQUIRED"
        finally:
            await client.disconnect()   

    async def sign_in_with_password(self, user_id: int, password: str):
        client = TelegramClient(
            f"sessions/{user_id}",
            API_ID,
            API_HASH
        )
    
        await client.connect()
        await client.sign_in(password=password)
        await client.disconnect()