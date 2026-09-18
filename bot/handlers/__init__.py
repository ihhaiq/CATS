"""
Aggregates all handler routers so main.py can register them in one shot.
Add new handler modules' routers to this list as they're implemented.
"""
from bot.handlers.adopt import router as adopt_router
from bot.handlers.care import router as care_router
from bot.handlers.partner import router as partner_router
from bot.handlers.status import router as status_router
from bot.handlers.shop import router as shop_router
from bot.handlers.shelter import router as shelter_router
from bot.handlers.inline import router as inline_router
from bot.handlers.guest import router as guest_router
from bot.handlers.rich_actions import router as rich_actions_router
from bot.handlers.media_dev import router as media_dev_router

all_routers = [
    adopt_router,
    care_router,
    partner_router,
    status_router,
    shop_router,
    shelter_router,
    inline_router,
    guest_router,
    rich_actions_router,
    media_dev_router,
]
