"""Rich shopping card shared by private and Guest Mode."""
from aiogram.types import InputRichMessage


def build_shop_card(items: list[dict], purchases: list[str], points: int) -> InputRichMessage:
    rows = "".join(
        f"<tr><td>{item['item_id']}. {item['name']} - 🐾 {item['price']}</td></tr>"
        for item in items
    )
    buttons = "".join(
        f'<tg-button type="callback_data" data="shop:buy:{item["item_id"]}">شراء {item["item_id"]}</tg-button>'
        for item in items
    )
    cart = "، ".join(purchases) if purchases else "لا توجد مشتريات بعد"
    html = f"""
<h2>🛍️ المتجر</h2>
<table bordered striped compact>
<tr><th>المشتريات</th></tr>
{rows}
</table>
<p><b>السلة الحالية:</b> {cart}</p>
<p>🐾 العملة القططية: {points}</p>
<tg-button-row align="center">{buttons}</tg-button-row>
""".strip()
    return InputRichMessage(html=html, is_rtl=True)
