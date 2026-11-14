"""Pelando (pelando.com.br): busca por termo.

A página de busca é renderizada com Astro; as ofertas vêm serializadas no atributo
`props` de um <astro-island>, no formato [tipo, valor] (0 = valor simples/objeto, 1 = lista).
"""

import html
import json
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from ..models import Deal
from ..textutil import normalize

BASE = "https://www.pelando.com.br"


def _decode(value):
    if isinstance(value, list) and len(value) == 2 and isinstance(value[0], int):
        kind, inner = value
        if kind == 1 and isinstance(inner, list):
            return [_decode(v) for v in inner]
        return _decode(inner)
    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}
    return value


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_deal_dicts(obj):
    """Percorre os props procurando objetos com cara de oferta (têm slug, title e price)."""
    if isinstance(obj, dict):
        if "slug" in obj and "title" in obj and "price" in obj:
            yield obj
            return
        for v in obj.values():
            yield from _find_deal_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _find_deal_dicts(v)


def parse_page(page: str) -> list[Deal]:
    deals: dict[str, Deal] = {}
    for raw in re.findall(r'<astro-island[^>]*\sprops="([^"]*)"', page):
        if "&quot;price&quot;" not in raw:
            continue
        try:
            props = _decode(json.loads(html.unescape(raw)))
        except json.JSONDecodeError:
            continue
        for d in _find_deal_dicts(props):
            if d.get("kind") == "discussion":
                continue
            store = d.get("store") or {}
            key = f"pelando:{d.get('id') or d.get('slug')}"
            deals[key] = Deal(
                source="Pelando",
                key=key,
                title=d["title"],
                url=f"{BASE}/d/{d.get('slug')}",
                price=d.get("price"),
                store=store.get("name") if isinstance(store, dict) else None,
                coupon=d.get("couponCode"),
                published=_parse_date(d.get("firstApprovedAt") or d.get("createdAt")),
                active=d.get("status", "active") == "active",
            )
    return list(deals.values())


async def search(client: httpx.AsyncClient, query: str) -> list[Deal]:
    slug = "-".join(normalize(query).split())
    resp = await client.get(f"{BASE}/busca/{quote(slug)}")
    resp.raise_for_status()
    return parse_page(resp.text)


async def recent(client: httpx.AsyncClient) -> list[Deal]:
    resp = await client.get(f"{BASE}/recentes")
    resp.raise_for_status()
    return parse_page(resp.text)
