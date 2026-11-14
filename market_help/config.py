import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    telegram_token: str
    telegram_chat_id: str | None
    check_interval_min: int
    max_age_hours: int
    db_path: Path


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Falta o TELEGRAM_TOKEN. Copie .env.example para .env e cole o token do @BotFather."
        )
    return Config(
        telegram_token=token,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip() or None,
        check_interval_min=int(os.getenv("CHECK_INTERVAL_MIN", "10")),
        max_age_hours=int(os.getenv("MAX_AGE_HOURS", "48")),
        db_path=Path(os.getenv("DB_PATH", str(ROOT / "data" / "market_help.db"))),
    )
