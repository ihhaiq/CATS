# catibot

Telegram virtual-cat bot built with aiogram, Rich Messages, Guest Mode,
filesystem-first cat assets, and PostgreSQL persistence.

## Runtime

The application starts from `bot/main.py`. PostgreSQL is the only persistence
backend. `STORAGE_BACKEND` must be `postgres` and `DATABASE_URL` must point
to the Railway PostgreSQL service.

All mutable bot state is stored in PostgreSQL, including:

- users and points
- cats and every care/needs/sleep field
- daily streak/bonus state
- shop items, purchases and inventory
- points history
- Telegram media mappings
- local-asset upload cache metadata
- admin media overrides

There is no JSON-file runtime fallback. If PostgreSQL is unavailable, startup
fails instead of silently switching storage.

For compatibility with existing deployments, the first PostgreSQL startup can
import an old `catibot.json` from `JSON_DATA_FILE`,
`RAILWAY_VOLUME_MOUNT_PATH/catibot.json`, or `data/catibot.json`. After a
successful import, the legacy JSON file and its `.bak` are removed.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `BOT_TOKEN` and `DATABASE_URL`, then run:

```powershell
python -m bot.main
```

## Cat Asset Library

Official cat artwork remains checked into the repository at:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

These PNG files are application assets, not runtime state. Their reusable
Telegram `file_id` cache and admin overrides are persisted in PostgreSQL.

Supported breeds:

- `orange_tabby`
- `black`
- `siamese`
- `british_shorthair_grey`
- `calico`
- `white`

Supported age stages:

- `kitten` — 0-6 days
- `junior` — 7-20 days
- `adult` — 21-89 days
- `senior` — 90+ days

Supported states:

- `idle`
- `happy`
- `hungry`
- `feed`
- `play`
- `walk`
- `talk`
- `sleep`
- `angry`
- `sick`

See `bot/assets/cats/README.md` for the art rules.

## Railway

Required:

```text
STORAGE_BACKEND=postgres
DATABASE_URL=<Railway PostgreSQL URL>
BOT_TOKEN=<Telegram bot token>
```

A Railway Volume is no longer required for bot state. You may remove an old
volume after the one-time JSON import has completed and the deployment logs
confirm PostgreSQL initialization.

## Checks

```powershell
python -m compileall -q bot
python -m unittest discover -s tests -p "test_*.py"
```


## Temporary breed rollout

The multi-breed system and all breed code remain in the repository, but additional breeds are temporarily disabled because completing the required image library would require a large number of images. New adoptions currently receive `siamese` automatically. Existing owners can use the breed-change notice to switch their cat to `siamese`.
