# Trading Terminal — Motor de Decisão V1.2

Motor estatístico puro para trading de futebol. Sem odd, preço, liquidez ou EV.

## Requisitos

```bash
pip3 install pyyaml playwright
python3 -m playwright install chromium
```

## Comandos

```bash
cd ~/Documents/trading-terminal

# Etapa 1: rodar exemplos estáticos (12 cenários)
python3 main.py

# Etapa 1: rodar testes automatizados (18 testes)
python3 tests/test_decision_engine.py

# Etapa 2: loop de simulação (feed JSON local)
python3 simulation_runner.py --fast

# Etapa 3: simulação com Telegram
python3 simulation_runner.py --fast --send-telegram

# Etapa 3: testar conexão Telegram
python3 -m src.telegram_client --test
```

## Configurar Telegram

### 1. Criar bot no BotFather

1. Abra o Telegram e procure **@BotFather**.
2. Envie `/newbot`.
3. Escolha um nome (ex: "Trading Terminal V12").
4. Escolha um username (ex: `trading_terminal_v12_bot`).
5. O BotFather vai retornar o **token**. Copie-o.

### 2. Pegar o TELEGRAM_CHAT_ID

1. Abra o bot que criou no Telegram e envie qualquer mensagem (ex: "oi").
2. No terminal, rode (substitua `SEU_TOKEN`):

```bash
curl -s "https://api.telegram.org/botSEU_TOKEN/getUpdates" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('result', []):
    chat = r.get('message', {}).get('chat', {})
    if chat.get('id'):
        print(f\"Chat ID: {chat['id']}\")
        break
"
```

3. Anote o número que aparece (ex: `123456789`).

### 3. Exportar variáveis no Mac

```bash
export TELEGRAM_BOT_TOKEN='cole_seu_token_aqui'
export TELEGRAM_CHAT_ID='cole_seu_chat_id_aqui'
```

Para tornar permanente, adicione ao `~/.zshrc`:

```bash
echo "export TELEGRAM_BOT_TOKEN='seu_token'" >> ~/.zshrc
echo "export TELEGRAM_CHAT_ID='seu_chat_id'" >> ~/.zshrc
source ~/.zshrc
```

### 4. Testar conexão

```bash
python3 -m src.telegram_client --test
```

Deve aparecer no Telegram:
```
[SIMULAÇÃO]

✅ Teste de conexão Telegram — Motor V1.2
Timestamp: 2026-05-22 17:30:00 UTC

Bot conectado e pronto para notificações.
```

### 5. Rodar simulação com Telegram

```bash
python3 simulation_runner.py --fast --send-telegram
```

## Etapa 4A: Input Manual (dados reais, sem scraping)

Permite inserir manualmente dados de um jogo ao vivo. O motor aplica as regras V1.2, gera decisão, salva log e (opcionalmente) envia Telegram.

### Modo interativo (campo a campo)

```bash
python3 manual_live_input.py
```

O terminal pergunta cada campo. Ao atualizar o mesmo `match_id`, o estado anterior é carregado automaticamente (delta detection, posição aberta, anti-spam).

### Modo JSON (arquivo)

```bash
python3 manual_live_input.py --file examples/manual_live_match.json
```

### Modo JSON + Telegram

```bash
python3 manual_live_input.py --file examples/manual_live_match.json --send-telegram
```

### Atualizar o mesmo jogo

Para simular a evolução de um jogo real, basta rodar novamente com o mesmo `match_id`. O terminal:
1. Carrega o estado anterior de `logs/manual_live_state.json`
2. Injeta prev_bc para delta detection
3. Preserva posição aberta, entry data, last_signal
4. Aplica regras V1.2 com contexto completo

Exemplo de fluxo (3 atualizações do mesmo jogo):

```bash
# Scan 1: min 42, Arsenal 3x0 CC → ENTER_BACK_T1_MAIN
python3 manual_live_input.py --file examples/manual_live_match.json --send-telegram

# Scan 2: editar o JSON para min 55, CC 4x0, placar 1-0 → HOLD_BACK
python3 manual_live_input.py --file examples/manual_live_match.json

# Scan 3: editar o JSON para min 72, CC 4x3, placar 1-0 → EXIT_BACK
python3 manual_live_input.py --file examples/manual_live_match.json --send-telegram
```

### Utilitários

```bash
# Ver estado atual de todos os jogos
python3 manual_live_input.py --show-state

# Limpar estado de um jogo
python3 manual_live_input.py --clear-match LIVE_001

# Limpar todo o estado
python3 manual_live_input.py --clear-state
```

### Onde ficam os dados

| Arquivo | Descrição |
|---------|-----------|
| `logs/manual_live_state.json` | Estado persistido (posição, delta, anti-spam) |
| `logs/manual_live_decisions.jsonl` | Log de todas as decisões |
| `examples/manual_live_match.json` | Exemplo de input JSON |

## Filtros de notificação

Configuráveis em `config/config.yaml` → seção `telegram`:

| Config | Default | Efeito |
|--------|---------|--------|
| `send_info_messages` | `false` | NO_ACTION, COOLDOWN |
| `send_hold_messages` | `false` | HOLD_BACK, HOLD_OVER |
| `anti_spam_minutes` | `5` | Sinal repetido → SINAL MANTIDO |

## Etapa 4B: Live Daemon (Flashscore automático)

Loop automático que descobre jogos ao vivo no Flashscore, extrai stats via Playwright, roda o Motor V1.2 e envia Telegram.

### Iniciar (modo rápido)

```bash
cd ~/Documents/trading-terminal
./start_daemon.sh
```

### Comandos avançados

```bash
# Auto-discover + Telegram (padrão do start_daemon.sh)
source .env && python3 live_daemon.py --send-telegram

# URLs fixas (sem auto-discover)
source .env && python3 live_daemon.py --send-telegram --urls "url1,url2"

# URLs de arquivo (uma por linha)
source .env && python3 live_daemon.py --send-telegram --urls-file jogos.txt

# Ciclo único (testar sem loop)
source .env && python3 live_daemon.py --once --max-games 5

# Intervalo customizado (3 min)
source .env && python3 live_daemon.py --send-telegram --interval 180

# Browser visível (debug)
source .env && python3 live_daemon.py --headed --once --urls "url"
```

### Parâmetros

| Flag | Default | Efeito |
|------|---------|--------|
| `--send-telegram` | OFF | Ativa notificações Telegram [SIMULAÇÃO] |
| `--interval N` | 120 | Segundos entre ciclos |
| `--max-games N` | 20 | Limite de jogos por ciclo (auto-discover) |
| `--once` | OFF | Roda um ciclo e sai |
| `--headed` | OFF | Abre browser visível |
| `--urls "u1,u2"` | - | URLs fixas (desativa auto-discover) |
| `--urls-file f` | - | Arquivo com URLs |

### Onde ficam os dados

| Arquivo | Descrição |
|---------|-----------|
| `logs/live_daemon_state.json` | Estado persistido entre ciclos |
| `logs/live_daemon_decisions.jsonl` | Log de todas as decisões |

### Parar

`Ctrl+C` — finaliza após o ciclo atual (shutdown limpo).

## Status

- [x] Etapa 1: Motor de decisão (12 cenários, 18 testes)
- [x] Etapa 2: Loop simulation local (feed JSON, logs JSONL)
- [x] Etapa 3: Telegram em modo SIMULAÇÃO
- [x] Etapa 4A: Input manual (dados reais, sem scraping)
- [x] Etapa 4B: Live daemon (Flashscore → Motor V1.2 → Telegram)
- [ ] Etapa 5: Modo LIVE
