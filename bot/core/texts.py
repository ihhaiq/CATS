"""
Every string the user sees, in one file.

Keeping copy out of the handlers means the tone can be edited without touching
logic, and a second language is a dict swap away. All output is HTML parse mode,
so anything interpolated from user input goes through `esc()`.
"""
from __future__ import annotations

from html import escape

from bot.core.enums import AlertState, CareAction, Emotion
from bot.domain.entities import CatData, ItemData, UserData
from bot.domain.rules import human_duration_ar

FULL = "█"
EMPTY = "░"


def esc(text: str) -> str:
    return escape(str(text), quote=False)


def bar(value: int, width: int = 10, *, invert: bool = False) -> str:
    """A 0-100 value as a block bar. `invert` for stats where low is good."""
    value = max(0, min(100, int(value)))
    filled = round(value / 100 * width)
    shown = FULL * filled + EMPTY * (width - filled)
    return shown


def stat_line(emoji: str, label: str, value: int, *, invert: bool = False) -> str:
    dot = _health_dot(value, invert=invert)
    return f"{emoji} <b>{label}</b>  <code>{bar(value)}</code> {value}% {dot}"


def _health_dot(value: int, *, invert: bool) -> str:
    score = 100 - value if invert else value
    if score >= 70:
        return "🟢"
    if score >= 35:
        return "🟡"
    return "🔴"


# --- guest -----------------------------------------------------------------
GUEST_BANNER = "👤 <i>وضع الضيف — تقدر تجرب كلشي بدون تسجيل.</i>"

WELCOME = (
    "🐾 <b>أهلاً بيك في كاتي بوت!</b>\n\n"
    "هنا تربي قطة افتراضية: تأكلها، تلعب وياها، تطلعها نزهة، "
    "وتجمع نقاط تشتري بيها أغراض من المتجر.\n\n"
    "اضغط الأزرار تحت حتى تبدي."
)

MENU = "🐾 <b>القائمة الرئيسية</b>"

GUEST_WELCOME = (
    "🐾 <b>أهلاً بيك في كاتي بوت!</b>\n\n"
    "هنا تربي قطة افتراضية: تأكلها، تلعب وياها، تطلعها نزهة، "
    "وتجمع نقاط تشتري بيها أغراض من المتجر.\n\n"
    "👤 <b>وضع الضيف شغال هسه</b> — ما تحتاج تسجيل ولا حساب. "
    "اضغط الزر وخذلك قطة بثانية.\n\n"
    "<i>ملاحظة: تقدم الضيف مؤقت، ويمكن ينمسح إذا البوت أعاد التشغيل.</i>"
)

GUEST_ADOPT_INTRO = (
    "🎁 <b>قطة الضيف جاهزة!</b>\n\n"
    "اخترنالك قطة عشوائية حتى تبدي بسرعة. "
    "تكدر تغير اسمها أو تبدلها من الأزرار تحت."
)

GUEST_UPGRADE_HINT = (
    "💾 <b>خلي تقدمك يبقى</b>\n\n"
    "وضع الضيف يشتغل بذاكرة مؤقتة. لتثبيت القطة والنقاط، "
    "شغّل البوت مع قاعدة بيانات (<code>DATABASE_URL</code>) أو استخدم /save."
)

SAVE_IN_GUEST = (
    "💾 التخزين الدائم مو مفعّل بهذا التشغيل.\n"
    "المطور يقدر يفعّله بضبط <code>DATABASE_URL</code> و<code>STORAGE_MODE=postgres</code>."
)

SAVE_OK = "✅ قطتك ونقاطك محفوظة على السيرفر. تكدر ترجعلها بأي وقت."


# --- help ------------------------------------------------------------------
def help_text(*, is_admin: bool) -> str:
    base = (
        "📖 <b>دليل الأوامر</b>\n\n"
        "🐱 <b>القطة</b>\n"
        "/adopt — تبني قطة جديدة\n"
        "/status — تشوف حالتها وصورتها\n"
        "/rename — تغير اسمها\n\n"
        "💚 <b>العناية</b>\n"
        "/feed — طعام (ينزّل الجوع)\n"
        "/play — لعب (يرفع السعادة)\n"
        "/walk — نزهة (يرفع الحب والنقاط)\n\n"
        "🛍️ <b>الاقتصاد</b>\n"
        "/shop — المتجر\n"
        "/bag — حقيبتك\n"
        "/points — رصيدك وسجل النقاط\n\n"
        "👥 <b>الشراكة والملجأ</b>\n"
        "/invite_partner — تدعو شريك يشاركك القطة\n"
        "/shelter — ملجأ القطط الهاربة\n\n"
        "ℹ️ /start للقائمة الرئيسية"
    )
    if is_admin:
        base += "\n\n🛠️ <b>للمطور</b>: /dev يفتح لوحة الاختبار."
    return base


