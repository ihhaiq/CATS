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

## Official Cat Asset System

Cat assets use one canonical identity:

```text
structure = breed / age_stage / state
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

The canonical runtime media key is:

```text
<breed>:<age_stage>:<state>
```

Example: `siamese:kitten:sleep`.

### Supported breeds

- `orange_tabby`
- `black`
- `siamese`
- `british_shorthair_grey`
- `calico`
- `white`

### Supported age stages

Age stage is derived from `age_days`; do not persist a second `age_stage`
field unless a future storage design has a concrete need for it.

- `kitten`: 0-6 days
- `junior`: 7-20 days
- `adult`: 21-89 days
- `senior`: 90+ days

### Supported states

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

Use lowercase snake_case names only. Keep the vocabulary centralized in
`bot/services/cat_assets.py`; do not create duplicate state/age/breed arrays
inside handlers.

### Runtime source of truth, lookup and cache

Official files under `bot/assets/cats/` are the primary source of truth.
Do not require an administrator to upload official art manually after deploy.

Runtime resolution is:

1. explicit admin override, if intentionally configured
2. local requested `breed + age_stage + visual_state`
3. local `breed + adult + visual_state`
4. legacy-compatible local path
5. legacy/generic Telegram `file_id`

Because Telegram Rich Messages use reusable Telegram media identifiers, local
files are lazily uploaded on first request. Persist only metadata
(`file_id`, SHA-256, media type, path), never image bytes/base64. A hash
mismatch invalidates the cache and triggers a fresh upload.

Use per-asset async synchronization so concurrent requests in one process do
not upload the same file twice. Do not pre-upload all 240 assets at startup.
Multi-instance deployments can still race across processes unless they share a
stronger external lock/cache; duplicate uploads in that topology are harmless.

Legacy JSON data is not migrated destructively. Keys such as
`siamese:sleep`, `siamese:status`, and generic state entries must continue
to work.

Compatibility aliases:

- `status -> idle`
- `cat_angry_sleep -> angry`

Visual-state precedence is centralized in
`resolve_cat_visual_state(cat, requested_state)`:

1. explicit action state
2. sleeping -> `sleep`
3. active refusal -> `angry`
4. sick flag -> `sick`
5. hunger threshold -> `hungry`
6. otherwise -> `idle`

This dynamic precedence applies to status/idle views; explicit states such as
feed/play/walk/talk/sleep/angry remain explicit.

When an alias is used, canonical age-aware keys are preferred, then legacy
original keys are checked so old deployments remain valid.

### Catibot Art Style v1

Official assets must be:

- 2D hand-drawn semi-realistic cartoon cat
- realistic feline anatomy
- soft painterly/cel shading
- muted warm colors
- restrained thin linework
- expressive but natural eyes
- simplified fur shapes
- full body
- 1:1 composition
- transparent background
- the same recognizable cat identity across ages and states

Forbidden style drift:

- no 3D
- no chibi
- no photorealistic rendering
- no flat vector style
- no exaggerated oversized eyes

### Anchor production workflow

For every `breed + age_stage`, the first asset produced is `idle.png`. This
is the **identity anchor**.

Every other state for that exact breed and age must be derived from the anchor.
Preserve coat pattern, face structure, eye color, body proportions, ears, tail,
and other identity-defining features. Change only pose, expression, action, or
condition needed by the state.

Across age stages, preserve the same identity while changing age-appropriate
proportions. Do not independently regenerate each state from scratch.

Transparent PNG is the canonical delivery format. Do not add empty PNG
placeholders just to satisfy the directory matrix.

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
  Redis cache keyed by `(breed, age_stage, state, title)`. DB column is
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
- Produce official assets under
  `bot/assets/cats/<breed>/<age_stage>/<state>.png` using Catibot Art Style v1.
- `idle.png` is the identity anchor for every breed + age combination.
- Do not assume breed alone identifies an asset; age stage and state are both
  part of the identity.
- Keep procedural rendering only as a deliberate fallback while the official
  library is incomplete.
- If rendering overlays/collars on top of library assets, cache by fields that
  include at least `breed + age_stage + state` plus any overlay-changing data.

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
