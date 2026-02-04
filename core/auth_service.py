import os
from telethon import TelegramClient
from config import API_HASH, API_ID
from telethon.errors import SessionPasswordNeededError

from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import UserSession

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

    async def sign_in(self, user_id: int, phone: str, code: str, phone_code_hash):
        client = TelegramClient(
            f"sessions/{user_id}",
            API_ID,
            API_HASH
        )

        await client.connect()

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            # ==========================
            # 🔥 ВОТ ЗДЕСЬ СОЗДАЁТСЯ UserSession
            # ==========================
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserSession).where(
                        UserSession.bot_user_id == user_id
                    )
                )
                user = result.scalar_one_or_none()

                if not user:
                    user = UserSession(
                        bot_user_id=user_id,
                        phone=phone,
                        session_name=f"sessions/{user_id}",
                        savemod_enabled=False
                    )
                    session.add(user)
                    await session.commit()

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
        try:
            await client.sign_in(password=password)
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserSession).where(
                        UserSession.bot_user_id == user_id
                    )
                )
                user = result.scalar_one_or_none()

                if not user:
                    user = UserSession(
                        bot_user_id = user_id,
                        phone = None,
                        session_name =  f"sessions/{user_id}",
                        savemod_enabled = False
                    )
                    session.add(user)
                
                    await session.commit()
            return "OK"
        except Exception as e:
            print(f"Auth Error for {user_id}: {e}") # Логируем реальную ошибку
            raise e
        finally:
            await client.disconnect()