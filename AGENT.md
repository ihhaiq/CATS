# AGENT.md — Build Roadmap for catibot

This file is the handoff doc for whoever (human or AI agent) implements the
logic. The folder structure and file stubs already exist — every file has a
`TODO` docstring pointing to the relevant step number below. Work through
these roughly in order; later steps depend on earlier ones.

---

## Status: local runtime implemented
The checked-in local runtime uses JSON storage, Rich Messages, Guest Mode,
action callbacks, sleep state, and admin media upload. PostgreSQL models and
the older `bot/core` path remain migration work; do not enable PostgreSQL in
deployment until all feature handlers use the repository abstraction.

---

## Build Order

### 1. Config & secrets
- `bot/config.py` — confirm the env var list is complete once you know your
  final Railway setup (e.g. do you need `REDIS_URL` for notification-cooldown
  tracking, or is the DB enough?).
- Add startup validation: fail fast with a clear error if `BOT_TOKEN` or
  `DATABASE_URL` is missing.

### 2. main.py wiring
- Confirm webhook vs polling behavior locally before deploying.
- Add graceful shutdown (close DB engine, stop scheduler) — not stubbed yet.

### 3. Database & migrations
- `bot/database/models.py` has all 5 tables from the spec.
- Run `alembic init bot/database/migrations` and generate the first revision
  from these models — don't rely on `Base.metadata.create_all` in production
  (it's only there as a dev convenience in `db.py`).
- Decide: do you want a `fled_at` timestamp column on `cats`? (referenced in
  `flee_logic.py` TODO but not yet in the model — add it before writing that
  logic.)

### 4. Core stat logic (decay_engine.py + economy.py)
- **Tune the decay rates** — current numbers (`HUNGER_RISE_PER_HOUR = 4`,
  etc.) are placeholders. Decide real game balance: how many real hours
  should a fully-fed cat stay "happy" before it needs attention again?
- Implement `assign_random_breed()` and `generate_unique_id_number()` in
  `economy.py`.
- Implement `award_points()` — must update `users.points` and insert a
  `points_log` row in the same DB transaction.

### 5. /adopt, /feed, /play, /walk
- Wire `adopt.py` using the helpers from step 4.
- Wire `care.py`: for each action, call `apply_lazy_decay()` first, then
  check cooldown via `economy.check_cooldown()`, then apply the effect +
  award points + re-render image.
- **Open decision:** should feed/play cooldowns be per-user or per-cat? (Spec
  assumes per-cat, confirm this matches your intent.)

### 6. Co-owner / partner system
- `partner.py` — build the deep-link token scheme for `/start <payload>`.
- Guard the one-time +50 bonus against re-invite abuse (check `points_log`
  or add a dedicated `partner_history` table if you want a cleaner audit
  trail than parsing log reasons).

### 7. Status view + image caching
- `status.py` ties together decay + flee check + render.
- Decide the caching mechanism: a hash column on `cats`, or an in-memory/
  Redis cache keyed by `(breed, emotion_bucket, title)`. DB column is
  simplest to start; Redis only if you outgrow it.

### 8. Shop & inventory
- Seed the `items` table with actual items (what do snacks/collar skins
  actually *do*? define `effect_type` values now, e.g. `"instant_happiness"`,
  `"cosmetic_collar"`).
- Implement `/buy` and an "use item" flow for consumables.

### 9. Flee logic + shelter
- Add `fled_at` column (see step 3).
- Implement `check_flee()` fully, wire it into `status.py` and the
  notification sweep (step 11).
- Implement `/shelter` and `/shelter_adopt` — **open decision:** what love_bar
  should a re-adopted cat start at? Spec suggests ~40% ("earned", not free).

### 10. Image rendering
- **You need actual art assets first** — this step blocks on getting cat
  images per breed (`orange_tabby`, `black`, `siamese`,
  `british_shorthair_grey`, `calico`, `white`) × 3 emotion states each, plus
  a collar/overlay template and an Arabic-capable font (e.g. Cairo, Tajawal,
  or similar — drop the `.ttf` into `bot/assets/fonts/`).
- Implement `render_cat()` in `image_renderer.py`: composite base + collar
  text (already using `shape_arabic()`, which is implemented).

### 11. Notification sweep — the piece that ties it all together
- This is the last step because it depends on decay, flee, and rendering all
  being real.
- Implement `start_notification_sweep()` with APScheduler's
  `AsyncIOScheduler`, interval per `settings` (suggest 15–30 min).
- Follow the 7-step logic already spelled out in
  `bot/services/notification_sweep.py`'s docstring.
- **Test carefully for spam** — this is the riskiest part UX-wise. Verify the
  `last_notified_state` / `last_notified_at` guard actually prevents repeat
  alerts for an unresolved condition.

---

## Open Product Decisions (confirm with H before building further)
- Per-cat vs per-user cooldowns on feed/play.
- Whether a user can re-adopt their *own* fled cat from the shelter for free.
- Exact decay-rate balance (steps 4) — needs playtesting, not just guessing.
- Notification channel: DM only, or also post to a group if the bot is added
  there?
- Whether breed is fully random at adoption or partially user-choosable from
  a free pool (spec allows either).

---

## Not yet stubbed (add when you get here)
- Admin commands (`admin.py` mentioned in the structure but not yet
  scaffolded — add stats/moderation commands here once core loop works).
- Rate-limit / anti-multi-account protection beyond the cooldown checks
  already noted in `economy.py`.
