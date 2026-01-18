# telegram_bot.py
"""
Telegram bot that responds to any chat and organizes messages by sessions
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Session(Base):
    """Model for chat sessions"""

    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(50), nullable=False, index=True)
    context_id = Column(String(100), nullable=True)  # For grouping related sessions
    messages_ai = Column(JSON, nullable=True)  # AI-related message metadata
    messages_client = Column(JSON, nullable=True)  # Client message metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    """Model for individual messages within a session"""

    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("sessions.session_id"), nullable=False, index=True
    )

    # Message details
    message_type = Column(String(20), nullable=False)  # 'incoming' or 'outgoing'
    sender = Column(String(50), nullable=True)  # 'user', 'bot', or username
    text = Column(Text, nullable=False)

    # Telegram-specific data
    telegram_message_id = Column(String(50), nullable=True)
    telegram_response = Column(JSON, nullable=True)

    # Status and metadata
    status = Column(String(20), nullable=False)  # 'success' or 'failed'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    session = relationship("Session", back_populates="messages")


class BusinessClient(Base):
    """Model for business clients (optional, for multi-tenant scenarios)"""

    __tablename__ = "business_clients"

    client_id = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String(255), nullable=False)
    bot_token = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    client_metadata = Column(JSON, nullable=True)


class TelegramMessenger:
    """
    Telegram bot that organizes conversations by sessions.
    """

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///telegram_bot.db",
        echo: bool = False,
    ):
        """
        Initialize the Telegram Messenger.

        Args:
            database_url: SQLAlchemy async database URL
            echo: Whether to echo SQL queries (for debugging)
        """
        self.engine = create_async_engine(database_url, echo=echo, future=True)
        self.SessionLocal = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.last_update_id = 0
        self.active_sessions = {}  # Cache: {chat_id: session_id}

    async def initialize(self):
        """Create database tables if they don't exist"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_or_create_session(self, chat_id: str) -> int:
        """
        Get existing active session or create a new one for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            session_id
        """
        # Check cache first
        if chat_id in self.active_sessions:
            return self.active_sessions[chat_id]

        async with self.SessionLocal() as db_session:
            # Try to find recent active session (within last hour, for example)
            from datetime import timedelta

            recent_time = datetime.utcnow() - timedelta(hours=1)

            result = await db_session.execute(
                select(Session)
                .where(Session.chat_id == chat_id)
                .where(Session.updated_at >= recent_time)
                .order_by(Session.updated_at.desc())
            )
            session = result.scalar_one_or_none()

            if session:
                session_id = session.session_id
            else:
                # Create new session
                new_session = Session(
                    chat_id=chat_id, messages_ai=[], messages_client=[]
                )
                db_session.add(new_session)
                await db_session.commit()
                await db_session.refresh(new_session)
                session_id = new_session.session_id

            # Cache it
            self.active_sessions[chat_id] = session_id
            return session_id

    async def add_message_to_session(
        self,
        session_id: int,
        text: str,
        message_type: str,
        sender: str = None,
        telegram_message_id: str = None,
        telegram_response: Dict = None,
        status: str = "success",
        error_message: str = None,
    ) -> int:
        """
        Add a message to a session.

        Args:
            session_id: The session ID
            text: Message text
            message_type: 'incoming' or 'outgoing'
            sender: Who sent the message
            telegram_message_id: Telegram's message ID
            telegram_response: Full Telegram API response
            status: 'success' or 'failed'
            error_message: Error message if failed

        Returns:
            message_id
        """
        async with self.SessionLocal() as db_session:
            message = Message(
                session_id=session_id,
                message_type=message_type,
                sender=sender,
                text=text,
                telegram_message_id=telegram_message_id,
                telegram_response=telegram_response,
                status=status,
                error_message=error_message,
            )
            db_session.add(message)

            # Update session's updated_at timestamp
            result = await db_session.execute(
                select(Session).where(Session.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.updated_at = datetime.utcnow()

            await db_session.commit()
            await db_session.refresh(message)
            return message.message_id

    async def get_session_messages(self, session_id: int) -> Dict[str, Any]:
        """
        Get all messages for a session in the structured format.

        Returns:
            {
                "session_id": int,
                "messages": [
                    {
                        "message_id": int,
                        "type": str,
                        "sender": str,
                        "text": str,
                        "created_at": datetime,
                        ...
                    }
                ],
                "created_at": datetime,
                "updated_at": datetime
            }
        """
        async with self.SessionLocal() as db_session:
            # Get session
            result = await db_session.execute(
                select(Session).where(Session.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            # Get all messages
            result = await db_session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
            )
            messages = result.scalars().all()

            return {
                "session_id": session.session_id,
                "chat_id": session.chat_id,
                "context_id": session.context_id,
                "messages": [
                    {
                        "message_id": msg.message_id,
                        "type": msg.message_type,
                        "sender": msg.sender,
                        "text": msg.text,
                        "status": msg.status,
                        "created_at": msg.created_at.isoformat(),
                        "telegram_message_id": msg.telegram_message_id,
                    }
                    for msg in messages
                ],
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
            }

    async def send_message(
        self,
        bot_token: str,
        chat_id: str,
        message: str,
        session_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a message via Telegram API and store it in the session structure.

        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat ID
            message: Message text to send
            session_id: Optional session ID (will be created if not provided)

        Returns:
            Dictionary with status, response, session_id, and message_id
        """
        # Get or create session
        if session_id is None:
            session_id = await self.get_or_create_session(chat_id)

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}

        result = {
            "status": "failed",
            "response": None,
            "error": None,
            "session_id": session_id,
            "message_id": None,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                response_data = response.json()

                result["status"] = "success"
                result["response"] = response_data

                # Store message in session
                telegram_msg_id = str(
                    response_data.get("result", {}).get("message_id", "")
                )
                message_id = await self.add_message_to_session(
                    session_id=session_id,
                    text=message,
                    message_type="outgoing",
                    sender="bot",
                    telegram_message_id=telegram_msg_id,
                    telegram_response=response_data,
                    status="success",
                )
                result["message_id"] = message_id

        except httpx.HTTPStatusError as e:
            result["error"] = (
                f"HTTP error: {e.response.status_code} - {e.response.text}"
            )
            message_id = await self.add_message_to_session(
                session_id=session_id,
                text=message,
                message_type="outgoing",
                sender="bot",
                status="failed",
                error_message=result["error"],
            )
            result["message_id"] = message_id
        except Exception as e:
            result["error"] = str(e)
            message_id = await self.add_message_to_session(
                session_id=session_id,
                text=message,
                message_type="outgoing",
                sender="bot",
                status="failed",
                error_message=result["error"],
            )
            result["message_id"] = message_id

        return result

    async def get_updates(
        self, bot_token: str, offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get updates from Telegram API (new messages).

        Args:
            bot_token: Telegram bot token
            offset: Update ID to start from (for getting only new updates)

        Returns:
            Dictionary with updates
        """
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        params = {
            "timeout": 30,  # Long polling timeout
            "offset": offset,
        }

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error getting updates: {e}")
            return {"ok": False, "result": []}

    async def start_polling(self, bot_token: str, on_message_callback=None):
        """
        Start polling for new messages and automatically respond.

        Args:
            bot_token: Telegram bot token
            on_message_callback: Optional custom callback function to handle messages.
                                Should accept (session_id, chat_id, message_text, user_info)
                                and return response text
        """
        print("🤖 Bot started! Waiting for messages...")
        print("💬 Send a message to your bot on Telegram to test it")
        print("Press Ctrl+C to stop\n")

        while True:
            try:
                # Get new updates
                updates = await self.get_updates(
                    bot_token, offset=self.last_update_id + 1
                )

                if updates.get("ok") and updates.get("result"):
                    for update in updates["result"]:
                        # Update the offset to mark this update as processed
                        self.last_update_id = update["update_id"]

                        # Extract message data
                        if "message" in update and "text" in update["message"]:
                            message = update["message"]
                            chat_id = str(message["chat"]["id"])
                            message_text = message["text"]
                            telegram_msg_id = str(message["message_id"])
                            user_info = {
                                "first_name": message["from"].get("first_name", ""),
                                "last_name": message["from"].get("last_name", ""),
                                "username": message["from"].get("username", ""),
                                "user_id": message["from"].get("id", ""),
                            }

                            # Get or create session for this chat
                            session_id = await self.get_or_create_session(chat_id)

                            # Store incoming message
                            await self.add_message_to_session(
                                session_id=session_id,
                                text=message_text,
                                message_type="incoming",
                                sender=user_info.get("username")
                                or user_info.get("first_name")
                                or "user",
                                telegram_message_id=telegram_msg_id,
                                telegram_response=message,
                                status="success",
                            )

                            print(
                                f"📨 [Session {session_id}] Received from {user_info['first_name']}: {message_text}"
                            )

                            # Generate response
                            if on_message_callback:
                                response_text = on_message_callback(
                                    session_id, chat_id, message_text, user_info
                                )
                            else:
                                # Default auto-reply
                                response_text = self._default_response(
                                    message_text, user_info
                                )

                            # Send response (will be stored automatically in session)
                            result = await self.send_message(
                                bot_token=bot_token,
                                chat_id=chat_id,
                                message=response_text,
                                session_id=session_id,
                            )

                            if result["status"] == "success":
                                print(
                                    f"✅ [Session {session_id}] Replied: {response_text}\n"
                                )
                            else:
                                print(
                                    f"❌ [Session {session_id}] Failed to send reply: {result['error']}\n"
                                )

                # Small delay to avoid hammering the API
                await asyncio.sleep(1)

            except KeyboardInterrupt:
                print("\n👋 Bot stopped by user")
                break
            except Exception as e:
                print(f"❌ Error in polling loop: {e}")
                await asyncio.sleep(5)  # Wait a bit before retrying

    def _default_response(self, message_text: str, user_info: Dict) -> str:
        """
        Generate a default response to incoming messages.

        Args:
            message_text: The text of the incoming message
            user_info: Dictionary with user information

        Returns:
            Response text to send back
        """
        name = user_info.get("first_name", "there")

        # Simple echo bot with greeting
        if message_text.lower() in ["/start", "/hello", "hello", "hi"]:
            return f"👋 Hello {name}! I'm your bot. How can I help you today?"
        elif message_text.lower() in ["/help", "help"]:
            return "🤖 I'm a simple bot. I'll echo back whatever you send me!\n\nTry sending me any message!"
        elif message_text.lower() == "/session":
            return "📊 Your messages are being organized in sessions. Each conversation is tracked!"
        else:
            return f"You said: {message_text}"

    async def get_all_sessions(
        self, chat_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all sessions, optionally filtered by chat_id.

        Args:
            chat_id: Optional chat ID to filter by

        Returns:
            List of session dictionaries
        """
        async with self.SessionLocal() as db_session:
            query = select(Session).order_by(Session.updated_at.desc())

            if chat_id:
                query = query.where(Session.chat_id == chat_id)

            result = await db_session.execute(query)
            sessions = result.scalars().all()

            return [
                {
                    "session_id": s.session_id,
                    "chat_id": s.chat_id,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": len(s.messages),
                }
                for s in sessions
            ]

    async def close(self):
        """Close database connections"""
        await self.engine.dispose()


# Example usage
async def main():
    # Your bot token from @BotFather
    BOT_TOKEN = ""

    # Initialize the bot
    bot = TelegramMessenger()
    await bot.initialize()
    print("✅ Database initialized\n")

    # Optional: Define custom message handler
    def custom_handler(session_id, chat_id, message_text, user_info):
        """Custom function to generate responses"""
        name = user_info.get("first_name", "Friend")

        if "hello" in message_text.lower() or "hi" in message_text.lower():
            return f"Hey {name}! 👋 Nice to hear from you! (Session #{session_id})"
        elif "how are you" in message_text.lower():
            return "I'm doing great! Thanks for asking 😊"
        elif "bye" in message_text.lower():
            return f"Goodbye {name}! Have a wonderful day! 👋"
        else:
            return f"Thanks for your message: '{message_text}'"

    # Start the bot with custom handler
    try:
        await bot.start_polling(BOT_TOKEN, on_message_callback=custom_handler)
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
