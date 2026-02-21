import datetime
from datetime import timezone
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Boolean,
    Text,
    ForeignKey, 
    DateTime,
)
from db.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)

    # ID пользователя бота (aiogram)
    bot_user_id = Column(BigInteger, unique=True, nullable=False)

    # телефон Telegram user-account
    phone = Column(String, nullable=True)

    # имя session-файла Telethon
    session_string = Column(Text, nullable=True)

    savemod_enabled = Column(Boolean, default=True)

class SavedMessage(Base):
    __tablename__ = "saved_messages"

    id = Column(Integer, primary_key=True)

    # чей это аккаунт (ключ для multi-user)
    owner_bot_id = Column(
        BigInteger,
        ForeignKey("user_sessions.bot_user_id"),
        index=True,
        nullable=False
    )

    # чат Telegram (личка)
    chat_id = Column(BigInteger, index=True)

    # ID сообщения в чате
    message_id = Column(BigInteger, index=True)

    # кто отправил сообщение
    sender_id = Column(BigInteger)

    # текст сообщения
    text = Column(Text)

    # unix timestamp
    date = Column(Integer)

    file_id = Column(String, nullable=True) 

class UserMessageLog(Base):
    __tablename__ = "user_message_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    username = Column(String, nullable=True)
    chat_id = Column(BigInteger)
    message_id = Column(BigInteger)
    text = Column(Text, nullable=True)
    content_type = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(timezone.utc))