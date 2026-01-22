from dataclasses import dataclass
from typing import List, Optional

from app.config import Settings


@dataclass
class BotConfig:
    name: str
    token: str
    webhook_path: str
    manager_ids: List[str]
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
    configs: List[BotConfig] = []

    if not settings.bot_tokens:
        return configs

    # If it's a single bot and BOT_TOKEN was used, we might want to use WEBHOOK_PATH
    if len(settings.bot_tokens) == 1 and (not settings.bot_names or settings.bot_names[0] == "default"):
        configs.append(
            BotConfig(
                name=settings.bot_names[0] if settings.bot_names else "default",
                token=settings.bot_tokens[0],
                webhook_path=_normalize_path(settings.webhook_path),
                manager_ids=settings.manager_ids[0] if settings.manager_ids else [],
                secret_token=settings.webhook_secret_token or "",
            )
        )
        return configs

    for index, token in enumerate(settings.bot_tokens):
        name = (
            settings.bot_names[index]
            if index < len(settings.bot_names) and settings.bot_names[index]
            else f"bot{index + 1}"
        )
        path = f"{settings.webhook_path_prefix}/{name}"
        
        # Получаем список менеджеров для этого бота
        # Если индекс выходит за пределы settings.manager_ids, берем пустой список или последний доступный?
        # По заданию: managers_ids=[123,321], [555,444] для bot1, bot2
        bot_manager_ids = (
            settings.manager_ids[index]
            if index < len(settings.manager_ids)
            else []
        )

        configs.append(
            BotConfig(
                name=name,
                token=token,
                webhook_path=_normalize_path(path),
                manager_ids=bot_manager_ids,
                secret_token=settings.webhook_secret_token or "",
            )
        )
    return configs
