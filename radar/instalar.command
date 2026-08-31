#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#   O CÓDIGO 3:1 — INSTALADOR AUTOMÁTICO (Mac)
#   Duplo-clique pra rodar. Instala tudo que você precisa.
# ═══════════════════════════════════════════════════════════════

# Garante que o terminal abre na pasta do script
cd "$(dirname "$0")"

# Cores pra mensagens ficarem legíveis
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
VERMELHO='\033[0;31m'
SEM_COR='\033[0m'

mostrar_passo() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════════════"
}

erro_e_sai() {
    echo ""
    echo -e "${VERMELHO}❌ ERRO: $1${SEM_COR}"
    echo ""
    echo "Não consegui continuar. Abra o LEIA-ME-PRIMEIRO.txt e leia"
    echo "a seção 'DEU ERRO?' pra ver as soluções comuns."
    echo ""
    read -p "Aperta Enter pra fechar esta janela..."
    exit 1
}

clear
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║     O CÓDIGO 3:1 — INSTALADOR AUTOMÁTICO                     ║"
echo "║     Sistema de Trading Esportivo                             ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Este instalador vai fazer 6 coisas pra você:"
echo "  1. Verificar que a pasta trading-terminal está no lugar certo"
echo "  2. Verificar/instalar o Python 3"
echo "  3. Instalar as bibliotecas necessárias"
echo "  4. Instalar o navegador Chromium (Playwright)"
echo "  5. Criar o arquivo .env vazio pra você preencher"
echo "  6. Validar que tudo funciona"
echo ""
echo "Tempo estimado: 10-15 minutos"
echo ""
read -p "Aperta Enter pra começar..."

# ─────────────────────────────────────────────────────────────
# PASSO 1: Verificar pasta
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 1/6 — Verificar a pasta trading-terminal"

PROJETO="$HOME/Documents/trading-terminal"

if [ ! -d "$PROJETO" ]; then
    echo ""
    echo -e "${VERMELHO}Não encontrei a pasta em $PROJETO${SEM_COR}"
    echo ""
    echo "VOCÊ ESQUECEU DO PASSO 1 DO LEIA-ME."
    echo ""
    echo "Faça isto agora:"
    echo "  1. Saia deste instalador (aperta Enter)"
    echo "  2. Volta no Finder"
    echo "  3. Arrasta a pasta 'trading-terminal' (que veio neste zip)"
    echo "     pra dentro de Documentos"
    echo "  4. Roda o instalar.command de novo"
    echo ""
    read -p "Aperta Enter pra fechar..."
    exit 1
fi

if [ ! -f "$PROJETO/live_daemon.py" ]; then
    erro_e_sai "Pasta existe mas live_daemon.py não está dentro. Verifica se você descompactou tudo direito."
fi

echo -e "${VERDE}✅ Pasta encontrada em: $PROJETO${SEM_COR}"

# ─────────────────────────────────────────────────────────────
# PASSO 2: Python
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 2/6 — Verificar Python 3"

