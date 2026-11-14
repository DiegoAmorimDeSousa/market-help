#!/data/data/com.termux/files/usr/bin/bash
# Mantém o robô rodando: se ele cair (ou for reiniciado num deploy), sobe de novo.
cd "$HOME/market-help"
while true; do
    # Mantém o log pequeno (celular tem pouco espaço)
    if [ -f data/bot.log ] && [ "$(stat -c %s data/bot.log)" -gt 5000000 ]; then
        tail -n 2000 data/bot.log > data/bot.log.tmp && mv data/bot.log.tmp data/bot.log
    fi
    .venv/bin/python -m market_help
    echo "$(date '+%F %T') robô parou; reiniciando em 10s..."
    sleep 10
done
