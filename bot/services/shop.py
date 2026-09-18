"""JSON shop service; the same contract can later be backed by PostgreSQL."""
from bot.services import local_store

DEFAULT_ITEMS = [
    {"item_id": 1, "name": "وجبة فاخرة", "price": 25, "effect_type": "hunger", "effect_value": 35},
    {"item_id": 2, "name": "لعبة ريشة", "price": 30, "effect_type": "happiness", "effect_value": 25},
    {"item_id": 3, "name": "طوق أزرق", "price": 60, "effect_type": "cosmetic_collar", "effect_value": 1},
]


async def list_items() -> list[dict]:
    async with local_store._lock:
        data = local_store._read()
        if not data.get("items"):
            data["items"] = DEFAULT_ITEMS.copy()
            local_store._write(data)
        return data["items"]


async def open_shop(user_id: int) -> list[dict]:
    await local_store.clear_purchases(user_id)
    return await list_items()


async def buy_item(user_id: int, item_id: int) -> tuple[bool, str, int]:
    async with local_store._lock:
        data = local_store._read()
        if not data.get("items"):
            data["items"] = DEFAULT_ITEMS.copy()
        item = next((row for row in data["items"] if row["item_id"] == item_id), None)
        if item is None:
            return False, "الغرض غير موجود.", 0
        user = data["users"].setdefault(str(user_id), {
            "user_id": user_id,
            "points": 100,
            "created_at": local_store.now_iso(),
        })
        if user["points"] < item["price"]:
            return False, "رصيدك من العملة القططية لا يكفي.", user["points"]
        user["points"] -= item["price"]
        user.setdefault("purchases", []).append(item["name"])
        inventory = next(
            (row for row in data["user_inventory"] if row["user_id"] == user_id and row["item_id"] == item_id),
            None,
        )
        if inventory is None:
            data["user_inventory"].append({"user_id": user_id, "item_id": item_id, "qty": 1})
        else:
            inventory["qty"] += 1
        data["points_log"].append({
            "user_id": user_id,
            "delta": -item["price"],
            "reason": f"buy:{item_id}",
            "ts": local_store.now_iso(),
        })
        local_store._write(data)
        return True, f"تم شراء {item['name']}.", user["points"]
