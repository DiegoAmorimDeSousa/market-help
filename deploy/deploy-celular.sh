#!/usr/bin/env bash
# Roda NO SEU PC. Envia o código para o celular (Termux) e reinicia o robô.
#
#   ./deploy/deploy-celular.sh USUARIO@IP_DO_CELULAR                 # atualizar código
#   ./deploy/deploy-celular.sh USUARIO@IP_DO_CELULAR --primeira-vez  # 1ª vez: leva também sua lista
#
# O celular precisa estar no mesmo Wi-Fi e com o "sshd" ligado no Termux.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Uso: $0 usuario@ip [--primeira-vez]" >&2
    exit 1
fi

PHONE="$1"
FIRST="${2:-}"
SSH="ssh -p 8022"
cd "$(dirname "$0")/.."

EXCLUDES=(--exclude .venv --exclude __pycache__ --exclude .claude --exclude .git)
if [ "$FIRST" != "--primeira-vez" ]; then
    # Depois da 1ª vez, a lista de alertas "oficial" é a do celular: não sobrescrever.
    EXCLUDES+=(--exclude data)
else
    echo "⚠️  Lembre de PARAR o robô no seu PC (Ctrl+C) — dois robôs com o mesmo token brigam."
    EXCLUDES+=(--exclude data/bot.log)
fi

echo "==> Enviando arquivos para o celular ($PHONE)"
rsync -az -e "$SSH" "${EXCLUDES[@]}" ./ "$PHONE:market-help/"

echo "==> Configurando e reiniciando no celular"
$SSH "$PHONE" "bash ~/market-help/deploy/termux/setup.sh"
