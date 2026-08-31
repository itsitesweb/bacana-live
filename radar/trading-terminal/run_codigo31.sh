#!/bin/bash
# ─── CÓDIGO 3:1 — COMANDO ÚNICO DE OPERAÇÃO ────────────────────────────
#
# Este é o ÚNICO comando que o usuário roda para o CÓDIGO 3:1.
#
# Arquitetura:
#   run_codigo31.sh  →  caffeinate -i python3 codigo31_supervisor.py
#                           │
#                           └─→ live_daemon.py --send-telegram
#                                              --use-watchlist
#                                              --mode codigo_3_1
#
# O SUPERVISOR é o processo pai. Ele:
#   - inicia o daemon como processo filho (process group próprio)
#   - vigia logs/heartbeat.json
#   - mata + reinicia o daemon se travar (SIGTERM → SIGKILL no grupo)
#   - manda Telegram crítico no restart e recovery quando voltar
#
# Não roda mais ./start_daemon.sh diretamente.
# Não depende mais do self-watchdog interno do daemon.
#
# Parar: Ctrl+C (mata supervisor → supervisor mata daemon + Playwright)

cd "$(dirname "$0")"

# Carrega .env (TELEGRAM_BOT_TOKEN, etc)
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  CÓDIGO 3:1 — SUPERVISOR EXTERNO                    ║"
echo "║  Sobe daemon, vigia, mata+reinicia se travar         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# caffeinate -i: impede macOS de suspender o supervisor
# exec: substitui o bash pelo supervisor (1 processo só, sinais propagam)
exec caffeinate -i python3 codigo31_supervisor.py "$@"
