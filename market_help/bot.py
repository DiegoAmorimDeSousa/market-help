"""O robô: recebe comandos pelo Telegram e roda a verificação periódica."""

import asyncio
import logging
import re

from .checker import check_products, collect_deals, describe_watch, find_matches, format_deal
from .config import Config
from .db import Database
from .matcher import parse_watch_text
from .models import Watch
from .sources import amazon, make_client
from .telegram import Telegram
from .textutil import brl, esc, parse_price

log = logging.getLogger(__name__)

MAX_PER_WATCH = 5  # máximo de notificações por item em cada rodada (evita enxurrada)

HELP = """🤖 <b>Market Help</b> — eu te aviso só das promoções que você pedir.

<b>Monitorar um termo</b> (Pelando, Promobit, Oferta Esperta):
<code>/add air fryer até 300</code>
<code>/add rtx 4060 até 1800 exceto usado, recondicionado</code>
<code>/add fone sem fio até 150 loja amazon, mercado livre</code>

• <b>até</b> = preço máximo
• <b>exceto</b> = palavras que você NÃO quer no título
• <b>loja</b> = só dessas lojas

<b>Acompanhar o preço de um produto da Amazon</b>:
<code>/acompanhar https://www.amazon.com.br/dp/XXXX até 500</code>
(sem "até", eu aviso sempre que o preço cair)

<b>Outros comandos</b>
/lista — o que estou monitorando
/remover 2 — remove o alerta #2 (ou <code>/remover A1</code> para produto)
/testar air fryer até 300 — mostra o que eu acharia agora, sem salvar
/checar — verifica tudo agora
/ajuda — esta mensagem"""

OWNER_HELP = """

<b>👑 Só para você (dono)</b>
/usuarios — quem pediu acesso / quem está liberado
/liberar 123456 — libera uma pessoa
/bloquear 123456 — tira o acesso (e apaga os alertas dela)"""

COMMANDS = [
    ("add", "Monitorar um termo: /add air fryer até 300"),
    ("acompanhar", "Acompanhar link da Amazon: /acompanhar <link> até 500"),
    ("lista", "Ver o que está sendo monitorado"),
    ("remover", "Remover um alerta: /remover 2 ou /remover A1"),
    ("testar", "Ver resultados agora sem salvar"),
    ("checar", "Verificar tudo agora"),
    ("ajuda", "Como usar"),
]


def _display_name(message: dict) -> str:
    user = message.get("from") or {}
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "Alguém"
    if user.get("username"):
        name += f" (@{user['username']})"
    return name


