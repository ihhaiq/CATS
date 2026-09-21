# AGENT.md — Catibot runtime notes

## Storage contract

PostgreSQL is the only runtime persistence backend.

- `STORAGE_BACKEND=postgres` is required.
- `DATABASE_URL` is required.
- Do not add a JSON/SQLite/file fallback.
- A database failure must fail startup rather than start with empty state.
- All mutable game state belongs in PostgreSQL.

The current schema stores the complete dictionary-shaped runtime state in the
`catibot_runtime_state` JSONB row. This intentionally preserves the existing
game behavior while eliminating JSON files. Mutations use a PostgreSQL row lock,
so multiple processes do not overwrite each other during read-modify-write
operations.

A one-time legacy importer may read an existing `catibot.json` only to migrate
it into PostgreSQL. After successful import, the legacy file is removed. It is
not a fallback backend.

## Active runtime

- `bot/main.py` boots aiogram and PostgreSQL.
- `bot/handlers/__init__.py` is the router registry.
- `bot/services/local_store.py` contains the active game logic and PostgreSQL
  state access. The filename is retained to avoid a broad import-only rename.
- `rich_card.py`, `media_runtime.py`, and `cat_assets.py` handle the Rich
  UI and cat assets.
- `notification_sweep.py` handles wake/needs notifications.

Do not introduce a second repository/domain stack beside this path.

## Assets

Official PNG assets remain under:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

Asset files are code/deployment resources, not persistence. Telegram media IDs,
cache metadata, and admin overrides are persisted in PostgreSQL.

## Development rules

- Keep private, Guest Mode, and callback behavior on the same game logic.
- Do not duplicate decay/cooldown/needs calculations inside handlers.
- Use `state_transaction()` for read-modify-write operations.
- Do not write runtime JSON files.
- New persistent fields should be added to the runtime state without creating
  a second source of truth.

## Checks

```bash
python -m compileall -q bot
python -m unittest discover -s tests -p "test_*.py"
```


## Temporary breed availability

Keep the complete breed model, pool, resolver, and asset paths intact. Additional breeds are temporarily disabled because the image library requires a large number of images. `siamese` is the only active breed: new adoptions receive it automatically, and existing owners may switch to it from the breed-change notice. Do not delete the disabled breed code or assets.