if ! command -v python3 &> /dev/null; then
    echo -e "${AMARELO}⚠️  Python 3 não encontrado. Instalando via Homebrew...${SEM_COR}"

    # Verifica Homebrew
    if ! command -v brew &> /dev/null; then
        echo "Instalando Homebrew primeiro (gerenciador de pacotes do Mac)..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
            || erro_e_sai "Falha ao instalar Homebrew. Tenta de novo ou contacta suporte."

        # Apple Silicon: brew fica em /opt/homebrew. Mac Intel: /usr/local.
        # Carrega o PATH do brew na sessão atual pra o comando 'brew install' funcionar.
        if [ -f "/opt/homebrew/bin/brew" ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f "/usr/local/bin/brew" ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi

    brew install python@3.11 || erro_e_sai "Falha ao instalar Python via Homebrew."
fi

PYTHON_VER=$(python3 --version 2>&1)
echo -e "${VERDE}✅ $PYTHON_VER instalado${SEM_COR}"

# ─────────────────────────────────────────────────────────────
# PASSO 3: Bibliotecas Python
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 3/6 — Instalar bibliotecas Python"

echo "Instalando: playwright, reportlab, pyyaml..."
echo "(isto pode demorar uns 3-5 minutos)"
echo ""

pip3 install --user playwright reportlab pyyaml 2>&1 | tail -5
if [ $? -ne 0 ]; then
    # Tenta com --break-system-packages (pip mais recente)
    pip3 install --break-system-packages playwright reportlab pyyaml 2>&1 | tail -5 \
        || erro_e_sai "Falha ao instalar bibliotecas. Verifica conexão com internet."
fi

echo -e "${VERDE}✅ Bibliotecas instaladas${SEM_COR}"

# ─────────────────────────────────────────────────────────────
# PASSO 4: Chromium do Playwright
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 4/6 — Instalar navegador Chromium"

echo "Baixando Chromium (necessário pra ler Flashscore)..."
echo "(isto pode demorar uns 5-8 minutos — vai baixar ~150MB)"
echo ""

python3 -m playwright install chromium || erro_e_sai "Falha ao instalar Chromium."

echo -e "${VERDE}✅ Chromium instalado${SEM_COR}"

# ─────────────────────────────────────────────────────────────
# PASSO 5: Arquivo .env
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 5/6 — Preparar arquivo de credenciais (.env)"

ENV_FILE="$PROJETO/.env"

if [ -f "$ENV_FILE" ]; then
    echo -e "${AMARELO}.env já existe em $ENV_FILE — não vou sobrescrever.${SEM_COR}"
else
    cat > "$ENV_FILE" << 'EOF'
# ═══════════════════════════════════════════════════════════════
# CREDENCIAIS DO TELEGRAM — VOCÊ TEM QUE PREENCHER ISTO
# ═══════════════════════════════════════════════════════════════
# Vá na AULA 4 do Guia_de_Configuracao_Aula.md pra criar seu bot.
# Depois cole aqui o TOKEN e o CHAT_ID:

TELEGRAM_BOT_TOKEN=cole_seu_token_aqui
TELEGRAM_CHAT_ID=cole_seu_chat_id_aqui
EOF
    echo -e "${VERDE}✅ Arquivo .env criado em $ENV_FILE${SEM_COR}"
    echo ""
    echo -e "${AMARELO}⚠️  IMPORTANTE: você AINDA precisa editar esse .env${SEM_COR}"
    echo -e "${AMARELO}    com o token e chat_id do seu bot do Telegram.${SEM_COR}"
fi

# ─────────────────────────────────────────────────────────────
# PASSO 6: Permissões de execução
# ─────────────────────────────────────────────────────────────
mostrar_passo "PASSO 6/6 — Configurar permissões dos scripts"

chmod +x "$PROJETO"/*.sh 2>/dev/null
echo -e "${VERDE}✅ Permissões configuradas${SEM_COR}"

# ─────────────────────────────────────────────────────────────
# FINAL
# ─────────────────────────────────────────────────────────────
echo ""
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo -e "║  ${VERDE}✅ INSTALAÇÃO CONCLUÍDA${SEM_COR}                                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "PRÓXIMOS PASSOS:"
echo ""
echo "  1. Abre o arquivo .env e preenche com teu Telegram bot:"
echo "       $ENV_FILE"
echo ""
echo "  2. Pra iniciar a operação, abre o Terminal e cola:"
echo ""
echo "       cd ~/Documents/trading-terminal && ./start_daemon.sh"
echo ""
echo "  3. Quando aparecer 'Telegram: PRONTO', tá no ar."
echo ""
echo "Em caso de dúvida, leia: trading-terminal/docs/Guia_de_Configuracao_Aula.md"
echo ""
read -p "Aperta Enter pra fechar esta janela..."
