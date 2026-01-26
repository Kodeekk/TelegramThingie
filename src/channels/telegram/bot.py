import asyncio
import random
from typing import Any, Dict, List, Optional

import httpx

from src.services.session_service import SessionService
from src.channels.telegram.client import TelegramClient
from src.utils.logger import logger


class TelegramBot:

    logger = logger

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
        sender: str = "bot",
        db_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        if session_id is None:
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
                text=db_text or message,
                message_type="outgoing",
                sender=sender,
                telegram_message_id=telegram_msg_id,
                status="success",
            )
            result["message_id"] = message_id

        except httpx.HTTPStatusError as e:
            result["error"] = f"HTTP error: {e.response.status_code} - {e.response.text}"
            message_id = await self.session_service.add_message_to_session(
                session_id=session_id,
                text=db_text or message,
                message_type="outgoing",
                sender=sender,
                status="failed",
                error_message=result["error"],
            )
            result["message_id"] = message_id
        except Exception as e:
            result["error"] = str(e)
            message_id = await self.session_service.add_message_to_session(
                session_id=session_id,
                text=db_text or message,
                message_type="outgoing",
                sender=sender,
                status="failed",
                error_message=result["error"],
            )
            result["message_id"] = message_id

        return result

    async def get_updates(self, offset: Optional[int] = None) -> Dict[str, Any]:
        try:
            return await self.client.get_updates(offset=offset)
        except Exception as e:
            self.logger.info(f"Error getting updates: {e}")
            return {"ok": False, "result": []}

    async def handle_update(
        self, update: Dict[str, Any], on_message_callback=None
    ) -> None:
        self.logger.debug(f"Handling update: {update}")
        if "callback_query" in update:
            await self._handle_callback_query(update["callback_query"])
            return

        if "message" not in update or "text" not in update["message"]:
            self.logger.info("Update ignored (no message or text)")
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

        if user_id in [str(mid) for mid in self.manager_ids]:
            self.logger.info(f"Manager message from {user_id}: {message_text}")
            await self._handle_manager_message(user_id, message_text, user_info, telegram_msg_id)
        else:
            self.logger.info(f"Client message from {user_id} ({chat_id}): {message_text}")
            await self._handle_client_update(
                chat_id, message_text, user_info, telegram_msg_id, message
            )
            if on_message_callback:
                self.logger.info(f"Executing on_message_callback for {user_id}")
                response = await asyncio.to_thread(
                    on_message_callback,
                    "unknown_session", # We don't have session_id here easily without more logic
                    chat_id,
                    message_text,
                    user_info,
                )
                if response:
                    await self.send_message(chat_id, response)

    async def _handle_manager_message(
        self, user_id: str, message_text: str, manager_info: Dict[str, Any], message_id: Optional[str] = None
    ) -> None:
        if message_text in ["/close", "Завершить диалог"]:
            if message_text == "Завершить диалог" and message_id:
                try:
                    await self.client.delete_message(user_id, int(message_id))
                except Exception as e:
                    self.logger.error(f"Failed to delete 'Завершить диалог' message: {e}")
            await self._close_manager_session(user_id)
            return

        active_session = await self.session_service.get_active_session_by_manager_id(
            self.bot_id, user_id
        )
        if active_session:
            display_name = manager_info.get("first_name") or "Manager"
            formatted_message = f"[{display_name}]: {message_text}"
            
            manager_username = manager_info.get("username")
            db_sender = f"bot-{manager_username}" if manager_username else "bot-manager"
            
            await self.send_message(
                active_session.chat_id,
                formatted_message,
                session_id=active_session.session_id,
                sender=db_sender,
                db_text=message_text,
            )

    async def _close_manager_session(self, user_id: str) -> None:
        active_session = (
            await self.session_service.get_active_session_by_manager_id(
                self.bot_id, user_id
            )
        )
        if not active_session:
            await self.client.send_message(user_id, "У вас нет активных сессий.")
            return

        await self.session_service.close_session(active_session.session_id)
        
        keyboard_remove = {"remove_keyboard": True}
        await self.client.send_message(user_id, "Сессия закрыта.", reply_markup=keyboard_remove)
        await self.client.send_message(
            active_session.chat_id, "Сессия завершена менеджером."
        )

        next_session = await self.session_service.get_next_waiting_session(self.bot_id)
        if next_session:
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Принять",
                            "callback_data": f"accept_session_{next_session.session_id}",
                        }
                    ]
                ]
            }
            await self.client.send_message(
                user_id,
                "В очереди есть клиент. Хотите принять?",
                reply_markup=keyboard
            )

    async def _handle_client_update(
        self,
        chat_id: str,
        message_text: str,
        user_info: Dict[str, Any],
        telegram_msg_id: str,
        raw_message: Dict[str, Any]
    ) -> None:
        if message_text == "/start":
            await self._handle_client_start(chat_id, user_info)
            return

        active_session = await self.session_service.get_active_session_by_chat_id(
            self.bot_id, chat_id
        )
        if not active_session:
            await self.client.send_message(chat_id, "Нажмите /start чтобы начать сессию.")
            return

        sender_name = user_info.get("username") or user_info.get("first_name") or "user"
        await self.session_service.add_message_to_session(
            session_id=active_session.session_id,
            text=message_text,
            message_type="incoming",
            sender=sender_name,
            telegram_message_id=telegram_msg_id,
            status="success",
        )

        if active_session.status == "active":
            username = user_info.get("username")
            display_name = f"@{username}" if username else user_info.get("first_name") or "user"
            
            await self.client.send_message(
                active_session.manager_id, 
                f"[{display_name}]: {message_text}"
            )
        else:
            await self.client.send_message(
                chat_id, "Менеджер еще не подключился. Пожалуйста, подождите."
            )

    async def _handle_client_start(self, chat_id: str, user_info: Dict[str, Any]) -> None:
        session = await self.session_service.get_active_session_by_chat_id(
            self.bot_id, chat_id
        )
        if session:
            await self.send_message(
                chat_id,
                "Вы уже ожидаете менеджера или находитесь в активной сессии.",
                session_id=session.session_id,
            )
            return

        session_id = await self.session_service.get_or_create_session(
            self.bot_id, chat_id
        )

        free_managers = await self.session_service.get_free_managers(
            self.bot_id, self.manager_ids
        )

        if free_managers:
            target_manager = random.choice(free_managers)
            #notifying manager
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

    async def _handle_callback_query(self, callback_query: Dict[str, Any]) -> None:
        data = callback_query.get("data", "")
        manager_id = str(callback_query["from"]["id"])

        if manager_id not in self.manager_ids:
            await self.client.answer_callback_query(
                callback_query["id"], text="Вы не являетесь менеджером"
            )
            return

        if data.startswith("accept_session_"):
            session_id = int(data.split("_")[-1])

            success = await self.session_service.accept_session(session_id, manager_id)
            if success:
                await self.client.answer_callback_query(
                    callback_query["id"], text="Сессия принята"
                )
                
                keyboard = {
                    "keyboard": [
                        [{"text": "Завершить диалог"}]
                    ],
                    "resize_keyboard": True,
                    "persistent": True
                }
                
                await self.client.send_message(
                    manager_id,
                    "Вы приняли сессию. Теперь вы можете общаться с клиентом. Для завершения используйте кнопку ниже или команду /close.",
                    reply_markup=keyboard
                )

                #notifying client
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
        elif data == "close_session":
            await self.client.answer_callback_query(callback_query["id"])
            await self._close_manager_session(manager_id)

