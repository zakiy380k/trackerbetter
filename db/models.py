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
    func,          
)
from db.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)

    # ID пользователя бота (aiogram)
    bot_user_id = Column(BigInteger, unique=True, nullable=False)

    # Телефон (только для full-режима)
    phone = Column(String, nullable=True)

    # StringSession Telethon (только для full-режима)
    session_string = Column(Text, nullable=True)

    savemod_enabled = Column(Boolean, default=True)

    # "full"     — полная регистрация через Telethon
    # "business" — Business Connection (только SaveMod, без Telethon)
    connection_type = Column(String, default="full", nullable=False)

    # ID бизнес-подключения (только для connection_type == "business")
    business_connection_id = Column(String, nullable=True, index=True)


class SavedMessage(Base):
    __tablename__ = "saved_messages"

    id = Column(Integer, primary_key=True)

    owner_bot_id = Column(
        BigInteger,
        ForeignKey("user_sessions.bot_user_id"),
        index=True,
        nullable=False,
    )

    chat_id = Column(BigInteger, index=True)
    message_id = Column(BigInteger, index=True)
    sender_id = Column(BigInteger)
    text = Column(Text)
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
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(timezone.utc)
    )




class UserBot(Base):
    __tablename__ = "user_bots"

    id = Column(Integer, primary_key=True, autoincrement=True)

    owner_id = Column(BigInteger, nullable=False, index=True)           # telegram user id
    token = Column(String, unique=True, nullable=False)
    
    username = Column(String, nullable=True, index=True)                # @username
    title = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    # Дополнительные полезные поля
    is_polling = Column(Boolean, default=True)          # polling или webhook
    last_started_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    def __repr__(self):
        return f"<UserBot {self.username} (owner={self.owner_id})>"