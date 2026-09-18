"""
Inline keyboards.

Callback payloads follow a flat `ns:action:arg` scheme parsed by `CB.parse()`.
Telegram caps callback_data at 64 bytes, so args stay numeric or short.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.core.enums import CareAction
from bot.domain.entities import CatData, ItemData
from bot.domain.rules import human_duration_ar


@dataclass(frozen=True)
class CB:
    ns: str
    action: str
    arg: str = ""

    def pack(self) -> str:
        raw = f"{self.ns}:{self.action}:{self.arg}"
        return raw[:64]

    @staticmethod
    def parse(data: str) -> "CB":
        parts = (data or "").split(":")
        parts += [""] * (3 - len(parts))
        return CB(parts[0], parts[1], parts[2])


def _btn(text: str, cb: CB) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


# --- main menu -------------------------------------------------------------
def main_menu(*, has_cat: bool, guest: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_cat:
        kb.row(_btn("📊 حالة قطتي", CB("cat", "status")))
        kb.row(
            _btn("🍖 إطعام", CB("care", "feed")),
            _btn("🎾 لعب", CB("care", "play")),
            _btn("🚶 نزهة", CB("care", "walk")),
        )
    else:
        kb.row(_btn("🐾 تبنّي قطة الآن", CB("cat", "adopt")))
    kb.row(
        _btn("🛍️ المتجر", CB("shop", "open")),
        _btn("🎒 حقيبتي", CB("bag", "open")),
    )
    kb.row(
        _btn("🏠 الملجأ", CB("shelter", "open")),
        _btn("🤝 شريك", CB("partner", "invite")),
    )
    kb.row(_btn("📖 المساعدة", CB("nav", "help")))
    if guest:
        kb.row(_btn("💾 احفظ تقدمي", CB("guest", "save")))
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(_btn("⬅️ القائمة الرئيسية", CB("nav", "menu")))
    return kb.as_markup()


# --- cat -------------------------------------------------------------------
def cat_actions(
    cat: CatData,
    *,
    cooldowns: dict[CareAction, int] | None = None,
    guest: bool = False,
) -> InlineKeyboardMarkup:
    """Care buttons; ones on cooldown show the remaining time instead of a verb."""
    cooldowns = cooldowns or {}
    kb = InlineKeyboardBuilder()

    row = []
    for action in (CareAction.FEED, CareAction.PLAY, CareAction.WALK):
        left = cooldowns.get(action, 0)
        if left > 0:
            label = f"{action.emoji} ⏳ {human_duration_ar(left)}"
        else:
            label = f"{action.emoji} {action.label_ar}"
        row.append(_btn(label, CB("care", action.value)))
    kb.row(*row)

    kb.row(
        _btn("🔄 تحديث", CB("cat", "status")),
        _btn("✏️ تغيير الاسم", CB("cat", "rename")),
    )
    kb.row(
        _btn("🛍️ المتجر", CB("shop", "open")),
        _btn("🤝 دعوة شريك", CB("partner", "invite")),
    )
    if guest:
        kb.row(_btn("🎲 بدّل القطة", CB("cat", "reroll")))
        kb.row(_btn("💾 احفظ تقدمي", CB("guest", "save")))
    kb.row(_btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()


def adopt_prompt(*, guest: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(_btn("🎲 قطة عشوائية", CB("cat", "adopt_random")))
    kb.row(_btn("✏️ أسميها بنفسي", CB("cat", "adopt_named")))
    if guest:
        kb.row(_btn("👤 جرب كضيف", CB("guest", "quickstart")))
    kb.row(_btn("⬅️ رجوع", CB("nav", "menu")))
    return kb.as_markup()


def fled_actions() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(_btn("🏠 شوف الملجأ", CB("shelter", "open")))
    kb.row(_btn("🐾 تبنّي قطة جديدة", CB("cat", "adopt")))
    kb.row(_btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()


def alert_actions(action: CareAction | None) -> InlineKeyboardMarkup:
    """Keyboard attached to a proactive notification — one tap to fix it."""
    kb = InlineKeyboardBuilder()
    if action is not None:
        kb.row(_btn(f"{action.emoji} {action.label_ar} الآن", CB("care", action.value)))
    kb.row(
        _btn("📊 الحالة", CB("cat", "status")),
        _btn("🔕 كتم ٦ ساعات", CB("notif", "snooze")),
    )
    return kb.as_markup()


# --- shop / bag ------------------------------------------------------------
def shop_keyboard(items: list[ItemData], points: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        affordable = points >= item.price
        mark = "" if affordable else "🔒 "
        kb.row(
            _btn(
                f"{mark}{item.emoji} {item.name} · {item.price}⭐",
                CB("shop", "buy", str(item.item_id)),
            )
        )
    kb.row(_btn("🎒 حقيبتي", CB("bag", "open")), _btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()


def bag_keyboard(rows: list[tuple[ItemData, int]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item, qty in rows:
        kb.row(
            _btn(f"{item.emoji} {item.name} ×{qty}", CB("bag", "use", str(item.item_id)))
        )
    kb.row(_btn("🛍️ المتجر", CB("shop", "open")), _btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()


def shelter_keyboard(cats: list[CatData]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cat in cats[:10]:
        kb.row(_btn(f"🏡 تبنّي {cat.name}", CB("shelter", "adopt", str(cat.cat_id))))
    kb.row(_btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()


def confirm(action: str, arg: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        _btn("✅ تأكيد", CB("confirm", action, arg)),
        _btn("❌ إلغاء", CB("nav", "menu")),
    )
    return kb.as_markup()


# --- developer panel -------------------------------------------------------
def dev_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(_btn("🩺 فحص النظام", CB("dev", "health")))
    kb.row(
        _btn("🍖 جوعانة", CB("dev", "state", "hungry")),
        _btn("😔 زهقانة", CB("dev", "state", "sad")),
    )
    kb.row(
        _btn("💔 حب منخفض", CB("dev", "state", "love_low")),
        _btn("🙀 هاربة", CB("dev", "state", "fled")),
    )
    kb.row(_btn("😻 ممتازة", CB("dev", "state", "happy")))
    kb.row(
        _btn("⏩ +1 ساعة", CB("dev", "time", "1")),
        _btn("⏩ +6 ساعات", CB("dev", "time", "6")),
        _btn("⏩ +24 ساعة", CB("dev", "time", "24")),
    )
    kb.row(_btn("↩️ صفّر الوقت", CB("dev", "time", "reset")))
    kb.row(
        _btn("🔔 نفّذ الفحص الدوري", CB("dev", "sweep")),
        _btn("🖼️ اختبر الصورة", CB("dev", "render")),
    )
    kb.row(_btn("🧪 شغّل كل السيناريوهات", CB("dev", "scenarios")))
    kb.row(_btn("🧹 صفّر بياناتي", CB("dev", "reset")))
    kb.row(_btn("⬅️ القائمة", CB("nav", "menu")))
    return kb.as_markup()
