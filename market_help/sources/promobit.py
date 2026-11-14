"""Promobit (promobit.com.br): ofertas recentes, lidas do __NEXT_DATA__ da página."""

import json
import re
from datetime import datetime

import httpx

from ..models import Deal

BASE = "https://www.promobit.com.br"


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    # "-0300" -> "-03:00" (Python < 3.11 só entende o formato com dois-pontos)
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_page(page: str) -> list[Deal]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    offers = (props.get("serverOffers") or {}).get("offers") or []
    deals = []
    for o in offers:
        if not o.get("offerTitle"):
            continue
        deals.append(
            Deal(
                source="Promobit",
                key=f"promobit:{o.get('offerId')}",
                title=o["offerTitle"],
                url=f"{BASE}/oferta/{o.get('offerSlug')}/",
                price=o.get("offerPrice") or None,
                store=o.get("storeName"),
                coupon=o.get("offerCoupon") or None,
                published=_parse_date(o.get("offerPublished")),
                active=not re.search(r"EXPIR|FINISH|CLOSE|REJECT|ENDED", o.get("offerStatusName") or ""),
            )
        )
    return deals


async def recent(client: httpx.AsyncClient) -> list[Deal]:
    resp = await client.get(f"{BASE}/promocoes/recentes/")
    resp.raise_for_status()
    return parse_page(resp.text)
