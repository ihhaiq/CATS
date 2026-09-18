"""Cat asset vocabulary, visual-state rules, filesystem lookup, and auditing."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from bot.core.enums import Breed

BREED_POOL: tuple[str, ...] = tuple(breed.value for breed in Breed)
AGE_STAGES: tuple[str, ...] = ("kitten", "junior", "adult", "senior")
CAT_STATES: tuple[str, ...] = (
    "idle",
    "happy",
    "hungry",
    "feed",
    "play",
    "walk",
    "talk",
    "sleep",
    "angry",
    "sick",
)

LEGACY_STATE_MAP: dict[str, str] = {
    "status": "idle",
    "cat_angry_sleep": "angry",
}

EXPLICIT_VISUAL_STATES = frozenset(CAT_STATES) - {"idle"}
DEFAULT_HUNGRY_VISUAL_THRESHOLD = 70
CAT_ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets" / "cats"
_ASSET_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")


def get_age_stage(age_days: int | float | str | None) -> str:
    """Derive an asset age stage from age_days without persisting extra state."""
    try:
        days = int(age_days or 0)
    except (TypeError, ValueError):
        days = 0
    days = max(0, days)

    if days <= 6:
        return "kitten"
    if days <= 20:
        return "junior"
    if days <= 89:
        return "adult"
    return "senior"


def normalize_cat_state(state: str | None) -> str:
    """Map known legacy runtime state names to the canonical asset vocabulary."""
    value = (state or "idle").strip().lower()
    return LEGACY_STATE_MAP.get(value, value)


def _cat_is_sleeping(cat: Mapping[str, object], now: datetime | None = None) -> bool:
    sleep_until = cat.get("sleep_until")
    if not sleep_until:
        return False
    try:
        until = datetime.fromisoformat(str(sleep_until))
    except (TypeError, ValueError):
        return False
    return until > (now or datetime.utcnow())


def _cat_has_active_refusal(
    cat: Mapping[str, object],
    now: datetime | None = None,
) -> bool:
    refusal_until = cat.get("action_refusal_until")
    if not refusal_until:
        return False
    try:
        refusal_ts = float(refusal_until)
    except (TypeError, ValueError):
        return False
    return refusal_ts > (now or datetime.utcnow()).timestamp()


def resolve_cat_visual_state(
    cat: Mapping[str, object],
    requested_state: str | None = "status",
    *,
    hunger_threshold: int = DEFAULT_HUNGRY_VISUAL_THRESHOLD,
    now: datetime | None = None,
) -> str:
    """Resolve the one canonical visual state used for an asset.

    Precedence:
      1. Explicit action/visual states win (feed/play/walk/talk/sleep/angry/etc).
      2. For status/idle requests, an actively sleeping cat uses sleep.
      3. Active refusal uses angry.
      4. A future sick flag uses sick.
      5. Hunger at/above the threshold uses hungry.
      6. Otherwise idle.

    Legacy names are normalized before precedence is applied:
    status -> idle and cat_angry_sleep -> angry.
    """
    state = normalize_cat_state(requested_state)
    if state in EXPLICIT_VISUAL_STATES:
        return state

    if _cat_is_sleeping(cat, now):
        return "sleep"
    if _cat_has_active_refusal(cat, now):
        return "angry"
    if bool(cat.get("is_sick") or cat.get("sick")):
        return "sick"

    try:
        hunger = int(cat.get("hunger", 0) or 0)
    except (TypeError, ValueError):
        hunger = 0
    if hunger >= hunger_threshold:
        return "hungry"
    return "idle"


def media_key_candidates(
    state: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> tuple[str, ...]:
    """Return Telegram media keys in compatibility fallback order."""
    original_state = (state or "idle").strip().lower()
    canonical_state = normalize_cat_state(original_state)
    keys: list[str] = []

    if breed and age_stage:
        keys.append(f"{breed}:{age_stage}:{canonical_state}")
        if age_stage != "adult":
            keys.append(f"{breed}:adult:{canonical_state}")

    if breed:
        keys.append(f"{breed}:{original_state}")
        if canonical_state != original_state:
            keys.append(f"{breed}:{canonical_state}")

    keys.append(original_state)
    if canonical_state != original_state:
        keys.append(canonical_state)

    return tuple(dict.fromkeys(keys))


def resolve_media_value(
    values: Mapping[str, str],
    state: str,
    breed: str | None = None,
    age_stage: str | None = None,
    default: str = "",
) -> tuple[str, str | None]:
    """Resolve a legacy Telegram value and report the key that won."""
    for key in media_key_candidates(state, breed, age_stage):
        value = values.get(key)
        if value:
            return value, key
    return default, None


@dataclass(frozen=True)
class LocalAsset:
    path: Path
    breed: str
    age_stage: str | None
    state: str
    cache_key: str
    relative_path: str


def local_asset_candidates(
    breed: str,
    age_stage: str,
    state: str,
    *,
    root: Path | None = None,
) -> tuple[LocalAsset, ...]:
    """Return local filesystem candidates in official fallback order.

    Order:
      1. breed/requested-age/state
      2. breed/adult/state
      3. legacy breed/state
      4. generic state at the asset root
    """
    root = root or CAT_ASSETS_ROOT
    state = normalize_cat_state(state)
    candidates: list[LocalAsset] = []

    def add(path: Path, source_age: str | None) -> None:
        relative = path.relative_to(root).as_posix()
        candidates.append(
            LocalAsset(
                path=path,
                breed=breed,
                age_stage=source_age,
                state=state,
                cache_key=f"asset:{relative}",
                relative_path=relative,
            )
        )

    add(root / breed / age_stage / f"{state}.png", age_stage)
    if age_stage != "adult":
        add(root / breed / "adult" / f"{state}.png", "adult")
    add(root / breed / f"{state}.png", None)
    add(root / f"{state}.png", None)

    unique: dict[str, LocalAsset] = {}
    for item in candidates:
        unique.setdefault(str(item.path), item)
    return tuple(unique.values())


def resolve_local_asset(
    breed: str,
    age_stage: str,
    state: str,
    *,
    root: Path | None = None,
) -> LocalAsset | None:
    """Return the first existing local asset according to filesystem precedence."""
    for candidate in local_asset_candidates(
        breed,
        age_stage,
        state,
        root=root,
    ):
        if candidate.path.is_file():
            return candidate
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_relative_path(breed: str, age_stage: str, state: str) -> Path:
    return Path(breed) / age_stage / f"{normalize_cat_state(state)}.png"


@dataclass(frozen=True)
class AssetLibraryReport:
    total_expected: int
    present: int
    missing: tuple[str, ...]

    @property
    def missing_count(self) -> int:
        return self.total_expected - self.present


def inspect_cat_asset_library(root: Path | None = None) -> AssetLibraryReport:
    """Count official breed × age × state files in bot/assets/cats."""
    root = root or CAT_ASSETS_ROOT
    missing: list[str] = []
    present = 0

    for breed in BREED_POOL:
        for age_stage in AGE_STAGES:
            for state in CAT_STATES:
                base = root / breed / age_stage / state
                if any(base.with_suffix(ext).is_file() for ext in _ASSET_EXTENSIONS):
                    present += 1
                else:
                    missing.append(asset_relative_path(breed, age_stage, state).as_posix())

    total = len(BREED_POOL) * len(AGE_STAGES) * len(CAT_STATES)
    return AssetLibraryReport(
        total_expected=total,
        present=present,
        missing=tuple(missing),
    )
