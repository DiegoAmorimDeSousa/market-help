#!/data/data/com.termux/files/usr/bin/bash
# Roda NO CELULAR (Termux). Instala dependências e (re)inicia o robô.
# Pode ser executado quantas vezes quiser (é assim que as atualizações são aplicadas).
set -euo pipefail

APP_DIR="$HOME/market-help"
cd "$APP_DIR"

echo "==> Instalando pacotes do Termux (se necessário)"
for pkg in python procps; do
    dpkg -s "$pkg" >/dev/null 2>&1 || pkg install -y "$pkg"
done

echo "==> Preparando ambiente virtual"
[ -d .venv ] || python -m venv .venv
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ] || ! grep -q '^TELEGRAM_TOKEN=.\+' .env; then
    echo "ERRO: falta o arquivo .env com TELEGRAM_TOKEN em $APP_DIR" >&2
    exit 1
fi

echo "==> Configurando início automático (app Termux:Boot)"
mkdir -p "$HOME/.termux/boot"
cp deploy/termux/start.sh "$HOME/.termux/boot/market-help.sh"
chmod +x "$HOME/.termux/boot/market-help.sh" deploy/termux/*.sh

echo "==> Ligando o robô sempre que o Termux for aberto"
BASHRC_LINE='bash ~/market-help/deploy/termux/start.sh  # market-help'
touch "$HOME/.bashrc"
grep -qF "# market-help" "$HOME/.bashrc" || echo "$BASHRC_LINE" >> "$HOME/.bashrc"

echo "==> (Re)iniciando o robô"
pkill -f "python -m market_help" 2>/dev/null || true  # o loop reinicia com o código novo
bash deploy/termux/start.sh
sleep 6
tail -n 5 data/bot.log || true
echo
echo "✅ Robô no ar. Logs: tail -f ~/market-help/data/bot.log"
