import asyncio
import random
from typing import Any, Dict, List, Optional

import httpx

from app.services.session_service import SessionService
from app.channels.telegram.client import TelegramClient


class TelegramBot:
    def __init__(
        self,
        client: TelegramClient,
        session_service: SessionService,
        bot_id: str,
        manager_ids: List[str],
    ) -> None:
        self.client = client
        self.session_service = session_service
        self.last_update_id = 0
        self.bot_id = bot_id
        self.manager_ids = manager_ids

    async def send_message(
        self,
        chat_id: str,
        message: str,
        session_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if session_id is None:
            # Попробуем найти активную сессию для этого chat_id
            active_session = await self.session_service.get_active_session_by_chat_id(
                self.bot_id, chat_id
            )
            if active_session:
                session_id = active_session.session_id
            else:
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
            response_data = await self.client.send_message(
                chat_id, message, reply_markup=reply_markup
            )
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
        if "callback_query" in update:
            await self._handle_callback_query(update["callback_query"])
            return

        if "message" not in update or "text" not in update["message"]:
            return

        message = update["message"]
        chat_id = str(message["chat"]["id"])
        message_text = message["text"]
        user_id = str(message["from"]["id"])
        telegram_msg_id = str(message["message_id"])
        user_info = {
            "first_name": message["from"].get("first_name", ""),
            "last_name": message["from"].get("last_name", ""),
            "username": message["from"].get("username", ""),
            "user_id": user_id,
        }

        # Если это менеджер
        if user_id in self.manager_ids:
            if message_text == "/close":
                active_session = (
                    await self.session_service.get_active_session_by_manager_id(
                        self.bot_id, user_id
                    )
                )
                if active_session:
                    await self.session_service.close_session(active_session.session_id)
                    await self.client.send_message(user_id, "Сессия закрыта.")
                    await self.client.send_message(
                        active_session.chat_id, "Сессия завершена менеджером."
                    )
                else:
                    await self.client.send_message(user_id, "У вас нет активных сессий.")
                return

            active_session = await self.session_service.get_active_session_by_manager_id(
                self.bot_id, user_id
            )
            if active_session:
                # Пересылаем сообщение клиенту
                await self.send_message(
                    active_session.chat_id,
                    message_text,
                    session_id=active_session.session_id,
                )
                return
            else:
                # Если менеджер написал что-то кроме /close и у него нет активной сессии,
                # возможно он хочет ответить на какое-то старое сообщение или просто так.
                # В данном простом диалоге - игнорируем или подсказываем.
                pass

        # Если это клиент
        if message_text == "/start":
            session = await self.session_service.get_active_session_by_chat_id(
                self.bot_id, chat_id
            )
            if not session:
                session_id = await self.session_service.get_or_create_session(
                    self.bot_id, chat_id
                )
                
                # Ищем свободного менеджера
                free_managers = await self.session_service.get_free_managers(
                    self.bot_id, self.manager_ids
                )
                
                if free_managers:
                    target_manager = random.choice(free_managers)
                    # Уведомляем менеджера
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Принять",
                                    "callback_data": f"accept_session_{session_id}",
                                }
                            ]
                        ]
                    }
                    manager_text = f"Есть новый клиент: {user_info['first_name']}"
                    if user_info["username"]:
                        manager_text += f" (@{user_info['username']})"
                    await self.client.send_message(
                        target_manager, manager_text, reply_markup=keyboard
                    )
                    await self.send_message(
                        chat_id, "Ожидайте менеджера...", session_id=session_id
                    )
                else:
                    await self.send_message(
                        chat_id, "К сожалению, сейчас все менеджеры заняты. Пожалуйста, попробуйте позже.", session_id=session_id
                    )
                    # Можно было бы оставить в очереди, но по заданию "give client a free manager"
                    # и если его нет, то мы уведомляем клиента.
            else:
                await self.send_message(
                    chat_id,
                    "Вы уже ожидаете менеджера или находитесь в активной сессии.",
                    session_id=session.session_id,
                )
            return

        # Обычное сообщение от клиента
        active_session = await self.session_service.get_active_session_by_chat_id(
            self.bot_id, chat_id
        )
        if active_session:
            # Сохраняем сообщение в базу
            await self.session_service.add_message_to_session(
                session_id=active_session.session_id,
                text=message_text,
                message_type="incoming",
                sender=user_info.get("username")
                or user_info.get("first_name")
                or "user",
                telegram_message_id=telegram_msg_id,
                telegram_response=message,
                status="success",
            )

            if active_session.status == "active":
                # Пересылаем менеджеру
                await self.client.send_message(
                    active_session.manager_id, f"Сообщение от клиента: {message_text}"
                )
            else:
                await self.client.send_message(
                    chat_id, "Менеджер еще не подключился. Пожалуйста, подождите."
                )
        else:
            await self.client.send_message(chat_id, "Нажмите /start чтобы начать сессию.")

    async def _handle_callback_query(self, callback_query: Dict[str, Any]) -> None:
        data = callback_query.get("data", "")
        if data.startswith("accept_session_"):
            session_id = int(data.split("_")[-1])
            manager_id = str(callback_query["from"]["id"])

            if manager_id not in self.manager_ids:
                await self.client.answer_callback_query(
                    callback_query["id"], text="Вы не являетесь менеджером"
                )
                return

            success = await self.session_service.accept_session(session_id, manager_id)
            if success:
                await self.client.answer_callback_query(
                    callback_query["id"], text="Сессия принята"
                )
                await self.client.send_message(
                    manager_id,
                    "Вы приняли сессию. Теперь вы можете общаться с клиентом. Для завершения используйте /close",
                )

                # Уведомляем клиента
                session_data = await self.session_service.get_session_messages(session_id)
                if session_data:
                    client_chat_id = session_data["chat_id"]
                    await self.send_message(
                        client_chat_id,
                        "Здравствуйте! Я менеджер компании Y. Чем я могу вам помочь?",
                        session_id=session_id,
                    )
            else:
                await self.client.answer_callback_query(
                    callback_query["id"],
                    text="Не удалось принять сессию (возможно, уже принята)",
                )

