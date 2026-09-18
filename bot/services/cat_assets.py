"""Central cat-asset vocabulary, lookup rules, and library auditing."""
from __future__ import annotations

from dataclasses import dataclass
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

_ASSET_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")


def get_age_stage(age_days: int | float | str | None) -> str:
    """Derive an asset age stage from age_days without persisting extra state.

    The game uses intentionally short day ranges so every stage can be exercised
    during normal play:
      0-6   -> kitten
      7-20  -> junior
      21-89 -> adult
      90+   -> senior
    """
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


def media_key_candidates(
    state: str,
    breed: str | None = None,
    age_stage: str | None = None,
) -> tuple[str, ...]:
    """Return media keys in strict compatibility lookup order.

    Precedence:
      1. breed + requested age + canonical state
      2. breed + adult + canonical state
      3. legacy breed + original/canonical state
      4. generic original/canonical state

    Duplicate keys are removed while preserving order.
    """
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
    """Resolve a value and report the key that won the fallback chain."""
    for key in media_key_candidates(state, breed, age_stage):
        value = values.get(key)
        if value:
            return value, key
    return default, None


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
    """Count official breed × age × state files in bot/assets/cats.

    PNG is the canonical/recommended format. Common static alternatives count
    as present so the audit remains useful during gradual asset production.
    """
    root = root or (Path(__file__).resolve().parents[1] / "assets" / "cats")
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
