"""Rich Telegram card shared by private chat and Guest Mode."""
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    InputRichMessage,
    InputRichMessageMedia,
)

from bot.services.local_store import is_sleeping, sleep_need_percent
from bot.services.media_runtime import resolve_cat_media


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
    sleep_note = "<p>😴 القطة نائمة. كل الأفعال متوقفة حتى تستيقظ.</p>" if sleeping else ""
    notice = cat.get("action_notice", "")
    notice_html = f"<p><b>{notice}</b></p>" if notice else ""
    wake_action = "wake" if sleeping else "sleep"
    wake_label = "إيقاظ" if sleeping else "نوم"
    fullness = 100 - cat["hunger"]
    sleep_need = sleep_need_percent(cat)
    html = f"""
<h2>{cat['name']}</h2>
<p>السلالة: {cat['breed']} | #{cat['id_number']}</p>
<hr/>
{media_markup}
<hr/>
<table bordered striped compact>
<tr><th>الحالة</th><th>النسبة</th></tr>
<tr><td>الشبع</td><td>{fullness}%</td></tr>
<tr><td>السعادة</td><td>{cat['happiness']}%</td></tr>
<tr><td>الحب</td><td>{cat['love_bar']}%</td></tr>
<tr><td>الراحة والنوم</td><td>{sleep_need}%</td></tr>
</table>
<p>🐾 العملة القططية: {points}</p>
<tg-button-row align="center">
<tg-button type="callback_data" style="success" data="cat:feed">إطعام</tg-button>
<tg-button type="callback_data" style="primary" data="cat:play">لعب</tg-button>
<tg-button type="callback_data" data="cat:walk">نزهة</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" data="cat:talk">تحدث</tg-button>
<tg-button type="callback_data" data="cat:{wake_action}">{wake_label}</tg-button>
</tg-button-row>
{sleep_note}
{notice_html}
""".strip()
    return InputRichMessage(html=html, is_rtl=True, media=media_list)
