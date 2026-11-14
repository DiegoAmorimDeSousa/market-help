from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Deal:
    """Uma promoção encontrada em alguma fonte."""

    source: str  # ex.: "Pelando"
    key: str  # identificador único da oferta (usado para não repetir notificações)
    title: str
    url: str
    price: float | None = None
    store: str | None = None
    coupon: str | None = None
    published: datetime | None = None
    active: bool = True


@dataclass
class Watch:
    """Um item da sua lista de monitoramento."""

    id: int
    query: str
    max_price: float | None = None
    exclude: list[str] = field(default_factory=list)
    stores: list[str] = field(default_factory=list)
    chat_id: str | None = None  # quem criou o alerta (quem recebe as notificações)


@dataclass
class Product:
    """Um produto específico (link da Amazon) com preço acompanhado."""

    id: int
    url: str
    title: str | None
    target_price: float | None
    last_price: float | None
    notified_price: float | None
    chat_id: str | None = None
