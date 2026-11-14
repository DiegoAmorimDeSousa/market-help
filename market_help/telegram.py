"""Cliente mínimo da API de bots do Telegram (long polling)."""

import logging

import httpx

log = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.client = httpx.AsyncClient(timeout=60)
        self.offset = 0

    async def close(self) -> None:
        await self.client.aclose()

    async def call(self, method: str, **params) -> dict:
        resp = await self.client.post(f"{self.base}/{method}", json=params)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} falhou: {data.get('description')}")
        return data["result"]

    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def get_updates(self) -> list[dict]:
        updates = await self.call("getUpdates", offset=self.offset, timeout=30, allowed_updates=["message"])
        if updates:
            self.offset = updates[-1]["update_id"] + 1
        return updates

    async def send(self, chat_id: int | str, text: str, preview: bool = True) -> None:
        try:
            await self.call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                link_preview_options={"is_disabled": not preview},
            )
        except Exception:
            log.exception("Erro ao enviar mensagem")

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        await self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in commands])
