import asyncio
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

def _validate_config(bots, settings: Settings) -> bool:
    if not bots:
        print("[Config] No bots configured. Set BOT_TOKEN or BOT_TOKENS.")
        return False
    if not settings.webhook_url and not settings.webhook_base_url:
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
    settings: Settings,
    base_url: str,
    full_url_path: Optional[str],
    single_bot: bool,
) -> Tuple[str, str]:
    telegram_client = TelegramClient(bot_cfg.token)
    bot = TelegramBot(
        telegram_client,
        session_service,
        bot_id=bot_cfg.name,
        manager_ids=settings.manager_ids,
    )

    if settings.webhook_url and single_bot:
        bot_webhook_path = full_url_path or "/"
        bot_webhook_url = settings.webhook_url
    else:
        bot_webhook_path = bot_cfg.webhook_path
        bot_webhook_url = bot_cfg.build_webhook_url(base_url)

    secret = _resolve_secret(bot_cfg.secret_token, settings.webhook_secret_token)

    async def handle_update(update: dict, _bot=bot) -> None:
        await _bot.handle_update(update, on_message_callback=_default_handler)

    server.add_route(path=bot_webhook_path, handler=handle_update, secret_token=secret)

    webhook_result = await telegram_client.set_webhook(
        url=bot_webhook_url,
        secret_token=secret,
        drop_pending_updates=settings.webhook_drop_pending_updates,
        allowed_updates=settings.webhook_allowed_updates,
    )
    print(f"[Webhook] setWebhook for {bot_cfg.name}: {webhook_result}")
    if not webhook_result.get("ok"):
        raise RuntimeError(
            "[Webhook] Registration failed. Check URL, token, and HTTPS setup."
        )

    return bot_webhook_path, bot_cfg.name


async def main() -> None:
    load_dotenv(find_dotenv())
    settings = Settings.from_env()

    bots = load_bot_configs(settings)
    if not _validate_config(bots, settings):
        return

    db = Database(settings.database_url, echo=settings.echo)
    await db.initialize()
    print("[DB] Database initialized")

    session_service = SessionService(db.session_factory)

    server = None
    try:
        server = WebhookServer(
            host=settings.webhook_host,
            port=settings.webhook_port,
            loop=asyncio.get_running_loop(),
        )
        routes = []

        base_url_from_full, full_url_path = _parse_webhook_url(settings.webhook_url)
        base_url = base_url_from_full or settings.webhook_base_url

        for bot_cfg in bots:
            route = await _register_bot(
                bot_cfg=bot_cfg,
                session_service=session_service,
                server=server,
                settings=settings,
                base_url=base_url,
                full_url_path=full_url_path,
                single_bot=len(bots) == 1,
            )
            routes.append(route)

        server.start()
        print(f"[Webhook] Listening on http://{settings.webhook_host}:{settings.webhook_port}")
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
