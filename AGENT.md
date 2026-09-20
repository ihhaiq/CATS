# AGENT.md — Catibot runtime notes

## Current runtime

Catibot has one active runtime path:

- `bot/main.py` boots aiogram.
- `bot/handlers/__init__.py` is the router registry.
- Active gameplay state lives in `bot/services/local_store.py`.
- Rich cards and media resolution live in `rich_card.py`,
  `media_runtime.py`, and `cat_assets.py`.
- Periodic needs/wake notifications live in `notification_sweep.py`.

Do not reintroduce a second domain/service/repository stack beside this path.
Shared logic should be added to the active services and reused by private,
Guest Mode, and callback handlers.

## Storage

The live gameplay repository is currently JSON-backed.

Railway PostgreSQL support is intentionally retained:

- `bot/database/db.py`
- `bot/database/models.py`
- `SQLAlchemy`
- `asyncpg`
- `alembic`

`DATABASE_URL` may stay configured in Railway. The existing SQL bootstrap can
create the schema when `STORAGE_BACKEND=postgres`, but current feature
handlers still read/write through `local_store.py`. Until that migration is
completed, keep the JSON file on a persistent Railway Volume too.

When migrating to PostgreSQL, replace the persistence layer behind the active
runtime instead of restoring the deleted legacy `bot/storage`, `bot/domain`,
or `CatService` stack.

## Official cat assets

The source of truth is:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

Age stage is derived from `age_days`.

Supported breeds:

- `orange_tabby`
- `black`
- `siamese`
- `british_shorthair_grey`
- `calico`
- `white`

Supported age stages:

- `kitten`: 0-6 days
- `junior`: 7-20 days
- `adult`: 21-89 days
- `senior`: 90+ days

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

Keep breed/state vocabulary centralized in `bot/services/cat_assets.py`.
Official files are uploaded lazily to Telegram and cached by content hash.
Do not store image bytes or base64 in the data store.

## Development rules

- Keep private, Guest Mode, and rich callback behavior on the same game logic.
- Do not duplicate decay/cooldown/needs calculations inside handlers.
- Preserve atomic JSON writes and backup recovery until PostgreSQL owns the
  gameplay state.
- Do not remove PostgreSQL dependencies while the Railway database is part of
  the deployment.
- New files need a concrete runtime purpose; avoid placeholder modules.

## Checks

Run before merging:

```bash
python -m compileall -q bot
python -m unittest discover -s tests -p "test_*.py"
```
