#!/bin/bash
# ─── Trading Terminal V1.2 — Live Daemon Launcher ───
# Uso: ./start_daemon.sh
# Parar: Ctrl+C

# NÃO usar set -e — precisamos do loop continuar mesmo quando o python sai com erro
# (self-watchdog mata com exit 99, e queremos que o bash reinicie em vez de sair)

cd "$(dirname "$0")"

# Carregar credenciais Telegram
if [ -f .env ]; then
    source .env
fi

# Verificar dependências
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "⚠️  Playwright não instalado. Instalando..."
    pip3 install playwright
    python3 -m playwright install chromium
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Trading Terminal V1.2 — LIVE DAEMON        ║"
echo "║  Modo: OPERAÇÃO DEFINITIVA                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Rodar daemon com auto-discover + Telegram, com auto-restart se cair/travar
# caffeinate -i: impede o macOS de suspender o processo (sleep)
# while true: se o python morrer (self-watchdog, crash, etc), reinicia em 10s
# (Ctrl+C duas vezes pra parar de vez — primeira mata o python, segunda o loop)
while true; do
    caffeinate -i python3 live_daemon.py \
        --send-telegram \
        --interval 120 \
        --max-games 20 \
        --use-watchlist \
        --mode codigo_3_1 \
        --scan-interval 120 \
        --discovery-interval 120 \
        "$@"
    EXIT_CODE=$?
    echo ""
    echo "⚠️  Daemon parou (código: $EXIT_CODE). Reiniciando em 10s..."
    echo "   (Ctrl+C duas vezes pra parar de vez)"
    sleep 10
done