# --- status ----------------------------------------------------------------
STATE_HEADLINE: dict[Emotion, str] = {
    Emotion.HAPPY: "😻 قطتك مبسوطة ومرتاحة!",
    Emotion.NEUTRAL: "😺 قطتك بخير — بس تحب شوية اهتمام.",
    Emotion.SAD: "😿 قطتك تعبانة وتحتاجك هسه.",
    Emotion.FLED: "🙀 قطتك هربت من البيت…",
}

ALERT_HEADLINE: dict[AlertState, str] = {
    AlertState.HUNGRY: "🍽️ <b>قطتك جوعانة!</b>",
    AlertState.SAD: "😔 <b>قطتك زهقانة!</b>",
    AlertState.LOVE_LOW: "💔 <b>حب قطتك على وشك ينطفي!</b>",
    AlertState.FLED: "🙀 <b>قطتك هربت!</b>",
}

ALERT_BODY: dict[AlertState, str] = {
    AlertState.HUNGRY: "صار وقت طويل من آخر أكلة. اضغط إطعام قبل ما تزعل.",
    AlertState.SAD: "ما لعبت وياها من زمان. جرب /play أو خذها نزهة.",
    AlertState.LOVE_LOW: "إذا نزل الحب للصفر راح تهرب للملجأ. داركها هسه!",
    AlertState.FLED: "تكدر تدور عليها بالملجأ /shelter وتحاول ترجعها.",
}


def cat_card(cat: CatData, user: UserData, *, emotion: Emotion, guest: bool) -> str:
    lines = [
        f"🐱 <b>{esc(cat.name)}</b>  <code>#{cat.id_number}</code>",
        f"{cat.title} · {esc(cat.breed.label_ar)} · 🎂 {cat.age_days} يوم",
        "",
        STATE_HEADLINE[emotion],
        "",
        stat_line("🍖", "الجوع", cat.hunger, invert=True),
        stat_line("🎾", "السعادة", cat.happiness),
        stat_line("💖", "الحب", cat.love_bar),
    ]
    if cat.partner_id:
        lines.append(stat_line("🤝", "الانسجام", cat.partner_affinity))
    lines += ["", f"⭐ نقاطك: <b>{user.points}</b>"]
    if guest:
        lines += ["", GUEST_BANNER]
    return "\n".join(lines)


def fled_card(cat: CatData) -> str:
    return (
        f"🙀 <b>{esc(cat.name)} هربت!</b>\n\n"
        "نزل الحب للصفر وقررت تترك البيت. "
        "هسه موجودة بالملجأ — تقدر تحاول ترجعها من /shelter "
        "أو تبني قطة جديدة بـ /adopt.\n\n"
        "<i>القطة المسترجعة تبدي بحب 40% — الثقة تنبني من جديد.</i>"
    )


def care_success(action: CareAction, cat: CatData, points: int, *, partner: bool = False) -> str:
    flavor = {
        CareAction.FEED: f"🍖 {esc(cat.name)} أكلت وشبعت!",
        CareAction.PLAY: f"🎾 لعبتوا سوا و{esc(cat.name)} انبسطت!",
        CareAction.WALK: f"🚶 طلعتوا نزهة حلوة — {esc(cat.name)} تحبك أكثر!",
    }[action]
    tail = f"\n\n⭐ +{points} نقطة"
    if partner:
        tail += " · 🤝 الانسجام ارتفع"
    return flavor + tail


def cooldown_text(action: CareAction, seconds_left: int, cat_name: str) -> str:
    return (
        f"⏳ <b>هدّي شوية</b>\n\n"
        f"{esc(cat_name)} ما تحتاج {action.label_ar} هسه.\n"
        f"جرب بعد <b>{human_duration_ar(seconds_left)}</b>."
    )


NO_CAT = (
    "🐾 <b>ما عندك قطة بعد!</b>\n\n"
    "اضغط الزر تحت أو اكتب /adopt وخذلك وحدة."
)

ALREADY_HAS_CAT = "🐱 عندك قطة فعلاً. شوف حالتها بـ /status."


