# catibot

Telegram virtual-cat bot built with aiogram, Rich Messages, Guest Mode, a
filesystem-first cat asset library, and persistent game state.

## Runtime

The application starts from `bot/main.py`. The active routers are aggregated
in `bot/handlers/__init__.py`; old parallel handler/domain/storage stacks have
been removed so there is one clear runtime path.

The current gameplay state is handled by `bot/services/local_store.py`.
PostgreSQL bootstrap/models remain under `bot/database/` because the Railway
deployment has PostgreSQL available, but the feature handlers have not yet been
migrated from the JSON store to SQL.

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

Local JSON data is written to `data/catibot.json` and is ignored by Git.

## Cat Asset Library

Official cat media uses:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

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

The filesystem is the source of truth for official art. Runtime lookup prefers
an explicit admin override, then the requested age asset, then the adult
fallback, then legacy-compatible Telegram media identifiers.

Rich Messages need Telegram media identifiers, so local PNG files are uploaded
lazily and cached by hash. Replacing an asset changes its hash and forces a new
upload automatically.

See `bot/assets/cats/README.md` for the art rules and identity-anchor workflow.

## Railway

Keep `DATABASE_URL` configured for PostgreSQL. PostgreSQL schema support is
retained in `bot/database/db.py` and `bot/database/models.py`.

Until the gameplay repository is migrated to SQL, keep the JSON store on a
persistent Railway Volume as well. With `RAILWAY_VOLUME_MOUNT_PATH` set and
`JSON_DATA_FILE` left at its default, Catibot stores state at:

```text
$RAILWAY_VOLUME_MOUNT_PATH/catibot.json
```

JSON writes are atomic and maintain `catibot.json.bak` for recovery.

## Checks

```powershell
python -m compileall -q bot
python -m unittest discover -s tests -p "test_*.py"
```
