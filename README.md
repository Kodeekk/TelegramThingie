# TelegramThingie

Async Telegram webhook bot with session storage and multi-bot support.

## Features
- Webhook-based updates (no polling loop)
- Multiple bots on a single server (different webhook paths)
- Session/message storage in SQLite via SQLAlchemy
- Simple handler you can customize per project

## Quick start

1) Install dependencies
```bash
pip install -r .requirements.txt
```

2) Create `.env` from example
```bash
copy .env.example .env
```

3) Fill `.env`
- `WEBHOOK_BASE_URL` should be your public HTTPS domain (e.g. ngrok)
- `BOT_TOKEN` for a single bot or `BOT_TOKENS` + `BOT_NAMES` for multiple bots

4) Run
```bash
python main.py
```

## Environment variables

Single bot:
```
BOT_TOKEN=123:ABC
WEBHOOK_BASE_URL=https://your-subdomain.ngrok-free.app
```

Multiple bots (CSV):
```
BOT_TOKENS=TOKEN1,TOKEN2
BOT_NAMES=bot1,bot2
WEBHOOK_BASE_URL=https://your-subdomain.ngrok-free.app
```
This creates webhook paths:
- `/telegram/bot1`
- `/telegram/bot2`

## Webhook details
- Telegram sends POST updates to your HTTPS endpoint.
- Local server listens on `WEBHOOK_HOST:WEBHOOK_PORT`.
- Each bot has its own path under `WEBHOOK_PATH_PREFIX`.

## Database
- SQLite file: `telegram_bot.db`
- If you change models, delete the db for a clean start (or add migrations).

## Notes
- For local development, use ngrok to expose your server:
```
ngrok http 8080
```
