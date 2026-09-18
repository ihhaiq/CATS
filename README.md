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

Runtime media lookup uses this compatibility order:

1. `breed + requested age + state`
2. `breed + adult + state`
3. legacy `breed + state`
4. generic `state`

Existing JSON keys such as `siamese:sleep` remain valid. Legacy runtime names
`status` and `cat_angry_sleep` are mapped to `idle` and `angry`
respectively while retaining old-key fallbacks.

To add a new asset, create the `idle.png` identity anchor first for that
`breed + age_stage`, then derive the other states from the same anchor and put
them in the matching directory. See `bot/assets/cats/README.md` for Catibot Art
Style v1, anchor rules, and examples.

## Media administration

Use `/dev` as the configured admin, press **تحرير الوسائط**, choose a breed,
then an age stage, then a state, and upload the photo/video. Telegram media is
stored as `file_id` values in the local JSON file under the new three-part
keys. The **فحص مكتبة القطط** button audits the filesystem library against the
full breed × age × state matrix.

## Railway

Set `BOT_TOKEN`, `STORAGE_BACKEND`, `DATABASE_URL`, `WEBHOOK_BASE_URL`, and
`ADMIN_IDS` in Railway. The current feature handlers use the JSON repository;
keep `STORAGE_BACKEND=json` until the repository migration to PostgreSQL is
completed. Do not deploy the database mode expecting the Rich handlers to use
PostgreSQL yet.

## Checks

```powershell
python -m compileall -q bot
python -m unittest tests.test_runtime
```

The legacy rule/service path is separate from the current Rich/JSON media
runtime. Asset compatibility tests live in `tests/test_runtime.py`.
