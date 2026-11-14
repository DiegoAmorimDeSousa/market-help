"""Amazon Brasil: lê título e preço da página de um produto específico.

A Amazon às vezes responde com captcha para robôs; nesse caso devolvemos None e
tentamos de novo na próxima rodada.
"""

import html
import re
from dataclasses import dataclass

import httpx

from ..textutil import parse_price


@dataclass
class AmazonInfo:
    title: str | None
    price: float | None
    available: bool


class Blocked(Exception):
    pass


def is_amazon_url(url: str) -> bool:
    return bool(re.match(r"https?://(www\.)?(amazon\.com\.br|amzn\.to|a\.co)/", url))


def clean_url(url: str) -> str:
    """Reduz o link ao essencial (https://www.amazon.com.br/dp/ASIN) quando possível."""
    m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return f"https://www.amazon.com.br/dp/{m.group(1)}" if m else url


def parse_page(page: str) -> AmazonInfo:
    if "captcha" in page.lower() and "productTitle" not in page:
        raise Blocked("Amazon pediu captcha")
    t = re.search(r'id="productTitle"[^>]*>\s*(.*?)\s*<', page, re.S)
    title = html.unescape(t.group(1)).strip() if t else None

    price = None
    core = page.find('id="corePrice')
    if core >= 0:
        m = re.search(r'class="a-offscreen">\s*([^<]+)<', page[core : core + 5000])
        if m:
            price = parse_price(m.group(1))
    if price is None:  # layout alternativo
        m = re.search(r'id="priceblock_(?:deal|our)price"[^>]*>([^<]+)<', page)
        if m:
            price = parse_price(m.group(1))

    unavailable = re.search(r'id="availability".{0,600}?(Não disponível|indisponível)', page, re.S | re.I)
    return AmazonInfo(title=title, price=price, available=not unavailable)


async def fetch(client: httpx.AsyncClient, url: str) -> AmazonInfo:
    resp = await client.get(url)
    if resp.status_code == 503:
        raise Blocked("Amazon respondeu 503")
    resp.raise_for_status()
    return parse_page(resp.text)
