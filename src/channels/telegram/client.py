from typing import Any, Dict, List, Optional

import httpx

from src.utils.logger import logger


class TelegramClient:
    logger = logger

    def __init__(self, bot_token: str, timeout_s: float = 30.0) -> None:
        self.bot_token = bot_token
        self.timeout_s = timeout_s

    async def send_message(
        self, chat_id: str, text: str, reply_markup: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def answer_callback_query(
        self, callback_query_id: str, text: Optional[str] = None
    ) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def get_updates(self, offset: Optional[int] = None) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"timeout": 30, "offset": offset}

        async with httpx.AsyncClient(timeout=self.timeout_s + 10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def set_webhook(
        self,
        url: str,
        secret_token: Optional[str] = None,
        drop_pending_updates: Optional[bool] = None,
        allowed_updates: Optional[List[str]] = None,
        max_connections: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        api_url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
        payload: Dict[str, Any] = {"url": url}

        if secret_token:
            payload["secret_token"] = secret_token
        if drop_pending_updates is not None:
            payload["drop_pending_updates"] = drop_pending_updates
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        if max_connections is not None:
            payload["max_connections"] = max_connections
        if ip_address is not None:
            payload["ip_address"] = ip_address

        async with httpx.AsyncClient(timeout=self.timeout_s + 10) as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def get_webhook_info(self) -> Dict[str, Any]:
        api_url = f"https://api.telegram.org/bot{self.bot_token}/getWebhookInfo"

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            return response.json()

    async def delete_message(self, chat_id: str, message_id: int) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.bot_token}/deleteMessage"
        payload = {"chat_id": chat_id, "message_id": message_id}

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
