"""Enumerations shared by the domain layer, the renderer and the handlers."""
from __future__ import annotations

from enum import Enum


class Breed(str, Enum):
    ORANGE_TABBY = "orange_tabby"
    BLACK = "black"
    SIAMESE = "siamese"
    BRITISH_GREY = "british_shorthair_grey"
    CALICO = "calico"
    WHITE = "white"

    @property
    def label_ar(self) -> str:
        return BREED_LABELS_AR[self]

    @property
    def palette(self) -> tuple[str, str]:
        """(fur, accent) — used by the procedural fallback renderer."""
        return BREED_PALETTE[self]


BREED_LABELS_AR: dict[Breed, str] = {
    Breed.ORANGE_TABBY: "🟠 مشمشي مخطط",
    Breed.BLACK: "⚫ أسود",
    Breed.SIAMESE: "🤎 سيامي",
    Breed.BRITISH_GREY: "🩶 بريطاني رمادي",
    Breed.CALICO: "🎨 كاليكو",
    Breed.WHITE: "⚪ أبيض",
}

BREED_PALETTE: dict[Breed, tuple[str, str]] = {
    Breed.ORANGE_TABBY: ("#E08A3C", "#B45F19"),
    Breed.BLACK: ("#3B3B42", "#23232A"),
    Breed.SIAMESE: ("#E7D6C0", "#7A5B47"),
    Breed.BRITISH_GREY: ("#9AA3AC", "#6E777F"),
    Breed.CALICO: ("#F0E2D0", "#C9713F"),
    Breed.WHITE: ("#F4F1EC", "#D6CFC5"),
}


class Emotion(str, Enum):
    HAPPY = "happy"
    NEUTRAL = "neutral"
    SAD = "sad"
    FLED = "fled"

    @property
    def emoji(self) -> str:
        return {"happy": "😻", "neutral": "😺", "sad": "😿", "fled": "🙀"}[self.value]


class AlertState(str, Enum):
    """The condition the notification sweep reports on."""

    HUNGRY = "hungry"
    SAD = "sad"
    LOVE_LOW = "love_low"
    FLED = "fled"


class CareAction(str, Enum):
    FEED = "feed"
    PLAY = "play"
    WALK = "walk"

    @property
    def emoji(self) -> str:
        return {"feed": "🍖", "play": "🎾", "walk": "🚶"}[self.value]

    @property
    def label_ar(self) -> str:
        return {"feed": "إطعام", "play": "لعب", "walk": "نزهة"}[self.value]


class EffectType(str, Enum):
    HUNGER_DOWN = "hunger_down"
    HAPPINESS_UP = "happiness_up"
    LOVE_UP = "love_up"
    COSMETIC_TITLE = "cosmetic_title"