class Bot:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)
        if self.owner:
            self.db.assign_orphans(self.owner)
        self.tg = Telegram(config.telegram_token)
        self.http = make_client()
        self.lock = asyncio.Lock()

    # ---------- quem pode usar ----------
    @property
    def owner(self) -> str | None:
        return self.config.telegram_chat_id or self.db.get_meta("owner_chat_id")

    def is_allowed(self, chat_id: str | None) -> bool:
        return chat_id is not None and (chat_id == self.owner or self.db.is_approved(chat_id))

    # ---------- verificação ----------
    async def run_check(self) -> int:
        """Roda uma verificação completa para todos. Devolve quantas notificações foram enviadas."""
        async with self.lock:
            sent = 0
            watches = [w for w in self.db.list_watches() if self.is_allowed(w.chat_id)]
            if watches:
                deals = await collect_deals(self.http, [w.query for w in watches])
                log.info("Verificação: %d ofertas coletadas, %d alertas", len(deals), len(watches))
                for w in watches:
                    new = [d for d in find_matches(w, deals, self.config.max_age_hours)
                           if not self.db.was_sent(w.id, d.key)]
                    for d in new[:MAX_PER_WATCH]:
                        await self.tg.send(w.chat_id, format_deal(d, w))
                        sent += 1
                    for d in new:  # marca todas, mesmo as que passaram do limite
                        self.db.mark_sent(w.id, d.key)
            allowed = {c for c in {p.chat_id for p in self.db.list_products()} if self.is_allowed(c)}
            for chat_id, msg in await check_products(self.http, self.db, allowed):
                await self.tg.send(chat_id, msg)
                sent += 1
            self.db.cleanup_sent()
            return sent

    async def periodic(self) -> None:
        while True:
            try:
                n = await self.run_check()
                log.info("Verificação concluída: %d notificação(ões)", n)
            except Exception:
                log.exception("Erro na verificação")
            await asyncio.sleep(self.config.check_interval_min * 60)

    # ---------- comandos ----------
    async def handle(self, message: dict) -> None:
        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        cmd, _, args = text.partition(" ")
        cmd = cmd[1:].split("@")[0].lower()
        args = args.strip()

        if self.owner is None and cmd == "start":
            self.db.set_meta("owner_chat_id", chat_id)
            self.db.assign_orphans(chat_id)
            log.info("Dono do bot registrado: chat %s", chat_id)

        if not self.is_allowed(chat_id):
            await self.handle_stranger(chat_id, cmd, message)
            return

        handler = {
            "start": self.cmd_help, "ajuda": self.cmd_help, "help": self.cmd_help,
            "add": self.cmd_add, "monitorar": self.cmd_add,
            "lista": self.cmd_list, "remover": self.cmd_remove,
            "acompanhar": self.cmd_track,
            "testar": self.cmd_test, "checar": self.cmd_check,
        }.get(cmd)
        if chat_id == self.owner:
            handler = handler or {
                "usuarios": self.cmd_users, "liberar": self.cmd_approve, "bloquear": self.cmd_block,
            }.get(cmd)
        if handler is None:
            await self.tg.send(chat_id, "Não conheço esse comando. Mande /ajuda.")
            return
        try:
            await handler(chat_id, args)
        except Exception:
            log.exception("Erro no comando /%s", cmd)
            await self.tg.send(chat_id, "😵 Deu erro ao executar o comando. Tente de novo mais tarde.")

    async def handle_stranger(self, chat_id: str, cmd: str, message: dict) -> None:
        """Quem ainda não foi liberado: /start vira um pedido de acesso para o dono."""
        if cmd != "start":
            await self.tg.send(chat_id, "🔒 Este robô é particular. Mande /start para pedir acesso.")
            return
        name = _display_name(message)
        self.db.request_access(chat_id, name)
        await self.tg.send(chat_id, "📨 Pedido de acesso enviado ao dono do robô. Te aviso quando for liberado!")
        if self.owner:
            await self.tg.send(
                self.owner,
                f"🙋 <b>{esc(name)}</b> quer usar o robô.\n"
                f"Para liberar, toque: /liberar {chat_id}\n"
                f"(se não conhece, é só ignorar)",
            )

    async def cmd_help(self, chat_id: str, args: str) -> None:
        await self.tg.send(chat_id, HELP + (OWNER_HELP if chat_id == self.owner else ""), preview=False)

    async def cmd_add(self, chat_id: str, args: str) -> None:
        query, max_price, exclude, stores = parse_watch_text(args)
        if not query:
            await self.tg.send(chat_id, "Diga o que monitorar. Ex.: <code>/add air fryer até 300</code>")
            return
        w = self.db.add_watch(chat_id, query, max_price, exclude, stores)
        await self.tg.send(chat_id, f"✅ Alerta #{w.id} criado: {describe_watch(w)}\nVou procurar agora…", preview=False)

        # Mostra o que já existe hoje e marca como enviado, para não repetir depois.
        async with self.lock:
            deals = await collect_deals(self.http, [w.query])
        found = find_matches(w, deals, self.config.max_age_hours)
        for d in found:
            self.db.mark_sent(w.id, d.key)
        if not found:
            await self.tg.send(chat_id, "Nada no momento. Te aviso quando aparecer! 👀")
            return
        await self.tg.send(chat_id, f"Encontrei {len(found)} oferta(s) agora. As melhores:")
        for d in found[:MAX_PER_WATCH]:
            await self.tg.send(chat_id, format_deal(d))

    async def cmd_test(self, chat_id: str, args: str) -> None:
        query, max_price, exclude, stores = parse_watch_text(args)
        if not query:
            await self.tg.send(chat_id, "Ex.: <code>/testar air fryer até 300</code>")
            return
        w = Watch(0, query, max_price, exclude, stores)
        deals = await collect_deals(self.http, [query])
        found = find_matches(w, deals, self.config.max_age_hours)
        await self.tg.send(chat_id, f"🧪 {describe_watch(w)}: {len(found)} resultado(s) nas últimas {self.config.max_age_hours}h.", preview=False)
        for d in found[:MAX_PER_WATCH]:
            await self.tg.send(chat_id, format_deal(d))

    async def cmd_list(self, chat_id: str, args: str) -> None:
        watches, products = self.db.list_watches(chat_id), self.db.list_products(chat_id)
        if not watches and not products:
            await self.tg.send(chat_id, "Lista vazia. Use /add ou /acompanhar. Veja /ajuda.")
            return
        lines = []
        if watches:
            lines.append("<b>🔎 Termos monitorados</b>")
            lines += [f"#{w.id} — {describe_watch(w)}" for w in watches]
        if products:
            lines.append("\n<b>📦 Produtos da Amazon</b>")
            for p in products:
                alvo = f" · alvo {brl(p.target_price)}" if p.target_price else " · aviso em qualquer queda"
                atual = f" · atual {brl(p.last_price)}" if p.last_price else ""
                name = esc((p.title or p.url)[:70])
                lines.append(f"A{p.id} — <a href=\"{esc(p.url)}\">{name}</a>{atual}{alvo}")
        await self.tg.send(chat_id, "\n".join(lines), preview=False)

    async def cmd_remove(self, chat_id: str, args: str) -> None:
        m = re.fullmatch(r"#?([aA])?(\d+)", args)
        if not m:
            await self.tg.send(chat_id, "Ex.: <code>/remover 2</code> ou <code>/remover A1</code>. Veja os números em /lista.")
            return
        is_product, num = bool(m.group(1)), int(m.group(2))
        ok = self.db.remove_product(num, chat_id) if is_product else self.db.remove_watch(num, chat_id)
        label = f"A{num}" if is_product else f"#{num}"
        await self.tg.send(chat_id, f"🗑️ {label} removido." if ok else f"Não achei {label} na sua lista.")

    async def cmd_track(self, chat_id: str, args: str) -> None:
        m = re.match(r"(\S+)(?:\s+at[eé]\s+(.+))?$", args, re.I)
        if not m or not amazon.is_amazon_url(m.group(1)):
            await self.tg.send(chat_id, "Mande um link da Amazon. Ex.: <code>/acompanhar https://www.amazon.com.br/dp/XXXX até 500</code>", preview=False)
            return
        target = parse_price(m.group(2)) if m.group(2) else None
        url = amazon.clean_url(m.group(1))
        try:
            info = await amazon.fetch(self.http, url)
        except Exception as e:
            log.warning("Falha ao ler %s: %s", url, e)
            info = None
        p = self.db.add_product(chat_id, url, target)
        if info:
            p.title, p.last_price = info.title, info.price
            self.db.update_product(p)
        alvo = f"Aviso quando chegar em {brl(target)}." if target else "Aviso sempre que o preço cair."
        atual = f"Preço atual: {brl(info.price)}" if info and info.price else "Não consegui ler o preço agora; tento de novo na próxima rodada."
        await self.tg.send(chat_id, f"📦 Acompanhando A{p.id}: {esc(p.title or url)}\n{atual}\n{alvo}", preview=False)

    async def cmd_check(self, chat_id: str, args: str) -> None:
        await self.tg.send(chat_id, "🔄 Verificando…")
        await self.run_check()
        await self.tg.send(chat_id, "Pronto! Se tinha novidade, já te mandei. 👍")

    # ---------- comandos do dono ----------
    async def cmd_users(self, chat_id: str, args: str) -> None:
        users = self.db.list_users()
        if not users:
            await self.tg.send(chat_id, "Ninguém pediu acesso ainda. A pessoa precisa abrir o bot e mandar /start.")
            return
        lines = ["<b>👥 Usuários</b>"]
        for u in users:
            if u["approved"]:
                lines.append(f"✅ {esc(u['name'])} — /bloquear {u['chat_id']}")
            else:
                lines.append(f"⏳ {esc(u['name'])} — /liberar {u['chat_id']}")
        await self.tg.send(chat_id, "\n".join(lines))

    async def cmd_approve(self, chat_id: str, args: str) -> None:
        target = args.strip()
        name = self.db.approve_user(target) if target else None
        if name is None:
            await self.tg.send(chat_id, "Não achei esse pedido. A pessoa precisa mandar /start no bot primeiro. Veja /usuarios.")
            return
        await self.tg.send(chat_id, f"✅ {esc(name)} liberado(a)! Cada um tem sua própria lista.")
        await self.tg.send(target, "🎉 Seu acesso foi liberado!\n\n" + HELP, preview=False)

    async def cmd_block(self, chat_id: str, args: str) -> None:
        target = args.strip()
        if target == self.owner:
            await self.tg.send(chat_id, "Você não pode bloquear a si mesmo. 🙂")
            return
        ok = self.db.remove_user(target) if target else False
        await self.tg.send(chat_id, "🚫 Acesso removido e alertas apagados." if ok else "Não achei esse usuário. Veja /usuarios.")

    # ---------- loop principal ----------
    async def poll(self) -> None:
        while True:
            try:
                for update in await self.tg.get_updates():
                    if "message" in update:
                        asyncio.create_task(self.handle(update["message"]))
            except Exception as e:
                log.warning("Erro ao buscar mensagens do Telegram: %s", e)
                await asyncio.sleep(5)

    async def run(self) -> None:
        me = await self.tg.get_me()
        await self.tg.set_commands(COMMANDS)
        log.info("Bot @%s no ar. Verificando a cada %d min.", me["username"], self.config.check_interval_min)
        if self.owner is None:
            log.info("Abra https://t.me/%s e mande /start para vincular o bot a você.", me["username"])
        try:
            await asyncio.gather(self.poll(), self.periodic())
        finally:
            await self.http.aclose()
            await self.tg.close()
