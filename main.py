import asyncio
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv, find_dotenv

from app.channels.telegram.bot import TelegramBot
from app.channels.telegram.client import TelegramClient
from app.bot_config import load_bot_configs
from app.config import Settings
from app.db.session import Database
from app.services.session_service import SessionService
from app.webhook_server import WebhookServer


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    echo: bool
    webhook_url: Optional[str]
    webhook_base_url: str
    webhook_host: str
    webhook_port: int
    webhook_secret_token: str
    drop_pending_updates: bool
    allowed_updates: List[str]


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _parse_allowed_updates(
    value: Optional[str], default: Optional[List[str]]
) -> List[str]:
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_app_config(settings: Settings) -> AppConfig:
    return AppConfig(
        database_url=os.getenv("DATABASE_URL", settings.database_url),
        echo=_parse_bool(os.getenv("ECHO"), settings.echo),
        webhook_url=os.getenv("WEBHOOK_URL"),
        webhook_base_url=os.getenv("WEBHOOK_BASE_URL", settings.webhook_base_url),
        webhook_host=os.getenv("WEBHOOK_HOST", settings.webhook_host),
        webhook_port=_parse_int(os.getenv("WEBHOOK_PORT"), settings.webhook_port),
        webhook_secret_token=os.getenv(
            "WEBHOOK_SECRET_TOKEN", settings.webhook_secret_token
        ),
        drop_pending_updates=_parse_bool(
            os.getenv("WEBHOOK_DROP_PENDING_UPDATES"),
            settings.webhook_drop_pending_updates,
        ),
        allowed_updates=_parse_allowed_updates(
            os.getenv("WEBHOOK_ALLOWED_UPDATES"),
            settings.webhook_allowed_updates,
        ),
    )


def _validate_config(bots, config: AppConfig) -> bool:
    if not bots:
        print("[Config] No bots configured. Set BOT_TOKEN or BOT_TOKENS.")
        return False
    if not config.webhook_url and not config.webhook_base_url:
        print(
            "[Config] WEBHOOK_BASE_URL is empty. Set it in environment or in app/config.py"
        )
        return False
    return True


def _parse_webhook_url(webhook_url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not webhook_url:
        return None, None
    parsed = urlparse(webhook_url)
    base_url = None
    if parsed.scheme and parsed.netloc:
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"
    return base_url, path


def _resolve_secret(bot_secret: str, default_secret: str) -> Optional[str]:
    secret = bot_secret or default_secret
    return secret if secret else None


def _default_handler(session_id, chat_id, message_text, user_info):
    name = user_info.get("first_name", "Friend")

    if "hello" in message_text.lower() or "hi" in message_text.lower():
        return f"Hey {name}! Nice to hear from you! (Session #{session_id})"
    if "how are you" in message_text.lower():
        return "I'm doing great! Thanks for asking."
    if "bye" in message_text.lower():
        return f"Goodbye {name}! Have a wonderful day!"
    return f"Thanks for your message: '{message_text}'"


async def _register_bot(
    bot_cfg,
    session_service: SessionService,
    server: WebhookServer,
    config: AppConfig,
    base_url: str,
    full_url_path: Optional[str],
    single_bot: bool,
) -> Tuple[str, str]:
    telegram_client = TelegramClient(bot_cfg.token)
    bot = TelegramBot(telegram_client, session_service, bot_id=bot_cfg.name)

    if config.webhook_url and single_bot:
        bot_webhook_path = full_url_path or "/"
        bot_webhook_url = config.webhook_url
    else:
        bot_webhook_path = bot_cfg.webhook_path
        bot_webhook_url = bot_cfg.build_webhook_url(base_url)

    secret = _resolve_secret(bot_cfg.secret_token, config.webhook_secret_token)

    async def handle_update(update: dict, _bot=bot) -> None:
        await _bot.handle_update(update, on_message_callback=_default_handler)

    server.add_route(path=bot_webhook_path, handler=handle_update, secret_token=secret)

    webhook_result = await telegram_client.set_webhook(
        url=bot_webhook_url,
        secret_token=secret,
        drop_pending_updates=config.drop_pending_updates,
        allowed_updates=config.allowed_updates,
    )
    print(f"[Webhook] setWebhook for {bot_cfg.name}: {webhook_result}")
    if not webhook_result.get("ok"):
        raise RuntimeError(
            "[Webhook] Registration failed. Check URL, token, and HTTPS setup."
        )

    return bot_webhook_path, bot_cfg.name


async def main() -> None:
    load_dotenv(find_dotenv())
    settings = Settings()
    config = _load_app_config(settings)

    bots = load_bot_configs(settings)
    if not _validate_config(bots, config):
        return

    db = Database(config.database_url, echo=config.echo)
    await db.initialize()
    print("[DB] Database initialized")

    session_service = SessionService(db.session_factory)

    server = None
    try:
        server = WebhookServer(
            host=config.webhook_host,
            port=config.webhook_port,
            loop=asyncio.get_running_loop(),
        )
        routes = []

        base_url_from_full, full_url_path = _parse_webhook_url(config.webhook_url)
        base_url = base_url_from_full or config.webhook_base_url

        for bot_cfg in bots:
            route = await _register_bot(
                bot_cfg=bot_cfg,
                session_service=session_service,
                server=server,
                config=config,
                base_url=base_url,
                full_url_path=full_url_path,
                single_bot=len(bots) == 1,
            )
            routes.append(route)

        server.start()
        print(f"[Webhook] Listening on http://{config.webhook_host}:{config.webhook_port}")
        for path, name in routes:
            print(f"[Webhook] Route ready: {path} ({name})")
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("[Webhook] Stopped by user")
    except RuntimeError as e:
        print(str(e))
    finally:
        if server:
            try:
                server.stop()
            except Exception:
                pass
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
