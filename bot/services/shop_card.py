"""Rich shopping card shared by private and Guest Mode."""
from html import escape

from aiogram.types import InputRichMessage


def build_shop_card(
    items: list[dict],
    purchases: list[str],
    points: int,
    owner_id: int | None = None,
) -> InputRichMessage:
    rows = "".join(
        f"<tr><td>{escape(str(purchase))}</td></tr>"
        for purchase in purchases
    )
    if not rows:
        rows = "<tr><td>السلة فارغة</td></tr>"

    callback_prefix = f"shop:buy:{owner_id}" if owner_id is not None else "shop:buy"
    buttons = "".join(
        (
            f'<tg-button type="callback_data" style="primary" '
            f'data="{callback_prefix}:{int(item["item_id"])}">'
            f'{escape(str(item["name"]))} · 🐾 {int(item["price"])}'
            f"</tg-button>"
        )
        for item in items
    )
    html = f"""
<h2>🛍️ المتجر</h2>
<p>اضغط على المنتج لشرائه:</p>
<tg-button-row align="center">{buttons}</tg-button-row>
<table bordered striped compact>
<tr><th>المشتريات</th></tr>
{rows}
</table>
<p>🐾 العملة القططية: {int(points)}</p>
""".strip()
    return InputRichMessage(html=html, is_rtl=True)
