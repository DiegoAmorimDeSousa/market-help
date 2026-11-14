"""Oferta Esperta (ofertaesperta.com): feed RSS de ofertas recentes."""

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from ..models import Deal
from ..textutil import parse_price

FEED = "https://www.ofertaesperta.com/feed/"


def parse_feed(xml_text: str) -> list[Deal]:
    root = ET.fromstring(xml_text)
    deals = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = item.findtext("description") or ""
        price_match = re.search(r"R\$\s*[\d.,]+", desc)
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            published = None
        deals.append(
            Deal(
                source="Oferta Esperta",
                key=f"ofertaesperta:{item.findtext('guid') or link}",
                title=title,
                url=link,
                price=parse_price(price_match.group(0)) if price_match else None,
                published=published,
            )
        )
    return deals


async def recent(client: httpx.AsyncClient) -> list[Deal]:
    resp = await client.get(FEED)
    resp.raise_for_status()
    return parse_feed(resp.text)
