"""
Developer tooling.

The problem this solves: every interesting behaviour in this bot is on an
hours-long timer. Waiting 20 hours to see whether the "hungry" alert fires is
not a testing strategy. These commands let you force any state, jump the clock,
run the sweep on demand, and assert the whole rule set in one tap.

Access: a user in ADMIN_IDS, or anyone when DEV_MODE=true and ADMIN_IDS is
empty (handy for local runs, refused in production because a deployed bot
should always have ADMIN_IDS set).
"""
from __future__ import annotations

import platform
import sys
import time

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import Settings
from bot.core import keyboards as kb
from bot.core import texts
from bot.core.clock import clock, now
from bot.core.enums import Breed, CareAction, Emotion
from bot.core.keyboards import CB
from bot.domain import rules
from bot.domain.entities import UserData
from bot.handlers._shared import reply_text, send_cat_card
from bot.services import scenarios
from bot.services.cat_service import CatService
from bot.services.image_renderer import assets_report, render_cat

router = Router(name="dev")

STARTED_AT = time.time()

STATE_PRESETS: dict[str, dict[str, int]] = {
    "happy": {"hunger": 10, "happiness": 95, "love_bar": 95},
    "neutral": {"hunger": 45, "happiness": 60, "love_bar": 70},
    "hungry": {"hunger": 92, "happiness": 60, "love_bar": 60},
    "sad": {"hunger": 30, "happiness": 12, "love_bar": 50},
    "love_low": {"hunger": 85, "happiness": 20, "love_bar": 8},
    "fled": {"hunger": 100, "happiness": 0, "love_bar": 0},
}


def _allowed(settings: Settings, user_id: int) -> bool:
    if settings.admin_ids:
        return settings.is_admin(user_id)
    return settings.dev_mode


async def _guard(event: Message | CallbackQuery, settings: Settings, user: UserData) -> bool:
    if _allowed(settings, user.user_id):
        return True
    if isinstance(event, CallbackQuery):
        await event.answer(texts.NOT_ADMIN, show_alert=True)
    else:
        await event.answer(texts.NOT_ADMIN)
    return False


# --- panel -----------------------------------------------------------------
@router.message(Command("dev"))
async def cmd_dev(message: Message, settings: Settings, user: UserData) -> None:
    if not await _guard(message, settings, user):
        return
    await message.answer(_panel_text(settings), reply_markup=kb.dev_panel())


def _panel_text(settings: Settings) -> str:
    return (
        "🛠️ <b>لوحة المطور</b>\n\n"
        f"⚙️ {texts.esc(settings.describe())}\n"
        f"🕒 الساعة: <b>{texts.esc(clock.describe())}</b>\n\n"
        "<b>الأوامر النصية</b>\n"
        "<code>/dev_health</code> — فحص شامل\n"
        "<code>/dev_state hungry|sad|love_low|fled|happy|neutral</code>\n"
        "<code>/dev_set hunger 90</code> — تعديل قيمة مباشرة\n"
        "<code>/dev_time +6h</code> · <code>/dev_time reset</code>\n"
        "<code>/dev_cooldown</code> — صفّر التبريد\n"
        "<code>/dev_points 500</code>\n"
        "<code>/dev_sweep</code> — نفّذ الفحص الدوري حالاً\n"
        "<code>/dev_render</code> — كل الحالات كصور\n"
        "<code>/dev_scenarios</code> — اختبار ذاتي كامل\n"
        "<code>/dev_reset</code> — امسح بياناتي"
    )


# --- health ----------------------------------------------------------------
@router.message(Command("dev_health"))
@router.callback_query(F.data.startswith("dev:health"))
async def dev_health(
    event: Message | CallbackQuery, settings: Settings, service: CatService, user: UserData
) -> None:
    if not await _guard(event, settings, user):
        return
    if isinstance(event, CallbackQuery):
        await event.answer()

    health = await service.repo.health()
    art = assets_report()
    uptime = int(time.time() - STARTED_AT)
    procedural = sum(1 for v in art["breeds"].values() if v == "procedural")

    lines = [
        "🩺 <b>فحص النظام</b>",
        "",
        f"💾 التخزين: <b>{health.get('backend')}</b> "
        f"{'✅' if health.get('ok') else '❌'} "
        f"({'دائم' if health.get('persistent') else 'مؤقت — وضع الضيف'})",
        f"👥 مستخدمين: <b>{health.get('users', 0)}</b> · "
        f"🐱 قطط: <b>{health.get('cats', 0)}</b> · "
        f"🙀 هاربة: <b>{health.get('fled', 0)}</b>",
        f"🛍️ أغراض بالمتجر: <b>{health.get('items', 0)}</b>",
        "",
        f"🕒 الساعة: <b>{texts.esc(clock.describe())}</b>",
        f"⏱️ التشغيل: <b>{rules.human_duration_ar(uptime)}</b>",
        f"🐍 بايثون {platform.python_version()} · {sys.platform}",
        "",
        f"🖼️ صور: <b>{6 - procedural}/6</b> سلالة عندها رسوم جاهزة "
        f"({procedural} رسم تلقائي)",
        f"🔤 خطوط: {texts.esc(', '.join(art['fonts']))}",
        f"🔠 تشكيل عربي: {'✅' if art['arabic_shaping'] else '⚠️ غير مثبت'}",
        "",
        f"🔔 الفحص كل <b>{settings.sweep_interval_minutes}</b> دقيقة · "
        f"مانع التكرار <b>{rules.human_duration_ar(settings.notification_min_gap)}</b>",
        f"⏳ التبريد: إطعام {rules.human_duration_ar(settings.feed_cooldown)} · "
        f"لعب {rules.human_duration_ar(settings.play_cooldown)} · "
        f"نزهة {rules.human_duration_ar(settings.walk_cooldown)}",
    ]
    await reply_text(event, "\n".join(lines), kb.dev_panel())


