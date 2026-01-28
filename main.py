import asyncio
import traceback
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv, find_dotenv

from src.channels.telegram.bot import TelegramBot
from src.channels.telegram.client import TelegramClient
from src.bot_config import load_bot_configs
from src.config import Settings
from src.db.session import Database
from src.services.session_service import SessionService
from src.webhook_server import WebhookServer
from src.utils.logger import logger

def _validate_config(bots, settings: Settings) -> bool:
    if not bots:
        settings.logger.info("No bots configured. Set BOT_TOKEN or BOT_TOKENS.")
        return False
    if not settings.webhook_url and not settings.webhook_base_url:
        settings.logger.info("WEBHOOK_BASE_URL is empty. Set it in environment or in src/config.py")
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
    return None


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
        manager_ids=bot_cfg.manager_ids,
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
    WebhookServer.logger.info(f"setWebhook for {bot_cfg.name}: {webhook_result}")
    if not webhook_result.get("ok"):
        raise RuntimeError(
            f"Registration failed for {bot_cfg.name}: {webhook_result}. Check URL, token, and HTTPS setup."
        )

    return bot_webhook_path, bot_cfg.name


async def main() -> None:
    load_dotenv(find_dotenv())
    settings = Settings.from_env()
    logger.set_level(settings.env)

    bots = load_bot_configs(settings)
    if not _validate_config(bots, settings):
        return

    db = Database(settings.database_url, echo=settings.echo)
    await db.initialize()
    db.logger.info("Database initialized")

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
        WebhookServer.logger.info(f"Listening on http://{settings.webhook_host}:{settings.webhook_port}")
        for path, name in routes:
            WebhookServer.logger.info(f"Route ready: {path} ({name})")
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        WebhookServer.logger.info("Stopped by user")
    except RuntimeError as e:
        WebhookServer.logger.error(str(e))
    except Exception as e:
        WebhookServer.logger.error(f"Unexpected error in main: {e}")
        WebhookServer.logger.debug(traceback.format_exc())
    finally:
        if server:
            try:
                server.stop()
            except Exception:
                pass
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
