import asyncio
import logging

from .bot import Bot
from .config import load_config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(Bot(load_config()).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
