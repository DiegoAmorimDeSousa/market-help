# Market Help 🤖

Robô de Telegram que avisa **só** das promoções que você pediu, sem a enxurrada de ofertas
irrelevantes dos grupos de promoção.

Você diz o que quer monitorar (`/add air fryer até 300`). O robô vasculha os principais sites de
promoção do Brasil a cada 10 minutos e manda uma mensagem quando aparece algo que bate com o seu
filtro.

```
🔥 Fritadeira Air Fryer Elgin 3.5L 110V
💰 R$ 151,90
🏪 Amazon · via Pelando
🔎 Alerta: air fryer · até R$ 300,00
https://www.pelando.com.br/d/...
```

## Funcionalidades

- **Alertas por termo, com filtros**: preço máximo (`até`), palavras proibidas (`exceto`) e lojas (`loja`).
- **Acompanhamento de preço na Amazon**: avisa quando o produto chega ao preço-alvo ou quando o preço cai.
- **Vários usuários**: cada pessoa tem a própria lista, e o dono libera ou bloqueia o acesso pelo próprio Telegram.
- **Sem repetição**: cada oferta é notificada uma única vez. Ofertas antigas ou encerradas são ignoradas.
- **Resiliente**: se uma fonte sai do ar ou muda o HTML, as outras continuam funcionando.

## Fontes

| Fonte | Como é lida |
|---|---|
| [Pelando](https://www.pelando.com.br) | Busca por termo; os dados são extraídos das *props* serializadas das ilhas Astro |
| [Promobit](https://www.promobit.com.br) | Ofertas recentes, a partir do `__NEXT_DATA__` (Next.js) |
| [Oferta Esperta](https://www.ofertaesperta.com) | Feed RSS |
| Amazon | Página do produto (preço e título) |

As ofertas de Mercado Livre, Magalu, Kabum, AliExpress etc. chegam por esses sites. O Mercado Livre
bloqueia acesso automatizado direto.

## Arquitetura

```
market_help/
├── bot.py          # comandos do Telegram, controle de acesso e loop de verificação
├── checker.py      # junta as ofertas das fontes, filtra e formata as notificações
├── matcher.py      # regras de correspondência e leitura de "/add ... até ... exceto ... loja ..."
├── db.py           # SQLite: alertas, produtos, usuários, ofertas já enviadas (com migração)
├── telegram.py     # cliente mínimo da Bot API (long polling)
└── sources/        # um módulo por fonte, todos devolvendo list[Deal]
```

- **Python 3.10+ com asyncio**: o long polling do Telegram e a verificação periódica rodam em paralelo,
  e as fontes são consultadas ao mesmo tempo com `asyncio.gather`.
- **Poucas dependências**: só `httpx` e `python-dotenv`. O cliente do Telegram foi escrito à mão.
- **Correspondência sem acentos e por início de palavra**: `tv` casa com "Smart TV", mas não com "estvalo".

## Rodando localmente

1. Crie um bot com o [@BotFather](https://t.me/BotFather) (`/newbot`) e copie o token.
2. Instale e rode:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # cole o token em TELEGRAM_TOKEN
.venv/bin/python -m market_help
```

3. Mande `/start` para o seu bot. O primeiro chat a fazer isso vira o dono.

## Comandos

| Comando | Exemplo |
|---|---|
| `/add` | `/add rtx 4060 até 1800 exceto usado, recondicionado` |
| | `/add fone sem fio até 150 loja amazon, mercado livre` |
| `/acompanhar` | `/acompanhar https://www.amazon.com.br/dp/B09B8VGCR8 até 500` |
| `/lista` | mostra seus alertas (#1, A1…) |
| `/remover` | `/remover 2` ou `/remover A1` |
| `/testar` | `/testar air fryer até 300` (mostra resultados sem salvar) |
| `/checar` | força uma verificação |
| `/usuarios`, `/liberar`, `/bloquear` | gestão de acesso (só o dono) |

## Deploy

O projeto inclui dois caminhos de deploy:

- **Celular Android antigo (Termux)**, que é o usado em produção: grátis, roda 24h na tomada e reinicia
  sozinho via Termux:Boot. Para enviar: `./deploy/deploy-celular.sh usuario@ip-do-celular [--primeira-vez]`.
  Veja [`deploy/termux/`](deploy/termux/).
- **Servidor Linux (VPS) com systemd**: `./deploy/deploy.sh usuario@ip [--primeira-vez]`.

## Testes

```bash
.venv/bin/python -m unittest
```

Os testes cobrem a leitura de preços e comandos, as regras de correspondência, o parser do Pelando,
os alertas de preço da Amazon, o isolamento entre usuários e a migração do banco.
