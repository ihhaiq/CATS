"""PostgreSQL-backed shop service."""
from bot.services import local_store

DEFAULT_ITEMS = [
    {
        "item_id": 1,
        "name": "وجبة فاخرة",
        "price": 25,
        "effect_type": "hunger",
        "effect_value": 35,
    },
    {
        "item_id": 2,
        "name": "لعبة ريشة",
        "price": 30,
        "effect_type": "happiness",
        "effect_value": 25,
    },
    {
        "item_id": 3,
        "name": "طوق أزرق",
        "price": 60,
        "effect_type": "cosmetic_collar",
        "effect_value": 1,
    },
]


async def list_items() -> list[dict]:
    async with local_store.state_transaction() as data:
        if not data["items"]:
            data["items"] = [dict(item) for item in DEFAULT_ITEMS]
        return [dict(item) for item in data["items"]]


async def open_shop(user_id: int) -> list[dict]:
    await local_store.clear_purchases(user_id)
    return await list_items()


async def buy_item(
    user_id: int,
    item_id: int,
) -> tuple[bool, str, int]:
    async with local_store.state_transaction() as data:
        if not data["items"]:
            data["items"] = [dict(item) for item in DEFAULT_ITEMS]

        item = next(
            (
                row
                for row in data["items"]
                if int(row["item_id"]) == int(item_id)
            ),
            None,
        )
        if item is None:
            return False, "الغرض غير موجود.", 0

        user = data["users"].setdefault(
            str(user_id),
            local_store._new_user(user_id),
        )
        user.setdefault("purchases", [])
        balance = int(user.get("points", 100))
        price = int(item["price"])
        if balance < price:
            return False, "رصيدك من العملة القططية لا يكفي.", balance

        user["points"] = balance - price
        user["purchases"].append(item["name"])

        inventory = next(
            (
                row
                for row in data["user_inventory"]
                if int(row["user_id"]) == int(user_id)
                and int(row["item_id"]) == int(item_id)
            ),
            None,
        )
        if inventory is None:
            data["user_inventory"].append(
                {
                    "user_id": user_id,
                    "item_id": item_id,
                    "qty": 1,
                }
            )
        else:
            inventory["qty"] = int(inventory.get("qty", 0)) + 1

        data["points_log"].append(
            {
                "user_id": user_id,
                "delta": -price,
                "reason": f"buy:{item_id}",
                "ts": local_store.now_iso(),
            }
        )
        return True, f"تم شراء {item['name']}.", int(user["points"])