def adopted(cat: CatData, *, guest: bool) -> str:
    text = (
        f"🎉 <b>مبروك! تبنيت {esc(cat.name)}</b>\n\n"
        f"🧬 السلالة: {esc(cat.breed.label_ar)}\n"
        f"🆔 الرقم: <code>#{cat.id_number}</code>\n"
        f"🎂 العمر: {cat.age_days} يوم\n\n"
        "دير بالك عليها: طعام، لعب، ونزهة. "
        "إذا أهملتها ينزل حبها وممكن تهرب."
    )
    if guest:
        text += f"\n\n{GUEST_BANNER}"
    return text


# --- shop ------------------------------------------------------------------
def shop_text(items: list[ItemData], points: int) -> str:
    lines = ["🛍️ <b>المتجر</b>", f"⭐ رصيدك: <b>{points}</b> نقطة", ""]
    for item in items:
        lines.append(f"{item.emoji} <b>{esc(item.name)}</b> — {item.price} نقطة")
        if item.description:
            lines.append(f"   <i>{esc(item.description)}</i>")
    lines += ["", "اختر غرض من الأزرار تحت."]
    return "\n".join(lines)


def bag_text(rows: list[tuple[ItemData, int]]) -> str:
    if not rows:
        return "🎒 <b>حقيبتك فارغة</b>\n\nروح للمتجر /shop وشوف شنو يعجبك."
    lines = ["🎒 <b>حقيبتك</b>", ""]
    for item, qty in rows:
        lines.append(f"{item.emoji} {esc(item.name)} ×{qty}")
    lines += ["", "اضغط على غرض حتى تستخدمه."]
    return "\n".join(lines)


def bought(item: ItemData, points_left: int) -> str:
    return (
        f"✅ اشتريت {item.emoji} <b>{esc(item.name)}</b>\n"
        f"⭐ الباقي: <b>{points_left}</b> نقطة"
    )


NOT_ENOUGH_POINTS = "😅 نقاطك ما تكفي لهذا الغرض. اربح أكثر من /walk و/play."


def item_used(item: ItemData, cat: CatData) -> str:
    return f"✨ استخدمت {item.emoji} <b>{esc(item.name)}</b> على {esc(cat.name)}."


# --- partner / shelter -----------------------------------------------------
def partner_invite(link: str, cat: CatData) -> str:
    return (
        f"🤝 <b>ادعُ شريك لـ {esc(cat.name)}</b>\n\n"
        "الشريك يقدر يطعّم ويلعب وياها، ويرتفع بينكم شريط الانسجام.\n\n"
        f"🔗 <code>{esc(link)}</code>\n\n"
        f"<i>أول شريك ينضم يعطيك +{50} نقطة.</i>"
    )


PARTNER_JOINED = "🤝 <b>انضميت كشريك!</b> تكدر تعتني بالقطة مثل صاحبها."
PARTNER_INVALID = "🔗 رابط الدعوة مو صالح أو انتهى."
PARTNER_ALREADY = "🤝 هذي القطة عدها شريك فعلاً."
PARTNER_SELF = "🙂 ما تكدر تكون شريك نفسك."


def shelter_text(cats: list[CatData]) -> str:
    if not cats:
        return "🏠 <b>الملجأ فاضي</b>\n\nما اكو قطط هاربة هسه — وهذا خبر زين!"
    lines = ["🏠 <b>ملجأ القطط الهاربة</b>", ""]
    for cat in cats:
        lines.append(
            f"🐱 <b>{esc(cat.name)}</b> <code>#{cat.id_number}</code> — {esc(cat.breed.label_ar)}"
        )
    lines += ["", "<i>القطة المسترجعة تبدي بحب 40%.</i>"]
    return "\n".join(lines)


def readopted(cat: CatData) -> str:
    return (
        f"🏡 <b>رجعت {esc(cat.name)} للبيت!</b>\n\n"
        f"💖 الحب بدا من {cat.love_bar}% — اهتم بيها زين هالمرة."
    )


# --- generic ---------------------------------------------------------------
ERROR_GENERIC = (
    "⚠️ صار خطأ غير متوقع. جرب مرة ثانية بعد شوية.\n"
    "<i>إذا تكرر، بلّغ المطور.</i>"
)
THROTTLED = "🐢 هوّن عليك — أوامر كثيرة بوقت قصير."
NOT_ADMIN = "🚫 هذا الأمر للمطورين بس."
CANCELLED = "❌ تم الإلغاء."
ASK_NAME = "✏️ اكتب اسم القطة الجديد (٢ إلى ٢٠ حرف):"
