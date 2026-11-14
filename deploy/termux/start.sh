#!/data/data/com.termux/files/usr/bin/bash
# Liga o robô em segundo plano (se ainda não estiver rodando).
# Também é copiado para ~/.termux/boot/ para ligar sozinho quando o celular reinicia.

APP_DIR="$HOME/market-help"
termux-wake-lock 2>/dev/null || true  # impede o Android de "dormir" o Termux
pgrep -x sshd >/dev/null || sshd 2>/dev/null || true  # permite atualizar pelo PC via Wi-Fi

if pgrep -f "market-help/deploy/termux/loop.sh" >/dev/null; then
    exit 0  # já está rodando
fi

mkdir -p "$APP_DIR/data"
nohup bash "$APP_DIR/deploy/termux/loop.sh" >>"$APP_DIR/data/bot.log" 2>&1 &
