"""Rich Telegram card shared by private chat and Guest Mode."""
import html
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    InputRichMessage,
    InputRichMessageMedia,
)

from bot.services.local_store import (
    collect_needs,
    fullness_percent,
    is_action_cooldown_bypassed,
    is_sleeping,
    recommended_action,
    sleep_duration_text,
    sleep_need_percent,
    sleep_remaining_minutes,
)
from bot.services.media_runtime import resolve_cat_media


def build_fled_card(cat: dict) -> InputRichMessage:
    name = html.escape(str(cat.get("name", "قطتك")))
    return InputRichMessage(
        html=(
            f"<h2>💨 هربت {name}</h2>"
            "<p>وصل الحب إلى 0 بسبب الإهمال، لذلك ما عادت أفعال العناية متاحة.</p>"
        ),
        is_rtl=True,
    )


async def build_rich_card(
    bot,
    cat: dict,
    points: int,
    media_kind: str = "status",
    *,
    upload_chat_id: int | str | None = None,
) -> InputRichMessage:
    resolved = await resolve_cat_media(
        bot,
        cat,
        media_kind,
        upload_chat_id=upload_chat_id,
    )

    media_markup = ""
    media_list = []
    if resolved:
        if resolved.media_type == "video":
            media = InputMediaVideo(media=resolved.file_id, duration=5)
            media_item = InputRichMessageMedia(id="cat_video", media=media)
            media_list.append(media_item)
            media_markup = '<video src="tg://video?id=cat_video"/>'
        else:
            media = InputMediaPhoto(media=resolved.file_id)
            media_item = InputRichMessageMedia(id="cat_photo", media=media)
            media_list.append(media_item)
            media_markup = '<img src="tg://photo?id=cat_photo"/>'
    else:
        media_markup = "<p>الصورة الواقعية ستظهر بعد إضافة ملف القطة.</p>"

    sleeping = is_sleeping(cat)
    if sleeping:
        sleep_kind = cat.get("sleep_kind")
        sleep_label = {
            "main": "نوم رئيسي",
            "nap": "قيلولة",
        }.get(sleep_kind, "نوم")
        remaining = sleep_duration_text(sleep_remaining_minutes(cat))
        sleep_note = (
            f"<p>😴 القطة في {sleep_label}. "
            f"⏳ باقي تقريباً {remaining}، وبعدها تصحى من نفسها.</p>"
        )
    else:
        sleep_note = ""
    notice = cat.get("action_notice", "")
    notice_html = f"<p><b>{html.escape(str(notice))}</b></p>" if notice else ""
    hunger = int(cat.get("hunger", 20))
    happiness = int(cat.get("happiness", 100))
    love = int(cat.get("love_bar", 100))
    trust = int(cat.get("trust", 60))
    boredom = int(cat.get("boredom", 10))
    fullness = fullness_percent(cat)
    sleep_need = sleep_need_percent(cat)

    def stat_cell(value: str, highlight: bool) -> str:
        return f"<mark><b>{value}</b></mark>" if highlight else value

    action_highlights = {
        "feed": {"fullness", "happiness", "love", "trust"},
        "play": {
            "fullness",
            "happiness",
            "love",
            "trust",
            "boredom",
            "rest",
        },
        "walk": {
            "fullness",
            "happiness",
            "love",
            "trust",
            "boredom",
            "rest",
        },
        "talk": {"happiness", "love", "trust", "boredom"},
        "sleep": {"rest"},
        "relax": {"happiness", "love", "boredom", "rest"},
    }.get(media_kind, set())

    fullness_cell = stat_cell(
        f"{fullness}%",
        "fullness" in action_highlights or hunger >= 70,
    )
    happiness_cell = stat_cell(
        f"{happiness}%",
        "happiness" in action_highlights or happiness <= 40,
    )
    love_cell = stat_cell(
        f"{love}%",
        "love" in action_highlights or love <= 30,
    )
    trust_cell = stat_cell(
        f"{trust}%",
        "trust" in action_highlights or trust <= 35,
    )
    boredom_cell = stat_cell(
        f"{boredom}%",
        "boredom" in action_highlights or boredom >= 35,
    )
    sleep_cell = stat_cell(
        f"{sleep_need}%",
        "rest" in action_highlights or (not sleeping and sleep_need <= 50),
    )

    needs = collect_needs(cat)
    next_action = recommended_action(cat)

    note_labels = {
        "starving": "جائعة جدًا",
        "hungry": "جائعة",
        "peckish": "جائعة شوي",
        "exhausted": "منهكة جدًا وتحتاج نوم",
        "tired": "متعبة وتحتاج ترتاح",
        "sleepy": "بدت تنعس",
        "very_bored": "ملل قاتل",
        "bored": "تحس بملل",
        "restless": "بدت تمل",
        "very_sad": "حزينة جدًا",
        "sad": "مزاجها مو زين",
        "love_critical": "حاسّة بإهمال قوي",
        "love_low": "محتاجة حنان واهتمام",
        "trust_critical": "ثقتها بيك ضعيفة جدًا",
        "trust_low": "ثقتها بيك نازلة",
        "walk_due": "محتاجة نزهة وتغيير جو",
        "attention_due": "مشتاقتلك وتريد تفاعل",
    }
    note_priority = [
        "starving",
        "exhausted",
        "very_bored",
        "very_sad",
        "love_critical",
        "trust_critical",
        "hungry",
        "tired",
        "bored",
        "sad",
        "love_low",
        "trust_low",
        "walk_due",
        "attention_due",
        "sleepy",
        "restless",
        "peckish",
    ]
    if sleeping:
        sleep_kind = cat.get("sleep_kind")
        note_text = (
            "نايمة نوم رئيسي"
            if sleep_kind == "main"
            else "نايمة قيلولة"
        )
    else:
        note_items = [
            note_labels[item]
            for item in note_priority
            if item in needs and item in note_labels
        ][:2]
        note_text = "، و".join(note_items) if note_items else "مرتاحـة وما تحتاج شي هسه"
    note_cell = html.escape(note_text)
    action_labels = {
        "feed": "🍖 إطعام",
        "play": "🎾 لعب",
        "walk": "🌿 نزهة",
        "talk": "💬 تحدث",
        "sleep": "😴 نوم",
        "relax": "🛋 استلقاء",
    }
    recommendation_html = (
        f"<p><b>🎯 المطلوب هسه: {action_labels[next_action]}</b></p>"
        if next_action
        else ""
    )
    feed_label = (
        "⚡ إطعام"
        if is_action_cooldown_bypassed(cat, "feed")
        else "إطعام"
    )
    play_label = (
        "⚡ لعب"
        if is_action_cooldown_bypassed(cat, "play")
        else "لعب"
    )
    walk_label = (
        "⚡ نزهة"
        if is_action_cooldown_bypassed(cat, "walk")
        else "نزهة"
    )
    talk_label = (
        "⚡ تحدث"
        if is_action_cooldown_bypassed(cat, "talk")
        else "تحدث"
    )
    relax_label = (
        "⚡ استلقاء"
        if is_action_cooldown_bypassed(cat, "relax")
        else "🛋 استلقاء"
    )
    sleep_button_label = "⚡ نوم" if next_action == "sleep" else "نوم"
    cat_id = cat.get("cat_id")

    def action_data(action: str) -> str:
        return f"cat:{cat_id}:{action}" if cat_id else f"cat:{action}"
    if sleeping:
        action_buttons_html = f"""
<tg-button-row align="center">
<tg-button type="callback_data" style="primary" data="{action_data('wake')}">إيقاظ</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data('status')}">🔄 تحديث</tg-button>
</tg-button-row>
""".strip()
    else:
        action_buttons_html = f"""
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data('feed')}">{feed_label}</tg-button>
<tg-button type="callback_data" style="primary" data="{action_data('play')}">{play_label}</tg-button>
<tg-button type="callback_data" data="{action_data('walk')}">{walk_label}</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" data="{action_data('talk')}">{talk_label}</tg-button>
<tg-button type="callback_data" data="{action_data('relax')}">{relax_label}</tg-button>
<tg-button type="callback_data" data="{action_data('sleep')}">{sleep_button_label}</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data('status')}">🔄 تحديث</tg-button>
</tg-button-row>
""".strip()
    hint_map = {
        "starving": "🚨🍖 جوعها شديد جداً.",
        "hungry": "🍗 جائعة وتحتاج أكل.",
        "exhausted": "🪫 منهكة وتحتاج نوم طويل.",
        "tired": "😴 تعبانة وتحتاج ترتاح.",
        "very_bored": "🙀 الملل عندها صار شديد.",
        "bored": "🌀 حست بالملل وتريد لعب أو حديث.",
        "restless": "😼 بدت تمل وتدور شي تسويه.",
        "very_sad": "💔😿 حزينة جداً.",
        "sad": "😿 مزاجها مو زين.",
        "trust_critical": "🧊 ثقتها بيك ضعفت هواية.",
        "trust_low": "🤝 ثقتها تحتاج رعاية ثابتة.",
        "love_critical": "💔 رابطتكم بحالة حرجة.",
        "love_low": "🥺 حست بالإهمال.",
        "walk_due": "🌿 محتاجة نزهة وتغيير جو.",
        "attention_due": "💭 مشتاقتلك وتريد تفاعل وياك.",
        "sleepy": "🥱 بدت تنعس.",
        "peckish": "🥣 بدت تجوع شوي.",
    }
    need_priority_by_action = {
        "feed": ["starving", "hungry", "peckish"],
        "sleep": ["exhausted", "tired", "sleepy"],
        "talk": [
            "love_critical",
            "trust_critical",
            "very_sad",
            "very_bored",
            "love_low",
            "trust_low",
            "sad",
            "bored",
            "attention_due",
        ],
        "walk": ["walk_due"],
        "play": ["very_bored", "bored", "restless"],
        "relax": ["sleepy", "restless"],
    }
    fallback_priority = [
        "starving",
        "hungry",
        "exhausted",
        "tired",
        "love_critical",
        "trust_critical",
        "very_sad",
        "very_bored",
        "love_low",
        "trust_low",
        "sad",
        "bored",
        "walk_due",
        "attention_due",
        "sleepy",
        "restless",
        "peckish",
    ]
    preferred = need_priority_by_action.get(next_action, [])
    primary_need = next(
        (item for item in preferred if item in needs),
        None,
    )
    if primary_need is None:
        primary_need = next(
            (item for item in fallback_priority if item in needs),
            None,
        )
    state_hint = (
        hint_map.get(primary_need, "")
        if primary_need
        else "😺 حالتها مستقرة هسه."
    )
    html_markup = f"""
<h2>{html.escape(str(cat['name']))}</h2>
<p>السلالة: {html.escape(str(cat['breed']))} | #{html.escape(str(cat['id_number']))}</p>
<hr/>
{media_markup}
<hr/>
<table bordered striped compact>
<tr><th>الحالة</th><th>النسبة</th></tr>
<tr><td>الشبع</td><td>{fullness_cell}</td></tr>
<tr><td>السعادة</td><td>{happiness_cell}</td></tr>
<tr><td>الحب</td><td>{love_cell}</td></tr>
<tr><td>الثقة</td><td>{trust_cell}</td></tr>
<tr><td>الملل</td><td>{boredom_cell}</td></tr>
<tr><td>الراحة</td><td>{sleep_cell}</td></tr>
<tr><td><b>ملاحظة</b></td><td>{note_cell}</td></tr>
</table>
<p><i>ℹ️ الشبع: 100 = شبعانة جدًا، 0 = جائعة جدًا. الملل: 0 = مرتاحة وغير مَلّانة، 100 = ملل شديد.</i></p>
<p><b>{state_hint}</b></p>
{recommendation_html}
<p>🐾 العملة القططية: {points}</p>
{action_buttons_html}
{sleep_note}
{notice_html}
""".strip()
    return InputRichMessage(html=html_markup, is_rtl=True, media=media_list)
