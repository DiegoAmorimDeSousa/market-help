import html
import re
import unicodedata


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços simples: 'Fritadeira AIR-Fryer' -> 'fritadeira air fryer'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


def parse_price(text: str | None) -> float | None:
    """Converte 'R$ 1.178,90', '1800', '1800.50' em float. Devolve None se não houver número."""
    if text is None:
        return None
    m = re.search(r"\d[\d.,]*", str(text))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s:  # formato brasileiro: 1.178,90
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):  # 1.178 ou 1.178.000
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def brl(value: float | None) -> str:
    if value is None:
        return "?"
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)
