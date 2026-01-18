import asyncio
from typing import Any, Dict, Optional

import httpx

from app.services.session_service import SessionService
from app.channels.telegram.client import TelegramClient


class TelegramBot:
    def __init__(
        self, client: TelegramClient, session_service: SessionService, bot_id: str
    ) -> None:
        self.client = client
        self.session_service = session_service
        self.last_update_id = 0
        self.bot_id = bot_id

    async def send_message(
        self, chat_id: str, message: str, session_id: Optional[int] = None
    ) -> Dict[str, Any]:
        if session_id is None:
            session_id = await self.session_service.get_or_create_session(
                self.bot_id, chat_id
            )

        result = {
            "status": "failed",
            "response": None,
            "error": None,
            "session_id": session_id,
            "message_id": None,
        }

        try:
            response_data = await self.client.send_message(chat_id, message)
            result["status"] = "success"
            result["response"] = response_data

            telegram_msg_id = str(response_data.get("result", {}).get("message_id", ""))
            message_id = await self.session_service.add_message_to_session(
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
            result["error"] = f"HTTP error: {e.response.status_code} - {e.response.text}"
            message_id = await self.session_service.add_message_to_session(
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
            message_id = await self.session_service.add_message_to_session(
                session_id=session_id,
                text=message,
                message_type="outgoing",
                sender="bot",
                status="failed",
                error_message=result["error"],
            )
            result["message_id"] = message_id

        return result

    async def get_updates(self, offset: Optional[int] = None) -> Dict[str, Any]:
        try:
            return await self.client.get_updates(offset=offset)
        except Exception as e:
            print(f"[Telegram] Error getting updates: {e}")
            return {"ok": False, "result": []}

    async def handle_update(self, update: Dict[str, Any], on_message_callback=None) -> None:
        if "message" not in update or "text" not in update["message"]:
            return

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

        session_id = await self.session_service.get_or_create_session(
            self.bot_id, chat_id
        )

        await self.session_service.add_message_to_session(
            session_id=session_id,
            text=message_text,
            message_type="incoming",
            sender=user_info.get("username") or user_info.get("first_name") or "user",
            telegram_message_id=telegram_msg_id,
            telegram_response=message,
            status="success",
        )

        print(
            f"[Session {session_id}] Received from {user_info['first_name']}: {message_text}"
        )

        if on_message_callback:
            response_text = on_message_callback(
                session_id, chat_id, message_text, user_info
            )
            if asyncio.iscoroutine(response_text):
                response_text = await response_text
        else:
            response_text = self._default_response(message_text, user_info)

        if not response_text:
            return

        result = await self.send_message(
            chat_id=chat_id,
            message=response_text,
            session_id=session_id,
        )

        if result["status"] == "success":
            print(f"[Session {session_id}] Replied: {response_text}")
        else:
            print(f"[Session {session_id}] Failed to send reply: {result['error']}")

    def _default_response(self, message_text: str, user_info: Dict) -> str:
        name = user_info.get("first_name", "there")

        if message_text.lower() in ["/start", "/hello", "hello", "hi"]:
            return f"Hello {name}! I'm your bot. How can I help you today?"
        if message_text.lower() in ["/help", "help"]:
            return "I'm a simple bot. I'll echo back whatever you send me! Try sending me any message."
        if message_text.lower() == "/session":
            return "Your messages are being organized in sessions. Each conversation is tracked."
        return f"You said: {message_text}"
