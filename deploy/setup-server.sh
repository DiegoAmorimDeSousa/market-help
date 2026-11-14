#!/usr/bin/env bash
# Roda NO SERVIDOR. Instala dependências e (re)inicia o robô como serviço.
# Pode ser executado quantas vezes quiser (é assim que as atualizações são aplicadas).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"

echo "==> Instalando Python (se necessário)"
if ! python3 -m venv --help >/dev/null 2>&1 || ! dpkg -s python3-venv >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
fi

echo "==> Preparando ambiente virtual"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ] || ! grep -q '^TELEGRAM_TOKEN=.\+' .env; then
    echo "ERRO: falta o arquivo .env com TELEGRAM_TOKEN em $APP_DIR" >&2
    exit 1
fi

echo "==> Configurando serviço systemd"
sudo tee /etc/systemd/system/market-help.service >/dev/null <<EOF
[Unit]
Description=Market Help - robo de promocoes
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m market_help
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable -q market-help
sudo systemctl restart market-help
sleep 4
sudo systemctl --no-pager --lines=5 status market-help || true
echo
echo "✅ Robô no ar. Logs ao vivo: journalctl -u market-help -f"
