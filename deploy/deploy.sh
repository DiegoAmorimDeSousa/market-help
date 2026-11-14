#!/usr/bin/env bash
# Roda NO SEU PC. Envia o código para o servidor e reinicia o robô.
#
#   ./deploy/deploy.sh ubuntu@IP_DO_SERVIDOR               # atualizar código
#   ./deploy/deploy.sh ubuntu@IP_DO_SERVIDOR --primeira-vez # 1ª vez: leva também sua lista de alertas
#
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Uso: $0 usuario@ip [--primeira-vez]" >&2
    exit 1
fi

SERVER="$1"
FIRST="${2:-}"
cd "$(dirname "$0")/.."

EXCLUDES=(--exclude .venv --exclude __pycache__ --exclude .claude --exclude .git)
if [ "$FIRST" != "--primeira-vez" ]; then
    # Depois da 1ª vez, a lista de alertas "oficial" é a do servidor: não sobrescrever.
    EXCLUDES+=(--exclude data)
else
    echo "⚠️  Lembre de PARAR o robô no seu PC (Ctrl+C) — dois robôs com o mesmo token brigam."
fi

echo "==> Enviando arquivos para $SERVER"
rsync -az --info=stats0 "${EXCLUDES[@]}" ./ "$SERVER:~/market-help/"

echo "==> Configurando e reiniciando no servidor"
ssh "$SERVER" "bash ~/market-help/deploy/setup-server.sh"
