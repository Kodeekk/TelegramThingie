import os
from dataclasses import dataclass
from typing import List, Optional

from app.config import Settings


@dataclass
class BotConfig:
    name: str
    token: str
    webhook_path: str
    secret_token: str = ""

    def build_webhook_url(self, base_url: str) -> str:
        base = base_url.rstrip("/")
        path = self.webhook_path if self.webhook_path.startswith("/") else f"/{self.webhook_path}"
        return f"{base}{path}"


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def load_bot_configs(settings: Settings) -> List[BotConfig]:
    default_secret = os.getenv("WEBHOOK_SECRET_TOKEN", settings.webhook_secret_token)
    path_prefix = os.getenv("WEBHOOK_PATH_PREFIX", settings.webhook_path_prefix)
    default_path = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
    configs: List[BotConfig] = []

    tokens_env = os.getenv("BOT_TOKENS")
    if tokens_env:
        tokens = [token.strip() for token in tokens_env.split(",") if token.strip()]
        names_env = os.getenv("BOT_NAMES")
        names = [name.strip() for name in names_env.split(",")] if names_env else []
        for index, token in enumerate(tokens):
            name = names[index] if index < len(names) and names[index] else f"bot{index + 1}"
            path = f"{path_prefix}/{name}"
            configs.append(
                BotConfig(
                    name=name,
                    token=token,
                    webhook_path=_normalize_path(path),
                    secret_token=default_secret or "",
                )
            )
        return configs

    token = os.getenv("BOT_TOKEN")
    if token:
        configs.append(
            BotConfig(
                name="default",
                token=token,
                webhook_path=_normalize_path(default_path),
                secret_token=default_secret or "",
            )
        )
    return configs
