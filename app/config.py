from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite+aiosqlite:///telegram_bot.db"
    echo: bool = False
    webhook_base_url: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path_prefix: str = "/telegram"
    webhook_secret_token: str = ""
    webhook_drop_pending_updates: bool = True
    webhook_allowed_updates: Optional[List[str]] = field(
        default_factory=lambda: ["message"]
    )
