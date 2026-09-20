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

## Cat Asset Library

Cat media is keyed by **breed + age stage + state**. The canonical filesystem
layout is:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

Example: `bot/assets/cats/siamese/kitten/sleep.png`.

Supported breeds:

- `orange_tabby`
- `black`
- `siamese`
- `british_shorthair_grey`
- `calico`
- `white`

Supported age stages:

- `kitten` — age_days 0-6
- `junior` — age_days 7-20
- `adult` — age_days 21-89
- `senior` — age_days 90+

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

Use lowercase snake_case names. Transparent PNG is the recommended and canonical
art format.

The filesystem is the **source of truth** for official cat art. Runtime lookup
uses this order:

1. explicit admin override, when one was intentionally set in `/dev`
2. `breed + requested age + visual state` on disk
3. `breed + adult + visual state` on disk
4. legacy local paths such as `breed/state.png`
5. Telegram legacy/generic `file_id` fallbacks

Rich Messages need Telegram media identifiers, so local PNGs are uploaded
**lazily on first use**. Catibot stores only cache metadata in JSON
(`file_id`, SHA-256 hash, media type and relative path). If the deployed PNG
changes, its hash changes and the file is uploaded again automatically. Asset
bytes are never stored in JSON.

Existing JSON keys such as `siamese:sleep`, `siamese:status`, and
`cat_angry_sleep` remain compatible.

To add a new asset, create the `idle.png` identity anchor first for that
`breed + age_stage`, then derive the other states from the same anchor and put
them in the matching directory. See `bot/assets/cats/README.md` for Catibot Art
Style v1, anchor rules, and examples.

## Media administration

Normal deployment does **not** require `/dev` uploads. Adding a PNG under
`bot/assets/cats/` and deploying is enough; the first request uploads and
caches it automatically.

`/dev` remains for manual overrides, auditing, debugging, and testing. The
**فحص مكتبة القطط** button audits the filesystem library. Use
`/dev_media_test` (or **اختبار الصور الغنية**) to send Rich Message tests for
the Siamese adult `idle`, `hungry`, `sleep`, and `angry` states.

`MEDIA_CACHE_CHAT_ID` is optional. When set, lazy uploads use that chat/channel
as a silent transport cache. Without it, Catibot temporarily uploads to the
current user/chat and deletes the transport message best-effort.

## Railway

Set `BOT_TOKEN`, `STORAGE_BACKEND`, `WEBHOOK_BASE_URL`, and `ADMIN_IDS` in
Railway. The current feature handlers use the JSON repository, so keep
`STORAGE_BACKEND=json` until the repository migration to PostgreSQL is
completed.

Attach a persistent Railway Volume to the service. When
`RAILWAY_VOLUME_MOUNT_PATH` is available and `JSON_DATA_FILE` is unset or
left at `data/catibot.json`, Catibot stores its state at
`$RAILWAY_VOLUME_MOUNT_PATH/catibot.json`. JSON writes are atomic, the previous
valid state is kept as `catibot.json.bak`, and a missing or damaged primary
file is restored from that backup instead of silently starting from an empty
store. Without a persistent Volume, a new Railway deployment can still lose
container-local files.

## Checks

```powershell
python -m compileall -q bot
python -m unittest tests.test_runtime
```

The legacy rule/service path is separate from the current Rich/JSON media
runtime. Asset compatibility tests live in `tests/test_runtime.py`.
