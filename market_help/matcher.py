import re
import unicodedata

from .models import Deal, Watch
from .textutil import normalize, parse_price

# "exceto" (e não "sem") para não quebrar buscas como "fone sem fio".
_KEYWORDS = re.compile(r"\b(ate|exceto|lojas?)\b")


def _contains(haystack: str, phrase: str) -> bool:
    """Cada palavra da frase precisa aparecer no início de alguma palavra do texto.
    Ex.: 'rtx 4060' casa com 'Placa RTX 4060 Ti', mas 'tv' não casa com 'estvalo'."""
    words = normalize(phrase).split()
    return bool(words) and all(re.search(rf"(?<![a-z0-9]){re.escape(w)}", haystack) for w in words)


def matches(watch: Watch, deal: Deal) -> bool:
    title = normalize(deal.title)
    if not _contains(title, watch.query):
        return False
    if any(_contains(title, ex) for ex in watch.exclude):
        return False
    if watch.max_price is not None and (deal.price is None or deal.price > watch.max_price):
        return False
    if watch.stores:
        store = normalize(deal.store or "")
        if not any(normalize(s) in store for s in watch.stores):
            return False
    return True


def parse_watch_text(text: str) -> tuple[str, float | None, list[str], list[str]]:
    """Interpreta o texto do comando /add.

    Exemplo: 'air fryer até 300 exceto usado, recondicionado loja amazon, mercado livre'
    -> ('air fryer', 300.0, ['usado', 'recondicionado'], ['amazon', 'mercado livre'])
    """
    # Trabalha numa versão sem acentos para achar as palavras-chave, mas preserva o texto original.
    plain = normalize_keep_punct(text)
    parts = _KEYWORDS.split(plain)
    query = parts[0].strip(" ,")
    max_price, exclude, stores = None, [], []
    for kw, value in zip(parts[1::2], parts[2::2]):
        value = value.strip(" ,")
        if kw == "ate":
            max_price = parse_price(value)
        elif kw == "exceto":
            exclude += [v.strip() for v in value.split(",") if v.strip()]
        else:
            stores += [v.strip() for v in value.split(",") if v.strip()]
    return query, max_price, exclude, stores


def normalize_keep_punct(text: str) -> str:
    """Como normalize(), mas mantém vírgulas e pontos (necessários para preços e listas)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9.,$ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
