"""Rich Telegram card shared by private chat and Guest Mode."""
import html
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    InputRichMessage,
    InputRichMessageMedia,
)

from bot.services.economy import ACTIVE_BREEDS
from bot.services.cat_events import (
    active_boredom_escape,
    active_boredom_host_busy,
    active_cat_request,
    active_hiding,
    boredom_escape_remaining_minutes,
    boredom_host_busy_remaining_minutes,
    request_label,
    request_message,
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
    TREAT_FULLNESS_THRESHOLD,
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
    cat_id = cat.get("cat_id")

    def action_data(action: str) -> str:
        return f"cat:{cat_id}:{action}" if cat_id else f"cat:{action}"

    if active_boredom_host_busy(cat):
        name = html.escape(str(cat.get("name", "قطتك")))
        breed = html.escape(str(cat.get("breed", "")))
        number = html.escape(str(cat.get("id_number", "")))
        peer_name = html.escape(
            str(cat.get("boredom_host_peer_cat_name", "قطة ثانية"))
        )
        remaining = sleep_duration_text(
            boredom_host_busy_remaining_minutes(cat)
        )
        return InputRichMessage(
            html=f"""
<h1>{name}</h1>
<p>🎾 القطة مشغولة تلعب ويا قطة <b>{peer_name}</b>.</p>
<p>🐾 ما تگدر تتفاعل وياها لحد ما تخلص اللعب.</p>
<p>⏳ باقي تقريباً <b>{html.escape(remaining)}</b>.</p>
<tg-button-row align="center">
<tg-button type="callback_data" style="secondary" data="{action_data('status')}">تحديث</tg-button>
</tg-button-row>
<footer>🐈 السلالة: {breed} | #{number}</footer>
""".strip(),
            is_rtl=True,
        )

    if active_boredom_escape(cat):
        name = html.escape(str(cat.get("name", "قطتك")))
        breed = html.escape(str(cat.get("breed", "")))
        number = html.escape(str(cat.get("id_number", "")))
        remaining = sleep_duration_text(
            boredom_escape_remaining_minutes(cat)
        )
        return InputRichMessage(
            html=f"""
<h1>{name}</h1>
<p>🌀 هربت من الملل وراحت تدور قطة تلعب وياها.</p>
<p>🐾 ما تگدر تتفاعل وياها وهي غايبة.</p>
<p>⏳ باقي تقريباً <b>{html.escape(remaining)}</b> على رجعتها.</p>
<tg-button-row align="center">
<tg-button type="callback_data" style="secondary" data="{action_data('status')}">تحديث</tg-button>
</tg-button-row>
<footer>🐈 السلالة: {breed} | #{number}</footer>
""".strip(),
            is_rtl=True,
        )

    if active_hiding(cat):
        name = html.escape(str(cat.get("name", "قطتك")))
        breed = html.escape(str(cat.get("breed", "")))
        number = html.escape(str(cat.get("id_number", "")))
        notice = cat.get("action_notice", "")
        notice_html = (
            f"<p><b>{html.escape(str(notice))}</b></p>"
            if notice
            else ""
        )
        call_label = html.escape(f"📣 نادي {cat.get('name', 'قطتك')}")
        return InputRichMessage(
            html=f"""
<h1>{name}</h1>
<p>🙀 اختفت بالبيت. دور عليها أو ناديها باسمها.</p>
{notice_html}
<tg-button-row align="center">
<tg-button type="callback_data" data="{action_data('hide_bed')}">🛏 تحت السرير</tg-button>
<tg-button type="callback_data" data="{action_data('hide_box')}">📦 داخل الكارتونة</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" data="{action_data('hide_curtain')}">🪟 ورا الستارة</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" style="primary" data="{action_data('hide_call')}">{call_label}</tg-button>
</tg-button-row>
<footer>🐈 السلالة: {breed} | #{number}</footer>
""".strip(),
            is_rtl=True,
        )

    asset_kind = (
        "play"
        if media_kind == "toy"
        else "feed"
        if media_kind == "treat"
        else media_kind
    )
    resolved = await resolve_cat_media(
        bot,
        cat,
        asset_kind,
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
    elif cat.get("breed") != "black":
        media_markup = "<p>الصورة الواقعية ستظهر بعد إضافة ملف القطة.</p>"

    sleeping = is_sleeping(cat)
    if sleeping:
        sleep_kind = cat.get("sleep_kind")
        sleep_label = {
            "main": "نوم رئيسي",
            "nap": "قيلولة",
            "away": "نومة طويلة لأنك مو يمها",
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
    breed_notice_html = (
        "<h3>⚠️ سلالة قطتك معطلة مؤقتًا من التبنّي الجديد، "
        "لكن قطتك تستمر وتشتغل بشكل طبيعي.</h3>"
        "<tg-button-row align=\"center\">"
        "<tg-button type=\"callback_data\" style=\"secondary\" "
        "data=\"cat:breed:choose\">🐾 تغيير</tg-button>"
        "</tg-button-row>"
        if cat.get("breed") not in ACTIVE_BREEDS
        else ""
    )
    hunger = int(cat.get("hunger", 20))
    happiness = int(cat.get("happiness", 100))
    love = int(cat.get("love_bar", 100))
    trust = int(cat.get("trust", 60))
    boredom = int(cat.get("boredom", 10))
    fullness = fullness_percent(cat)
    sleep_need = sleep_need_percent(cat)

    def stat_cell(value: str, highlight: bool) -> str:
        return f"<mark><b>{value}</b></mark>" if highlight else value

    def stat_emoji(kind: str, value: int) -> str:
        value = max(0, min(100, int(value)))
        if kind == "fullness":
            if value >= 80:
                return "😋"
            if value >= 60:
                return "🍗"
            if value >= 40:
                return "🍽️"
            if value >= 20:
                return "🥣"
            return "🚨"
        if kind == "happiness":
            if value >= 80:
                return "😸"
            if value >= 60:
                return "🙂"
            if value >= 40:
                return "😐"
            if value >= 20:
                return "😿"
            return "💔"
        if kind == "love":
            if value >= 80:
                return "😻"
            if value >= 60:
                return "💗"
            if value >= 40:
                return "💕"
            if value >= 20:
                return "🥺"
            return "💔"
        if kind == "trust":
            if value >= 80:
                return "🤝"
            if value >= 60:
                return "🐾"
            if value >= 40:
                return "🤔"
            if value >= 20:
                return "🧊"
            return "🚫"
        if kind == "boredom":
            if value <= 15:
                return "😌"
            if value <= 35:
                return "😺"
            if value <= 60:
                return "😼"
            if value <= 80:
                return "🙀"
            return "🌀"
        if sleeping:
            return "😴"
        if value >= 80:
            return "⚡"
        if value >= 60:
            return "🔋"
        if value >= 40:
            return "🥱"
        if value >= 20:
            return "😴"
        return "🪫"

    action_highlights = {
        "feed": {"fullness", "happiness", "love", "trust", "boredom"},
        "treat": {"fullness", "happiness", "love", "boredom"},
        "play": {
            "fullness",
            "happiness",
            "love",
            "trust",
            "boredom",
            "rest",
        },
        "toy": {"happiness", "love", "boredom"},
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

    def stat_note(kind: str, value: int) -> str:
        value = max(0, min(100, int(value)))

        if kind == "fullness":
            if value == 100:
                return "شبعانة حيل"
            if value >= 80:
                return "شبعانة"
            if value >= 60:
                return "شبعها زين"
            if value >= 40:
                return "جائعة شوي"
            if value >= 20:
                return "جائعة"
            if value > 0:
                return "جوعانة حيل"
            return "ميتة جوع"

        if kind == "happiness":
            if value == 100:
                return "فرحانة حيل"
            if value >= 80:
                return "سعيدة ورايقة"
            if value >= 60:
                return "مزاجها زين"
            if value >= 40:
                return "مزاجها عادي"
            if value >= 20:
                return "زعلانة شوي"
            if value > 0:
                return "حزينة حيل"
            return "حزينة جدًا"

        if kind == "love":
            if value == 100:
                return "تحبك حيل"
            if value >= 80:
                return "مرتبطة بيك هواية"
            if value >= 60:
                return "تحبك"
            if value >= 40:
                return "تحتاج اهتمام أكثر"
            if value >= 20:
                return "حاسّة بإهمال"
            if value > 0:
                return "حبها إلك شبه منتهي"
            return "ما بقى عندها حب"

        if kind == "trust":
            if value == 100:
                return "واثقة بيك حيل"
            if value >= 80:
                return "تثق بيك هواية"
            if value >= 60:
                return "ثقتها بيك زينة"
            if value >= 40:
                return "ثقتها متوسطة"
            if value >= 20:
                return "ثقتها ضعيفة"
            if value > 0:
                return "تقريبًا ما تثق بيك"
            return "ما تثق بيك أبد"

        if kind == "boredom":
            if value == 0:
                return "مو ملانة أبد"
            if value <= 15:
                return "مرتاحة ومستانسة"
            if value <= 35:
                return "بدت تمل شوي"
            if value <= 60:
                return "تحس بملل"
            if value <= 80:
                return "ملانة حيل"
            return "ملل قاتل"

        if sleeping:
            return "نايمة وتسترجع طاقتها"
        if value == 100:
            return "مرتاحة حيل"
        if value >= 80:
            return "عندها طاقة"
        if value >= 60:
            return "تحتاج استراحة بسيطة"
        if value >= 40:
            return "متعبة شوي"
        if value >= 20:
            return "متعبة"
        if value > 0:
            return "منهكة حيل"
        return "منهكة وما بيها حيل"

    fullness_note = html.escape(stat_note("fullness", fullness))
    happiness_note = html.escape(stat_note("happiness", happiness))
    love_note = html.escape(stat_note("love", love))
    trust_note = html.escape(stat_note("trust", trust))
    boredom_note = html.escape(stat_note("boredom", boredom))
    sleep_note_cell = html.escape(stat_note("rest", sleep_need))

    request_action = active_cat_request(cat)
    if request_action:
        request_html = f"""
<h3>{html.escape(request_message(request_action))}</h3>
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data(request_action)}">{html.escape(request_label(request_action))}</tg-button>
<tg-button type="callback_data" style="secondary" data="{action_data('request_ignore')}">🙈 طنش</tg-button>
</tg-button-row>
""".strip()
    else:
        request_html = ""

    action_labels = {
        "feed": "🍖 إطعام",
        "treat": "تحلية 🍬",
        "play": "🎾 لعب",
        "toy": "🧸 لعبة",
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
    food_action = (
        "treat"
        if fullness >= TREAT_FULLNESS_THRESHOLD
        else "feed"
    )
    feed_label = (
        "⚡🍖 إطعام"
        if is_action_cooldown_bypassed(cat, "feed")
        else "🍖 إطعام"
    )
    food_label = "تحلية 🍬" if food_action == "treat" else feed_label
    play_label = (
        "⚡🎾 لعب"
        if is_action_cooldown_bypassed(cat, "play")
        else "🎾 لعب"
    )
    toy_label = (
        "⚡🧸 اعطها لعبة"
        if is_action_cooldown_bypassed(cat, "toy")
        else "🧸 اعطها لعبة"
    )
    walk_label = (
        "⚡🌿 نزهة"
        if is_action_cooldown_bypassed(cat, "walk")
        else "🌿 نزهة"
    )
    talk_label = (
        "⚡💬 تحدث"
        if is_action_cooldown_bypassed(cat, "talk")
        else "💬 تحدث"
    )
    relax_label = (
        "⚡🛋 استلقاء"
        if is_action_cooldown_bypassed(cat, "relax")
        else "🛋 استلقاء"
    )
    sleep_button_label = "⚡😴 نوم" if next_action == "sleep" else "😴 نوم"
    if sleeping:
        action_buttons_html = f"""
<tg-button-row align="center">
<tg-button type="callback_data" style="primary" data="{action_data('wake')}">☀️ إيقاظ</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data('status')}">🔄 تحديث</tg-button>
</tg-button-row>
""".strip()
    else:
        action_buttons_html = f"""
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="{action_data(food_action)}">{food_label}</tg-button>
<tg-button type="callback_data" style="primary" data="{action_data('play')}">{play_label}</tg-button>
<tg-button type="callback_data" data="{action_data('walk')}">{walk_label}</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" data="{action_data('talk')}">{talk_label}</tg-button>
<tg-button type="callback_data" style="primary" data="{action_data('toy')}">{toy_label}</tg-button>
<tg-button type="callback_data" data="{action_data('relax')}">{relax_label}</tg-button>
</tg-button-row>
<tg-button-row align="center">
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
        "bored": "🌀 حست بالملل وتريد لعب، لعبة أو حديث.",
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
        "toy": ["very_bored", "bored", "restless"],
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
<h1>{html.escape(str(cat['name']))}</h1>
{breed_notice_html}
<hr/>
{media_markup}
{request_html}
<hr/>
<table bordered striped compact>
<tr><th>الحالة</th><th>النسبة</th><th>ملاحظة</th></tr>
<tr><td>{stat_emoji("fullness", fullness)} الشبع</td><td>{fullness_cell}</td><td>{fullness_note}</td></tr>
<tr><td>{stat_emoji("happiness", happiness)} السعادة</td><td>{happiness_cell}</td><td>{happiness_note}</td></tr>
<tr><td>{stat_emoji("love", love)} الحب</td><td>{love_cell}</td><td>{love_note}</td></tr>
<tr><td>{stat_emoji("trust", trust)} الثقة</td><td>{trust_cell}</td><td>{trust_note}</td></tr>
<tr><td>{stat_emoji("boredom", boredom)} الملل</td><td>{boredom_cell}</td><td>{boredom_note}</td></tr>
<tr><td>{stat_emoji("rest", sleep_need)} الراحة</td><td>{sleep_cell}</td><td>{sleep_note_cell}</td></tr>
</table>
<details>
<summary>شنو تعني النسب؟</summary>
<ul>
<li><b>الشبع:</b> 0 يعني جوعانة حيل، و100 يعني شبعانة حيل.</li>
<li><b>السعادة:</b> 0 يعني حزينة جدًا، و100 يعني فرحانة حيل.</li>
<li><b>الحب:</b> 0 يعني ما بقى عندها حب إلك، و100 يعني تحبك حيل.</li>
<li><b>الثقة:</b> 0 يعني ما تثق بيك أبد، و100 يعني واثقة بيك حيل.</li>
<li><b>الملل:</b> 0 يعني مو ملانة أبد، و100 يعني عندها ملل قاتل.</li>
<li><b>الراحة:</b> 0 يعني منهكة وما بيها حيل، و100 يعني مرتاحة حيل.</li>
</ul>
</details>
<p><b>{state_hint}</b></p>
{recommendation_html}
<p>🐾 العملة القططية: {points}</p>
{action_buttons_html}
{sleep_note}
{notice_html}
<footer>🐈 السلالة: {html.escape(str(cat['breed']))} | #{html.escape(str(cat['id_number']))}</footer>
""".strip()
    return InputRichMessage(html=html_markup, is_rtl=True, media=media_list)
