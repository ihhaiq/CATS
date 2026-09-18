"""
Deep-link payloads for /start.

Telegram start payloads are public, so the cat id is signed with an HMAC keyed
on the bot token. That stops anyone from typing `?start=p_7` and co-owning a
stranger's cat, which the original plain "base64 of cat_id" sketch allowed.
"""
from __future__ import annotations

import base64
import hmac
from hashlib import sha256

PREFIX = "p"


def _sig(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:10]


def make_partner_token(cat_id: int, secret: str) -> str:
    body = f"{PREFIX}{cat_id}"
    return f"{body}_{_sig(body, secret)}"


def parse_partner_token(token: str, secret: str) -> int | None:
    if not token or "_" not in token:
        return None
    body, _, sig = token.partition("_")
    if not body.startswith(PREFIX) or not body[1:].isdigit():
        return None
    if not hmac.compare_digest(sig, _sig(body, secret)):
        return None
    return int(body[1:])
