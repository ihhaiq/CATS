"""Rich shopping card shared by private and Guest Mode."""
from aiogram.types import InputRichMessage


def build_shop_card(items: list[dict], purchases: list[str], points: int) -> InputRichMessage:
    rows = "".join(f"<tr><td>{purchase}</td></tr>" for purchase in purchases)
    if not rows:
        rows = "<tr><td>السلة فارغة</td></tr>"
    buttons = "".join(
        f'<tg-button type="callback_data" style="primary" data="shop:buy:{item["item_id"]}">{item["name"]} · 🐾 {item["price"]}</tg-button>'
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
<p>🐾 العملة القططية: {points}</p>
""".strip()
    return InputRichMessage(html=html, is_rtl=True)
