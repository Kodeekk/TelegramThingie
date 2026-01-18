from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ChannelBot(ABC):
    @abstractmethod
    async def send_message(
        self, chat_id: str, message: str, session_id: Optional[int] = None
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def handle_update(
        self, update: Dict[str, Any], on_message_callback=None
    ) -> None:
        raise NotImplementedError
