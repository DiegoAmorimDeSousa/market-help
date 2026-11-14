"""Busca promoções nas fontes, filtra pela lista de monitoramento e decide o que notificar."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .db import Database
from .matcher import matches
from .models import Deal, Product, Watch
from .sources import amazon, ofertaesperta, pelando, promobit
from .textutil import brl, esc

log = logging.getLogger(__name__)


async def _safe(name: str, coro) -> list[Deal]:
    try:
        return await coro
    except Exception as e:  # uma fonte fora do ar não pode derrubar as outras
        log.warning("Fonte %s falhou: %s", name, e)
        return []


async def collect_deals(client: httpx.AsyncClient, queries: list[str]) -> list[Deal]:
    """Ofertas recentes das fontes gerais + busca no Pelando para cada termo monitorado."""
    tasks = [
        _safe("Promobit", promobit.recent(client)),
        _safe("Oferta Esperta", ofertaesperta.recent(client)),
        _safe("Pelando recentes", pelando.recent(client)),
    ]
    for q in dict.fromkeys(queries):  # remove duplicados mantendo a ordem
        tasks.append(_safe(f"Pelando '{q}'", pelando.search(client, q)))
    results = await asyncio.gather(*tasks)
    unique: dict[str, Deal] = {}
    for deals in results:
        for d in deals:
            unique.setdefault(d.key, d)
    return list(unique.values())


def is_fresh(deal: Deal, max_age_hours: int) -> bool:
    if not deal.active:
        return False
    if deal.published is None:
        return True
    published = deal.published if deal.published.tzinfo else deal.published.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - published <= timedelta(hours=max_age_hours)


def find_matches(watch: Watch, deals: list[Deal], max_age_hours: int) -> list[Deal]:
    found = [d for d in deals if is_fresh(d, max_age_hours) and matches(watch, d)]
    found.sort(key=lambda d: (d.price is None, d.price or 0))  # mais baratas primeiro
    return found


def describe_watch(w: Watch) -> str:
    parts = [f"<b>{esc(w.query)}</b>"]
    if w.max_price is not None:
        parts.append(f"até {brl(w.max_price)}")
    if w.exclude:
        parts.append("exceto " + ", ".join(esc(x) for x in w.exclude))
    if w.stores:
        parts.append("lojas: " + ", ".join(esc(x) for x in w.stores))
    return " · ".join(parts)


def format_deal(deal: Deal, watch: Watch | None = None) -> str:
    lines = [f"🔥 <b>{esc(deal.title)}</b>", f"💰 {brl(deal.price) if deal.price else 'ver preço no link'}"]
    if deal.coupon:
        lines.append(f"🎟️ Cupom: <code>{esc(deal.coupon)}</code>")
    where = f"🏪 {esc(deal.store)} · " if deal.store else "🏪 "
    lines.append(f"{where}via {esc(deal.source)}")
    if watch:
        lines.append(f"🔎 Alerta: {describe_watch(watch)}")
    lines.append(deal.url)
    return "\n".join(lines)


async def check_products(
    client: httpx.AsyncClient, db: Database, allowed: set[str]
) -> list[tuple[str, str]]:
    """Verifica preços dos produtos da Amazon acompanhados por link.
    Devolve (chat_id, mensagem) para cada aviso a enviar."""
    messages = []
    for p in db.list_products():
        if p.chat_id not in allowed:
            continue
        try:
            info = await amazon.fetch(client, p.url)
        except Exception as e:
            log.warning("Amazon (%s) falhou: %s", p.url, e)
            continue
        finally:
            await asyncio.sleep(3)  # não sobrecarregar a Amazon
        msg = evaluate_product(p, info.title, info.price if info.available else None)
        db.update_product(p)
        if msg:
            messages.append((p.chat_id, msg))
    return messages


def evaluate_product(p: Product, title: str | None, price: float | None) -> str | None:
    """Atualiza o produto com o preço atual e devolve uma mensagem se valer a pena avisar."""
    p.title = title or p.title
    previous = p.last_price
    if price is None:
        return None
    p.last_price = price
    name = esc(p.title or p.url)

    if p.target_price is not None:
        hit = price <= p.target_price
        if hit and (p.notified_price is None or price < p.notified_price):
            p.notified_price = price
            return (
                f"🎯 <b>Preço-alvo atingido!</b>\n{name}\n"
                f"💰 {brl(price)} (alvo: {brl(p.target_price)})\n{p.url}"
            )
        if not hit:
            p.notified_price = None  # voltou a subir: avisar de novo quando cair
        return None

    if previous is not None and price < previous:
        drop = (previous - price) / previous * 100
        return f"📉 <b>Preço caiu {drop:.0f}%</b>\n{name}\n💰 {brl(previous)} → {brl(price)}\n{p.url}"
    return None
