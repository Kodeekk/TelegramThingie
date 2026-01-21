import os
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
    webhook_allowed_updates: List[str] = field(
        default_factory=lambda: ["message", "callback_query"]
    )
    manager_ids: List[str] = field(default_factory=lambda: ["741343652"])
    webhook_url: Optional[str] = None
    bot_tokens: List[str] = field(default_factory=list)
    bot_names: List[str] = field(default_factory=list)
    webhook_path: str = "/telegram/webhook"

    @classmethod
    def from_env(cls) -> "Settings":
        def parse_bool(value: Optional[str], default: bool) -> bool:
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "y"}

        def parse_int(value: Optional[str], default: int) -> int:
            if value is None or not value.strip():
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def parse_list(value: Optional[str], default: List[str]) -> List[str]:
            if value is None or not value.strip():
                return default
            return [item.strip() for item in value.split(",") if item.strip()]

        bot_tokens = parse_list(os.getenv("BOT_TOKENS"), [])
        bot_names = parse_list(os.getenv("BOT_NAMES"), [])
        if not bot_tokens and os.getenv("BOT_TOKEN"):
            bot_tokens = [os.getenv("BOT_TOKEN")]
            if not bot_names:
                bot_names = ["default"]

        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///telegram_bot.db"),
            echo=parse_bool(os.getenv("ECHO"), False),
            webhook_base_url=os.getenv("WEBHOOK_BASE_URL", ""),
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=parse_int(os.getenv("WEBHOOK_PORT"), 8080),
            webhook_path_prefix=os.getenv("WEBHOOK_PATH_PREFIX", "/telegram"),
            webhook_secret_token=os.getenv("WEBHOOK_SECRET_TOKEN", ""),
            webhook_drop_pending_updates=parse_bool(
                os.getenv("WEBHOOK_DROP_PENDING_UPDATES"), True
            ),
            webhook_allowed_updates=parse_list(
                os.getenv("WEBHOOK_ALLOWED_UPDATES"), ["message", "callback_query"]
            ),
            manager_ids=parse_list(os.getenv("MANAGER_IDS"), ["741343652"]),
            webhook_url=os.getenv("WEBHOOK_URL"),
            bot_tokens=bot_tokens,
            bot_names=bot_names,
            webhook_path=os.getenv("WEBHOOK_PATH", "/telegram/webhook"),
        )
