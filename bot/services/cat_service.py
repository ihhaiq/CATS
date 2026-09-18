"""
The orchestration layer between handlers and storage.

Handlers stay thin: they parse input and render output. Everything that decides
what happens to a cat lives here, and everything that decides *the numbers*
lives in domain/rules.py. Three layers, one direction of dependency.

The single most important rule: `refresh()` runs before any read or write of
cat state. It is the only place decay is applied, and it is idempotent — calling
it twice in a row is a no-op because it advances `last_decay_at`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.config import Settings
from bot.core.clock import now
from bot.core.enums import AlertState, Breed, CareAction, EffectType, Emotion
from bot.domain import rules
from bot.domain.entities import CatData, ItemData, UserData
from bot.storage.base import Repository

logger = logging.getLogger("catibot.service")


@dataclass
class RefreshResult:
    cat: CatData
    just_fled: bool = False
    state: AlertState | None = None
    emotion: Emotion = Emotion.NEUTRAL


@dataclass
class CareResult:
    ok: bool
    cat: CatData
    action: CareAction
    seconds_left: int = 0
    points: int = 0
    is_partner: bool = False
    just_fled: bool = False
    reason: str = ""


class CatService:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    # --- reading ----------------------------------------------------------
    async def refresh(self, cat: CatData, *, persist: bool = True) -> RefreshResult:
        """Apply lazy decay, re-derive age, and run the flee check. Idempotent."""
        moment = now()
        decay = rules.compute_decay(
            hunger=cat.hunger,
            happiness=cat.happiness,
            love_bar=cat.love_bar,
            since=cat.last_decay_at,
            now=moment,
        )
        if decay.changed:
            cat.hunger = decay.hunger
            cat.happiness = decay.happiness
            cat.love_bar = decay.love_bar
            cat.last_decay_at = moment

        cat.age_days = rules.age_in_days(cat.created_at, moment)

        just_fled = rules.should_flee(love_bar=cat.love_bar, is_fled=cat.is_fled)
        if just_fled:
            cat.is_fled = True
            cat.fled_at = moment
            logger.info("cat %s fled (owner=%s)", cat.cat_id, cat.owner_id)

        if persist and (decay.changed or just_fled):
            await self.repo.save_cat(cat)

        state = rules.alert_state(
            hunger=cat.hunger,
            happiness=cat.happiness,
            love_bar=cat.love_bar,
            is_fled=cat.is_fled,
            hunger_threshold=self.settings.hunger_alert_threshold,
            happiness_threshold=self.settings.happiness_alert_threshold,
            love_threshold=self.settings.love_alert_threshold,
        )
        emotion = rules.emotion_of(
            hunger=cat.hunger, happiness=cat.happiness, is_fled=cat.is_fled
        )
        return RefreshResult(cat=cat, just_fled=just_fled, state=state, emotion=emotion)

    async def load(self, user_id: int) -> tuple[UserData, CatData | None]:
        user = await self.repo.get_or_create_user(user_id)
        cat = await self.repo.get_active_cat_for(user_id)
        return user, cat

    def cooldowns_for(self, cat: CatData) -> dict[CareAction, int]:
        moment = now()
        out: dict[CareAction, int] = {}
        for action in CareAction:
            _, left = rules.check_cooldown(
                cat.timestamp_for(action.value), self._cooldown(action), moment
            )
            out[action] = left
        return out

    def _cooldown(self, action: CareAction) -> int:
        return {
            CareAction.FEED: self.settings.feed_cooldown,
            CareAction.PLAY: self.settings.play_cooldown,
            CareAction.WALK: self.settings.walk_cooldown,
        }[action]

    # --- writing ----------------------------------------------------------
    async def adopt(
        self,
        user_id: int,
        *,
        name: str,
        breed: Breed | None = None,
        is_guest: bool = False,
    ) -> CatData:
        existing = await self.repo.get_active_cat_for(user_id)
        if existing is not None:
            raise ValueError("already_has_cat")
        clean = rules.validate_cat_name(name)
        cat = await self.repo.create_cat(
            owner_id=user_id,
            name=clean,
            breed=breed or rules.assign_random_breed(),
            is_guest=is_guest,
        )
        await self.repo.add_points(user_id, rules.ADOPT_BONUS, "adopt")
        return cat

    async def do_care(self, user: UserData, cat: CatData, action: CareAction) -> CareResult:
        refreshed = await self.refresh(cat)
        cat = refreshed.cat
        if cat.is_fled:
            return CareResult(False, cat, action, reason="fled", just_fled=refreshed.just_fled)

        ready, left = rules.check_cooldown(
            cat.timestamp_for(action.value), self._cooldown(action), now()
        )
        if not ready:
            return CareResult(False, cat, action, seconds_left=left, reason="cooldown")

        cat.hunger, cat.happiness, cat.love_bar = rules.apply_care(
            action=action, hunger=cat.hunger, happiness=cat.happiness, love_bar=cat.love_bar
        )
        moment = now()
        cat.touch(action.value, moment)
        cat.last_decay_at = moment

        is_partner = cat.partner_id == user.user_id
        if is_partner:
            cat.partner_affinity = rules.clamp(
                cat.partner_affinity + rules.PARTNER_AFFINITY_PER_ACTION
            )

        # The need was met, so let the sweep alert again next time it appears.
        new_state = rules.alert_state(
            hunger=cat.hunger,
            happiness=cat.happiness,
            love_bar=cat.love_bar,
            is_fled=cat.is_fled,
            hunger_threshold=self.settings.hunger_alert_threshold,
            happiness_threshold=self.settings.happiness_alert_threshold,
            love_threshold=self.settings.love_alert_threshold,
        )
        if new_state is None or new_state.value != cat.last_notified_state:
            cat.last_notified_state = None
            cat.last_notified_at = None

        await self.repo.save_cat(cat)
        points = rules.CARE_POINTS[action]
        await self.repo.add_points(user.user_id, points, f"care:{action.value}")
        return CareResult(True, cat, action, points=points, is_partner=is_partner)

    async def rename(self, cat: CatData, new_name: str) -> CatData:
        cat.name = rules.validate_cat_name(new_name)
        await self.repo.save_cat(cat)
        return cat

    async def use_item(self, user: UserData, cat: CatData, item: ItemData) -> CatData:
        await self.refresh(cat)
        effect = item.effect_type
        if effect == EffectType.HUNGER_DOWN.value:
            cat.hunger = rules.clamp(cat.hunger - item.effect_value)
        elif effect == EffectType.HAPPINESS_UP.value:
            cat.happiness = rules.clamp(cat.happiness + item.effect_value)
        elif effect == EffectType.LOVE_UP.value:
            cat.love_bar = rules.clamp(cat.love_bar + item.effect_value)
        elif effect == EffectType.COSMETIC_TITLE.value:
            cat.title = f"👑 {item.name.split(':')[-1].strip()}"
        await self.repo.change_inventory(user.user_id, item.item_id, -1)
        await self.repo.save_cat(cat)
        return cat

    async def buy(self, user: UserData, item: ItemData) -> tuple[bool, int]:
        if user.points < item.price:
            return False, user.points
        balance = await self.repo.add_points(user.user_id, -item.price, f"buy:{item.item_id}")
        await self.repo.change_inventory(user.user_id, item.item_id, +1)
        user.points = balance
        return True, balance

    async def readopt(self, user_id: int, cat_id: int) -> CatData:
        cat = await self.repo.get_cat(cat_id)
        if cat is None or not cat.is_fled:
            raise ValueError("not_in_shelter")
        if await self.repo.get_active_cat_for(user_id) is not None:
            raise ValueError("already_has_cat")

        moment = now()
        cat.owner_id = user_id
        cat.partner_id = None
        cat.partner_affinity = 0
        cat.is_fled = False
        cat.fled_at = None
        cat.love_bar = rules.SHELTER_READOPT_LOVE
        cat.hunger = 40
        cat.happiness = 60
        cat.last_fed = cat.last_played = cat.last_walk = cat.last_decay_at = moment
        cat.last_notified_state = None
        cat.last_notified_at = None
        await self.repo.save_cat(cat)
        return cat

    async def attach_partner(self, cat: CatData, partner_id: int) -> tuple[bool, str]:
        if partner_id == cat.owner_id:
            return False, "self"
        if cat.partner_id and cat.partner_id != partner_id:
            return False, "taken"
        if cat.partner_id == partner_id:
            return True, "already"
        cat.partner_id = partner_id
        await self.repo.save_cat(cat)
        await self.repo.add_points(cat.owner_id, rules.PARTNER_JOIN_BONUS, "partner_join")
        return True, "joined"
