# catibot

Telegram virtual-cat bot using aiogram. The checked-in runtime is
`bot/main.py`; local development uses JSON storage and Rich Messages.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `BOT_TOKEN` in `.env`, then run:

```powershell
python -m bot.main
```

Local data is written to `data/catibot.json`, which is intentionally ignored by
Git. Never commit `.env` or a bot token.

## Media

Use `/dev` as the configured admin, press **تحرير الوسائط**, choose a breed and
then a state, and upload the photo/video. Media is stored as Telegram `file_id`
values in the local JSON file. Breed-specific media overrides generic media.

Supported states include `status`, `feed`, `play`, `walk`, `talk`, `sleep`, and
`cat_angry_sleep`.

## Railway

Set `BOT_TOKEN`, `STORAGE_BACKEND`, `DATABASE_URL`, `WEBHOOK_BASE_URL`, and
`ADMIN_IDS` in Railway. The current feature handlers use the JSON repository;
keep `STORAGE_BACKEND=json` until the repository migration to PostgreSQL is
completed. Do not deploy the database mode expecting the Rich handlers to use
PostgreSQL yet.

## Checks

```powershell
python -m compileall -q bot
python -m tests.test_runtime
```

The legacy `tests.test_rules` suite targets the retired `bot/core` runtime and
is not the source of truth for the current entry point.


## Sleep / cooldown tuning

The active JSON runtime reads these optional variables:

- `SLEEP_NEED_DROP_INTERVAL_MINUTES=5`: how often the rest meter drops while awake.
- `SLEEP_NEED_DROP_PER_INTERVAL=1`: points lost each interval.
- `FEED_COOLDOWN_SECONDS=900`
- `PLAY_COOLDOWN_SECONDS=900`
- `WALK_COOLDOWN_SECONDS=14400`
- `TALK_COOLDOWN_SECONDS=300`

With the defaults, rest goes from 100% to 99% after five awake minutes and reaches the current 65% refusal threshold after about 175 minutes.