# --- forcing state ---------------------------------------------------------
async def _apply_preset(
    event: Message | CallbackQuery,
    preset: str,
    service: CatService,
    user: UserData,
    guest: bool,
) -> None:
    values = STATE_PRESETS.get(preset)
    if values is None:
        await reply_text(
            event, f"❓ حالة غير معروفة. المتاح: {', '.join(STATE_PRESETS)}"
        )
        return

    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        cat = await service.adopt(user.user_id, name="تجريبية", is_guest=guest)

    for key, value in values.items():
        setattr(cat, key, value)
    cat.last_decay_at = now()
    cat.last_notified_state = None
    cat.last_notified_at = None
    if preset == "fled":
        cat.is_fled = True
        cat.fled_at = now()
    else:
        cat.is_fled = False
        cat.fled_at = None
    await service.repo.save_cat(cat)

    user = await service.repo.get_or_create_user(user.user_id)
    await send_cat_card(
        event, service, user, cat, guest=guest, header=f"🧪 تم فرض الحالة: <code>{preset}</code>"
    )


@router.message(Command("dev_state"))
async def cmd_dev_state(
    message: Message,
    command: CommandObject,
    settings: Settings,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    if not await _guard(message, settings, user):
        return
    await _apply_preset(
        message, (command.args or "").strip().lower(), service, user, is_guest_mode
    )


@router.callback_query(F.data.startswith("dev:state"))
async def cb_dev_state(
    callback: CallbackQuery,
    settings: Settings,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    if not await _guard(callback, settings, user):
        return
    await callback.answer()
    await _apply_preset(callback, CB.parse(callback.data or "").arg, service, user, is_guest_mode)


@router.message(Command("dev_set"))
async def cmd_dev_set(
    message: Message,
    command: CommandObject,
    settings: Settings,
    service: CatService,
    user: UserData,
    is_guest_mode: bool,
) -> None:
    if not await _guard(message, settings, user):
        return
    parts = (command.args or "").split()
    allowed = {"hunger", "happiness", "love_bar", "partner_affinity", "age_days"}
    if len(parts) != 2 or parts[0] not in allowed or not parts[1].lstrip("-").isdigit():
        await message.answer(
            "الاستعمال: <code>/dev_set hunger 90</code>\n"
            f"القيم المسموحة: {', '.join(sorted(allowed))}"
        )
        return

    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        await message.answer(texts.NO_CAT)
        return
    field, raw = parts[0], int(parts[1])
    setattr(cat, field, raw if field == "age_days" else rules.clamp(raw))
    cat.last_decay_at = now()
    await service.repo.save_cat(cat)
    await send_cat_card(
        message, service, user, cat, guest=is_guest_mode,
        header=f"🧪 <code>{field} = {getattr(cat, field)}</code>",
    )


@router.message(Command("dev_time"))
async def cmd_dev_time(
    message: Message, command: CommandObject, settings: Settings, user: UserData
) -> None:
    if not await _guard(message, settings, user):
        return
    arg = (command.args or "").strip().lower()
    if arg in {"reset", "0"}:
        clock.reset()
    elif arg in {"freeze", "stop"}:
        clock.freeze()
    elif arg in {"unfreeze", "run"}:
        clock.unfreeze()
    else:
        try:
            value = float(arg.rstrip("hd").lstrip("+"))
            clock.advance(days=value) if arg.endswith("d") else clock.advance(hours=value)
        except ValueError:
            await message.answer(
                "الاستعمال: <code>/dev_time +6h</code> · <code>+2d</code> · "
                "<code>reset</code> · <code>freeze</code>"
            )
            return
    await message.answer(
        f"🕒 الساعة الآن: <b>{texts.esc(clock.describe())}</b>\n"
        f"<i>{now().strftime('%Y-%m-%d %H:%M')} UTC (محاكاة)</i>",
        reply_markup=kb.dev_panel(),
    )


@router.callback_query(F.data.startswith("dev:time"))
async def cb_dev_time(callback: CallbackQuery, settings: Settings, user: UserData) -> None:
    if not await _guard(callback, settings, user):
        return
    arg = CB.parse(callback.data or "").arg
    if arg == "reset":
        clock.reset()
    else:
        clock.advance(hours=float(arg or 1))
    await callback.answer(f"🕒 {clock.describe()}")
    await reply_text(callback, _panel_text(settings), kb.dev_panel())


@router.message(Command("dev_cooldown"))
async def cmd_dev_cooldown(
    message: Message, settings: Settings, service: CatService, user: UserData
) -> None:
    if not await _guard(message, settings, user):
        return
    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        await message.answer(texts.NO_CAT)
        return
    from bot.domain.entities import _actionable

    cat.last_fed = cat.last_played = cat.last_walk = _actionable()
    await service.repo.save_cat(cat)
    await message.answer("⏳ تم تصفير التبريد — كل الأفعال متاحة الآن.")


@router.message(Command("dev_points"))
async def cmd_dev_points(
    message: Message,
    command: CommandObject,
    settings: Settings,
    service: CatService,
    user: UserData,
) -> None:
    if not await _guard(message, settings, user):
        return
    raw = (command.args or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("الاستعمال: <code>/dev_points 500</code>")
        return
    balance = await service.repo.add_points(user.user_id, int(raw), "dev_grant")
    await message.answer(f"⭐ الرصيد الآن: <b>{balance}</b>")


# --- sweep / render / scenarios --------------------------------------------
@router.message(Command("dev_sweep"))
@router.callback_query(F.data.startswith("dev:sweep"))
async def dev_sweep(
    event: Message | CallbackQuery, settings: Settings, user: UserData, sweeper=None
) -> None:
    if not await _guard(event, settings, user):
        return
    if isinstance(event, CallbackQuery):
        await event.answer("🔔 جاري الفحص…")
    if sweeper is None:
        await reply_text(event, "⚠️ خدمة الإشعارات مو شغالة بهذا التشغيل.")
        return
    report = await sweeper.run_once()
    await reply_text(event, report.as_text(), kb.dev_panel())


@router.message(Command("dev_render"))
@router.callback_query(F.data.startswith("dev:render"))
async def dev_render(
    event: Message | CallbackQuery, settings: Settings, service: CatService, user: UserData
) -> None:
    if not await _guard(event, settings, user):
        return
    if isinstance(event, CallbackQuery):
        await event.answer("🖼️ …")

    cat = await service.repo.get_active_cat_for(user.user_id)
    if cat is None:
        from bot.domain.entities import CatData

        cat = CatData(
            cat_id=0, owner_id=user.user_id, name="عيّنة",
            breed=Breed.ORANGE_TABBY, id_number="000000",
        )

    msg = event if isinstance(event, Message) else event.message
    for emotion in (Emotion.HAPPY, Emotion.NEUTRAL, Emotion.SAD, Emotion.FLED):
        photo = BufferedInputFile(
            render_cat(cat, emotion), filename=f"{emotion.value}.png"
        )
        await msg.answer_photo(photo, caption=f"{emotion.emoji} <code>{emotion.value}</code>")


@router.message(Command("dev_scenarios"))
@router.callback_query(F.data.startswith("dev:scenarios"))
async def dev_scenarios(
    event: Message | CallbackQuery, settings: Settings, user: UserData
) -> None:
    if not await _guard(event, settings, user):
        return
    if isinstance(event, CallbackQuery):
        await event.answer("🧪 جاري التشغيل…")
    checks = await scenarios.run_all()
    verbose = isinstance(event, Message) and "full" in (event.text or "")
    await reply_text(event, scenarios.summarize(checks, verbose=verbose), kb.dev_panel())


@router.message(Command("dev_reset"))
@router.callback_query(F.data.startswith("dev:reset"))
async def dev_reset(
    event: Message | CallbackQuery, settings: Settings, service: CatService, user: UserData
) -> None:
    if not await _guard(event, settings, user):
        return
    if isinstance(event, CallbackQuery):
        await event.answer()
    await service.repo.reset_user(user.user_id)
    await reply_text(event, "🧹 تم مسح بياناتك. اكتب /start من جديد.", kb.back_to_menu())


@router.message(Command("dev_whoami"))
async def cmd_whoami(message: Message, settings: Settings, user: UserData) -> None:
    await message.answer(
        f"🆔 <code>{user.user_id}</code>\n"
        f"⭐ نقاط: {user.points}\n"
        f"🛠️ مطور: {'نعم' if _allowed(settings, user.user_id) else 'لا'}\n"
        f"💾 التخزين: <code>{settings.storage_mode}</code>"
    )
