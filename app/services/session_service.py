from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Message, Session


class SessionService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.active_sessions: Dict[tuple[str, str], int] = {}

    async def get_or_create_session(self, bot_id: str, chat_id: str) -> int:
        cache_key = (bot_id, chat_id)
        if cache_key in self.active_sessions:
            return self.active_sessions[cache_key]

        async with self.session_factory() as db_session:
            recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

            result = await db_session.execute(
                select(Session)
                .where(Session.bot_id == bot_id)
                .where(Session.chat_id == chat_id)
                .where(Session.updated_at >= recent_time)
                .order_by(Session.updated_at.desc())
            )
            session = result.scalar_one_or_none()

            if session:
                session_id = session.session_id
            else:
                new_session = Session(
                    bot_id=bot_id, chat_id=chat_id, messages_ai=[], messages_client=[]
                )
                db_session.add(new_session)
                await db_session.commit()
                await db_session.refresh(new_session)
                session_id = new_session.session_id

            self.active_sessions[cache_key] = session_id
            return session_id

    async def add_message_to_session(
        self,
        session_id: int,
        text: str,
        message_type: str,
        sender: Optional[str] = None,
        telegram_message_id: Optional[str] = None,
        telegram_response: Optional[Dict] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> int:
        async with self.session_factory() as db_session:
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

            result = await db_session.execute(
                select(Session).where(Session.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.updated_at = datetime.now(timezone.utc)

            await db_session.commit()
            await db_session.refresh(message)
            return message.message_id

    async def get_session_messages(self, session_id: int) -> Optional[Dict[str, Any]]:
        async with self.session_factory() as db_session:
            result = await db_session.execute(
                select(Session).where(Session.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            result = await db_session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
            )
            messages = result.scalars().all()

            return {
                "session_id": session.session_id,
                "bot_id": session.bot_id,
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

    async def get_all_sessions(
        self, chat_id: Optional[str] = None, bot_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self.session_factory() as db_session:
            query = (
                select(Session)
                .options(selectinload(Session.messages))
                .order_by(Session.updated_at.desc())
            )

            if bot_id:
                query = query.where(Session.bot_id == bot_id)
            if chat_id:
                query = query.where(Session.chat_id == chat_id)

            result = await db_session.execute(query)
            sessions = result.scalars().unique().all()

            return [
                {
                    "session_id": s.session_id,
                    "bot_id": s.bot_id,
                    "chat_id": s.chat_id,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": len(s.messages),
                }
                for s in sessions
            ]
