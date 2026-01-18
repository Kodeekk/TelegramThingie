from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Session(Base):
    """Model for chat sessions."""

    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(String(100), nullable=False, index=True)
    chat_id = Column(String(50), nullable=False, index=True)
    context_id = Column(String(100), nullable=True)
    messages_ai = Column(JSON, nullable=True)
    messages_client = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    """Model for individual messages within a session."""

    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("sessions.session_id"), nullable=False, index=True
    )

    message_type = Column(String(20), nullable=False)  # 'incoming' or 'outgoing'
    sender = Column(String(50), nullable=True)
    text = Column(Text, nullable=False)

    telegram_message_id = Column(String(50), nullable=True)
    telegram_response = Column(JSON, nullable=True)

    status = Column(String(20), nullable=False)  # 'success' or 'failed'
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    session = relationship("Session", back_populates="messages")


class BusinessClient(Base):
    """Model for business clients (optional, for multi-tenant scenarios)."""

    __tablename__ = "business_clients"

    client_id = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String(255), nullable=False)
    bot_token = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    client_metadata = Column(JSON, nullable=True)
