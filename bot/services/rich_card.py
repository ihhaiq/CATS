"""Rich Telegram card shared by private chat and Guest Mode."""
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    InputRichMessage,
    InputRichMessageMedia,
)

from bot.config import settings
from bot.services.local_store import get_media_file_id_sync, get_media_type_sync
from bot.services.local_store import is_sleeping, sleep_need_percent


def _media_id(kind: str, breed: str) -> str:
    return get_media_file_id_sync(kind, breed) or get_media_file_id_sync(kind) or getattr(settings, f"{kind}_media_file_id", "") or ""


def _media_block(kind: str, breed: str) -> tuple[str, InputRichMessageMedia] | None:
    file_id = _media_id(kind, breed)
    if not file_id:
        return None
    if get_media_type_sync(kind, breed) == "video" or get_media_type_sync(kind) == "video" or kind.endswith("_gif") or kind.endswith("_animation"):
        media = InputMediaVideo(media=file_id, duration=5)
        return "video", InputRichMessageMedia(id="cat_video", media=media)
    media = InputMediaPhoto(media=file_id)
    return "photo", InputRichMessageMedia(id="cat_photo", media=media)


def build_rich_card(cat: dict, points: int, media_kind: str = "status") -> InputRichMessage:
    media = _media_block(media_kind, cat["breed"])
    media_markup = ""
    media_list = []
    if media:
        block_type, media_item = media
        media_list.append(media_item)
        tag = "img" if block_type == "photo" else "video"
        protocol = "photo" if block_type == "photo" else "video"
        media_markup = f"<{tag} src=\"tg://{protocol}?id={media_item.id}\"/>"
    else:
        media_markup = "<p>الصورة الواقعية ستظهر بعد إضافة ملف القطة.</p>"

    sleeping = is_sleeping(cat)
    sleep_note = "<p>😴 القطة نائمة. كل الأفعال متوقفة حتى تستيقظ.</p>" if sleeping else ""
    notice = cat.get("action_notice", "")
    notice_html = f"<p><b>{notice}</b></p>" if notice else ""
    wake_action = "wake" if sleeping else "sleep"
    wake_label = "إيقاظ" if sleeping else "نوم"
    callback_prefix = f"cat:{cat['owner_id']}"
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
<tg-button type="callback_data" style="success" data="{callback_prefix}:feed">إطعام</tg-button>
<tg-button type="callback_data" style="primary" data="{callback_prefix}:play">لعب</tg-button>
<tg-button type="callback_data" data="{callback_prefix}:walk">نزهة</tg-button>
</tg-button-row>
<tg-button-row align="center">
<tg-button type="callback_data" data="{callback_prefix}:talk">تحدث</tg-button>
<tg-button type="callback_data" data="{callback_prefix}:{wake_action}">{wake_label}</tg-button>
</tg-button-row>
{sleep_note}
{notice_html}
""".strip()
    return InputRichMessage(html=html, is_rtl=True, media=media_list)
