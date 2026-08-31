---
title: "Guia de Configuração — O Código 3:1"
subtitle: "Passo a passo completo para configurar seu Terminal"
author: "Material de Aula"
date: "25 de maio de 2026"
---

# Guia de Configuração — O Código 3:1

## Passo a passo completo para configurar seu Terminal

**Material de Aula — Edição 2026**

---


> ⚡ **ATENÇÃO — VOCÊ RODOU O INSTALADOR AUTOMÁTICO (`instalar.command`)?**
>
> Se SIM (recomendado): pule direto para a **Aula 4 — Criar bot do Telegram**.
> As Aulas 1, 2, 3 e 5 já foram executadas pelo instalador.
>
> Se NÃO (instalação manual): siga este guia desde a Aula 1.

### O que você vai conseguir ao final deste guia

- Terminal funcionando 24/7 na sua máquina
- Alertas chegando no seu Telegram
- Cobertura de jogos premium (Brasileirão, Premier League, etc.)
- Sistema rodando sozinho, sem precisar olhar

### Tempo estimado

- Aula 1 a 6: **30 minutos** (setup inicial)
- Aula 7 a 9: **15 minutos** (primeira execução)
- Aula 10 a 12: **10 minutos** (validação e operação)
- **Total: ~55 minutos**

### Símbolos usados neste guia

| Símbolo | Significado |
|---|---|
| ✅ | Passo concluído com sucesso |
| ⚠️ | Atenção — não pule este passo |
| 💡 | Dica útil |
| 🛑 | Erro comum — leia com cuidado |
| 📝 | Você precisa anotar algo |

\newpage

## Sumário

**Parte 1 — Setup do zero**

1. Pré-requisitos
2. Receber o projeto
3. Instalar Python
4. Criar bot do Telegram
5. Instalar dependências
6. Configurar arquivo `.env`

**Parte 2 — Personalização (sem mexer na regra)**

7. Adicionar suas ligas e times
8. Validar a configuração

**Parte 3 — Operação**

9. Primeira execução (teste)
10. Rodar 24/7 com o supervisor
11. Validar que está tudo OK
12. Parar, reiniciar, manutenção

**Apêndices**

A. Comandos de emergência
B. Erros comuns e soluções
C. Checklist final do aluno
D. FAQ

\newpage

# PARTE 1 — SETUP DO ZERO

## Aula 1 — Pré-requisitos

### O que você PRECISA ter ANTES de começar

| Item | Por quê |
|---|---|
| Computador macOS, Linux ou Windows com WSL | Onde o terminal vai rodar |
| Conexão de internet estável | Pra ler o Flashscore continuamente |
| Conta no Telegram + celular com Telegram | Pra receber os alertas |
| Cerca de 1 hora livre | Pra configurar com calma |
| 2 GB de espaço em disco | Python + browsers + projeto |

### O que NÃO é necessário

- Conhecimento de programação (vou explicar cada comando)
- Conta paga em nenhum serviço
- Servidor / VPS (roda no seu Mac/PC mesmo)
- Conhecimento de banco de dados

### O que ESTE GUIA NÃO cobre

- Como apostar
- Como interpretar os sinais como aposta
- Configurar servidor remoto (VPS)
- Modificar a Regra 3.1.2.0 (não toque na lógica — siga o oficial)

> 💡 **Dica:** se você é Windows puro, instale o WSL primeiro (Windows Subsystem for Linux). Procure no YouTube "instalar WSL Ubuntu" — vídeo de 5 min. Depois siga este guia normalmente dentro do WSL.

---

## Aula 2 — Receber o projeto

### Passo 2.1 — Receber a pasta do curso

Você vai receber uma pasta chamada `trading-terminal` (zipada). Pode ser via:

- Download de link enviado pelo professor
- Pendrive entregue na aula
- Repositório privado (se o curso fornece)

### Passo 2.2 — Onde colocar a pasta

> ⚠️ **IMPORTANTE:** a pasta DEVE ficar em `~/Documents/trading-terminal`. Não mude esse caminho — alguns scripts do projeto esperam essa localização exata.

**No macOS:**

```bash
# Abra o Terminal (Cmd+Espaço → digite "Terminal" → Enter)
# Vá para a pasta Documentos:
cd ~/Documents

# Se você baixou um .zip, descompacte:
unzip ~/Downloads/trading-terminal.zip -d ~/Documents/

# Confira se a pasta apareceu:
ls trading-terminal
```

Você deve ver algo assim listado:

```text
README.md       config/        live_daemon.py   src/         tests/
codigo31_supervisor.py   historical/   logs/    run_codigo31.sh
```

✅ Pasta no lugar certo.

### Passo 2.3 — Entender (rapidamente) a estrutura

Você não precisa decorar isto. Só pra contexto:

| Pasta / Arquivo | O que faz |
|---|---|
| `live_daemon.py` | O coração do sistema — o que escaneia jogos |
| `codigo31_supervisor.py` | O guardião — reinicia se travar |
| `run_codigo31.sh` | Comando único pra iniciar tudo |
| `src/` | Código interno (NÃO MEXA) |
| `config/` | Onde VOCÊ vai editar (ligas premium) |
| `logs/` | Onde ficam os logs (criado automaticamente) |
| `tests/` | Testes automáticos (você não roda) |
| `.env` | **Você vai criar** — com suas credenciais |

---

## Aula 3 — Instalar Python

### Passo 3.1 — Verificar se já tem Python

No Terminal, digite:

```bash
python3 --version
```

**Se aparecer algo como `Python 3.9.X`, `Python 3.10.X` ou `Python 3.11.X`** → ✅ tudo certo, pule para a Aula 4.

**Se aparecer erro `command not found` ou versão `Python 2.X.X`** → continue abaixo.

### Passo 3.2 — Instalar Python (macOS)

A forma mais simples é via **Homebrew**. Cole no Terminal:

```bash
# Instala Homebrew (se não tiver):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Depois, instala Python:
brew install python@3.11
```

> 💡 Pode pedir sua senha — é a senha do seu usuário Mac (não aparece nada quando você digita, é normal). Aperte Enter.

Confira:

```bash
python3 --version
```

Deve aparecer `Python 3.11.X`. ✅

### Passo 3.3 — Instalar Python (Linux / WSL)

```bash
sudo apt update
sudo apt install python3 python3-pip -y
python3 --version
```

---

## Aula 4 — Criar bot do Telegram

Aqui você vai criar um **bot pessoal** no Telegram pra receber os alertas. Leva 5 minutos.

### Passo 4.1 — Abrir o BotFather

1. Abra o Telegram (no celular ou desktop)
2. Na busca do Telegram, digite `@BotFather`
3. Toque no resultado oficial (tem ✓ azul de verificação)
4. Aperte `/start` ou "Iniciar"

### Passo 4.2 — Criar o bot

Digite no chat com BotFather:

```text
/newbot
```

Ele vai pedir:

**1. Nome do bot** (display name — qualquer coisa):

```text
Meu Codigo 3:1
```

**2. Username do bot** (deve terminar em `bot`, sem espaços, único no Telegram):

```text
meu_codigo_31_bot
```

(Se já existir, ele pede outro. Tente combinações com seu nome ou número.)

### Passo 4.3 — Anotar o TOKEN

Após criar, BotFather envia uma mensagem como:

```text
Done! Congratulations on your new bot...

Use this token to access the HTTP API:
1234567890:AAEvxXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

Keep your token secure...
```

> 📝 **ANOTE ESSE TOKEN** em algum lugar seguro. Você vai usar daqui a pouco.
> ⚠️ NÃO compartilhe com ninguém. Quem tem o token controla seu bot.

### Passo 4.4 — Descobrir seu CHAT_ID

Agora você precisa do seu chat_id pessoal (pra onde os alertas chegam).

1. No Telegram, busque por: `@userinfobot`
2. Toque no resultado oficial
3. Aperte `/start` ou "Iniciar"
4. Ele responde com algo como:

```text
👤 You
Id: 123456789
First: Tiago
...
```

> 📝 **ANOTE O `Id`** (no exemplo: `123456789`). É o seu chat_id.

### Passo 4.5 — Iniciar o bot uma vez

> ⚠️ **CRÍTICO:** o bot só consegue mandar mensagem pra você DEPOIS que você falar com ele uma vez. Faça agora:

1. No Telegram, busque pelo seu bot (`@meu_codigo_31_bot` ou o nome que você escolheu)
2. Toque nele
3. Aperte `/start` ou "Iniciar"
4. Mande qualquer mensagem, ex: `oi`

✅ Bot pronto pra receber comandos.

---

## Aula 5 — Instalar dependências

### Passo 5.1 — Entrar na pasta do projeto

```bash
cd ~/Documents/trading-terminal
pwd
```

A última linha deve mostrar `/Users/SEU_USUARIO/Documents/trading-terminal`.

### Passo 5.2 — Instalar Playwright (browser headless)

```bash
pip3 install --user playwright
```

Aguarde a instalação (1-3 minutos).

### Passo 5.3 — Instalar o navegador do Playwright

```bash
python3 -m playwright install chromium
```

Aguarde (3-5 minutos — baixa ~150MB).

### Passo 5.4 — Confirmar

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

Deve imprimir `Playwright OK`. ✅

> 🛑 **Erro comum:** se aparecer `command not found: python3`, volte para a Aula 3 (Python não está instalado).
>
> 🛑 **Erro comum:** se aparecer `Permission denied`, tente trocar `pip3 install --user playwright` por `pip3 install --break-system-packages playwright` (em sistemas mais novos do macOS).

---

## Aula 6 — Configurar arquivo `.env`

Aqui você guarda suas credenciais. Esse arquivo **fica só no seu computador, NUNCA compartilhe**.

### Passo 6.1 — Criar o arquivo `.env`

Ainda no Terminal, na pasta do projeto:

```bash
cd ~/Documents/trading-terminal
nano .env
```

(O `nano` é um editor de texto simples dentro do Terminal.)

### Passo 6.2 — Colar o conteúdo

Cole exatamente isto (substitua pelos SEUS valores anotados na Aula 4):

```text
export TELEGRAM_BOT_TOKEN="1234567890:AAEvxXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
export TELEGRAM_CHAT_ID="123456789"
```

> ⚠️ As **aspas duplas são obrigatórias**. Substitua o conteúdo entre aspas pelos seus valores.

### Passo 6.3 — Salvar e sair do nano

- Aperte `Ctrl + O` (salvar)
- Aperte `Enter` (confirmar nome do arquivo)
- Aperte `Ctrl + X` (sair)

### Passo 6.4 — Confirmar que ficou certo

```bash
cat .env
```

Deve aparecer o conteúdo que você colou (com seus valores). ✅

> 🛑 **Erro comum:** copiar/colar com aspas curvas (`"..."` ao invés de `"..."`). Use SEMPRE aspas retas. Se copiou de um PDF/Word, digite de novo no nano à mão.

### Passo 6.5 — Proteger o arquivo

```bash
chmod 600 .env
```

Agora só você consegue ler. ✅

\newpage

# PARTE 2 — PERSONALIZAÇÃO

## Aula 7 — Adicionar suas ligas e times

Você NÃO vai mexer na lógica da regra. Vai só dizer ao sistema **quais ligas/times você considera premium** (vão entrar com prioridade na watchlist).

### Passo 7.1 — Abrir o arquivo de configuração

```bash
cd ~/Documents/trading-terminal
nano config/premium_competitions.json
```

### Passo 7.2 — Entender a estrutura

O arquivo tem 4 seções principais que você pode editar:

| Seção | O que define | Tem que editar? |
|---|---|---|
| `_premium_a_leagues` | Ligas de PRIORIDADE MÁXIMA (Brasileirão, Premier, etc.) | Provavelmente não — já vem completo |
| `_premium_b_keywords` | Palavras-chave que jogam a liga pra B (Sub-20, Feminino, etc.) | Provavelmente não |
| `_highlighted_css_patterns` | Padrões CSS do Flashscore (estrela amarela) | NÃO MEXA |
| `brasileirao_serie_a`, `premier_league_ing`, etc. | Slugs de times pra cada liga | Sim, se quiser cobrir time que falta |

### Passo 7.3 — Adicionar um time que está faltando

Exemplo: você quer cobrir o Náutico (que pode subir pra Série A futuramente). O slug no Flashscore é `nautico`.

1. Encontre a seção `"brasileirao_serie_a"` no arquivo
2. Adicione `"nautico"` na lista, com vírgula:

```json
"brasileirao_serie_a": [
  "atletico-mg", "athletico-pr", "atletico-pr", "bahia",
  ...
  "vasco", "vitoria", "america-mg", "atletico-go",
  "coritiba", "chapecoense", "nautico"
],
```

> ⚠️ Atenção à vírgula: cada item tem vírgula DEPOIS, exceto o último.

### Passo 7.4 — Como descobrir o slug correto de um time

1. Abra o Flashscore.com no navegador
2. Procure o time
3. Olhe a URL — o slug é o nome do time na URL, antes do hífen e do ID

Exemplo, URL do Náutico:

```text
https://www.flashscore.com.br/equipe/nautico/XXXXXXXX/
                                   ^^^^^^^
                                   esse é o slug
```

### Passo 7.5 — Salvar

- `Ctrl + O` → Enter → `Ctrl + X`

### Passo 7.6 — Adicionar uma liga inteira (avançado)

Se for adicionar uma liga NOVA (ex: Premier League da Tailândia), você precisa também colocar o nome dela em `_premium_b_keywords` ou `_premium_a_leagues`.

Exemplo, adicionar Thai League:

```json
"_premium_a_leagues": [
  "brasileirão betano", "brasileirao betano",
  ...
  "thai league"
],
```

E criar uma nova seção:

```json
"thai_league_tailandia": [
  "buriram-united", "muangthong-united", "bangkok-united",
  "bg-pathum-united"
],
```

> 💡 Você pode editar e adicionar sem medo — o sistema sempre tem fallback. No pior caso, a liga não vira premium, mas continua sendo monitorada normalmente.

---

## Aula 8 — Validar a configuração

### Passo 8.1 — Conferir se o JSON está válido

```bash
cd ~/Documents/trading-terminal
python3 -c "import json; json.load(open('config/premium_competitions.json')); print('JSON OK')"
```

- Se aparecer `JSON OK` → ✅ tudo certo
- Se aparecer erro `JSONDecodeError` → você quebrou a estrutura. Verifique vírgulas, aspas, colchetes.

### Passo 8.2 — Confirmar que o Telegram está configurado

```bash
source .env
echo "Token termina em: ${TELEGRAM_BOT_TOKEN: -5}"
echo "Chat ID: $TELEGRAM_CHAT_ID"
```

Deve mostrar os últimos 5 caracteres do seu token e seu chat_id.

> 🛑 Se aparecer vazio, seu `.env` não está sendo carregado. Volte para a Aula 6.

\newpage

# PARTE 3 — OPERAÇÃO

## Aula 9 — Primeira execução (teste)

### Passo 9.1 — Rodar 1 ciclo só (modo teste)

```bash
cd ~/Documents/trading-terminal
source .env
python3 live_daemon.py --send-telegram --use-watchlist --mode codigo_3_1 --once
```

O `--once` faz rodar só 1 ciclo (≈ 2 minutos) e parar. Perfeito pra primeiro teste.

### Passo 9.2 — O que esperar no terminal

Você deve ver:

```text
╔══════════════════════════════════════════════╗
║  O CÓDIGO 3:1 — Terminal de Chances Claras  ║
║  Modo: ALERTA POR CHANCES CLARAS            ║
╚══════════════════════════════════════════════╝

  Agente: codigo_3_1
  Scan-alvo: 120s
  Discovery-alvo: 120s
  Telegram: PRONTO
  ...

────────────────────────────────────────────────
  🔭 DISCOVERY — HH:MM:SS — Buscando jogos ao vivo...
  🔍 N jogos descobertos → catálogo agora com N jogos

📊 DOM LEAGUE META:
   total_links:                             N
   sportName_containers_found:              N
   ...

🏆 PREMIUM A — PRIORIDADE MÁXIMA
   - Brasileirão Betano | Brasil | live=X | watchlist=X ...

SCAN #1 — HH:MM:SS — Watchlist: 15 jogos
========================================================================
  ⚽ Time A 1-0 Time B | 2T min 56
     CC: 3x1 | Total=4 | Rate=14.0
     Gols reais: 1 | Esperado por CC: 1
     Placar abaixo da produção: NÃO
     Status 3.1.2: sem alerta (goals>=expected)
  ⚽ ...
```

### Passo 9.3 — Validar que o Telegram funciona

Se algum jogo bater a regra durante o ciclo, você recebe Telegram. Mas pra **garantir** que o pipeline está OK, mesmo sem alerta natural:

1. Confira no Terminal a linha `Telegram: PRONTO` (deve estar PRONTO, não OFF nem ERRO)
2. Se aparecer `✅ Telegram enviado` em algum jogo, ABRA o Telegram no celular — a mensagem deve estar lá

> 🛑 Se o Telegram NÃO chegou:
> - Confira se você falou com seu bot pelo menos 1 vez (Aula 4, Passo 4.5)
> - Confira se o token e chat_id no `.env` estão corretos
> - Tente: `cat .env` e leia com calma cada caractere

✅ Se tudo OK, pare aqui e vamos pra operação contínua.

---

## Aula 10 — Rodar 24/7 com o supervisor

Agora vamos colocar pra rodar de verdade — sem parar, com restart automático se travar.

### Passo 10.1 — Tornar o script executável (1 vez só)

```bash
cd ~/Documents/trading-terminal
chmod +x run_codigo31.sh
```

### Passo 10.2 — Iniciar o supervisor

```bash
./run_codigo31.sh
```

Você verá:

```text
╔══════════════════════════════════════════════════════╗
║  CÓDIGO 3:1 — SUPERVISOR EXTERNO                    ║
║  Sobe daemon, vigia, mata+reinicia se travar         ║
╚══════════════════════════════════════════════════════╝

  Supervisor do CÓDIGO 3:1 iniciando.
  Startup timeout:  420s (7.0min)
  Stale heartbeat:  600s (10.0min)
  Max restarts/h:   10
  Telegram:         ATIVO
  ...

[supervisor] supervisor_started
[supervisor] started_daemon  {'pid': XXXXX, 'restart_count': 1, ...}
```

### Passo 10.3 — Deixar essa janela aberta

> ⚠️ A janela do Terminal precisa ficar **aberta** pra o sistema rodar. Se fechar, o sistema para.

Você pode:

- Minimizar a janela ✅
- Mudar pra outras telas ✅
- Travar o computador ✅ (o sistema já evita o sleep automaticamente)
- Fechar a janela ❌ (mata o sistema)
- Desligar o computador ❌ (mata o sistema)

### Passo 10.4 — O que vai aparecer em loop

A cada ~2 minutos, o terminal vai mostrar:

```text
🔭 DISCOVERY — HH:MM:SS — Buscando jogos ao vivo...
🔍 N jogos descobertos
🏆 PREMIUM A — ...
SCAN #N — Watchlist: 15 jogos
⚽ Jogo 1 — análise
⚽ Jogo 2 — análise
...
   ⏳ Dormindo XXs (Ctrl+C para parar)
```

Quando bater algum alerta, você verá no terminal:

```text
Status 3.1.2: 📡 WATCH 3.1.2 — RADAR DE GOL
✅ Telegram enviado (RADAR)
```

E no celular: mensagem chegou no Telegram. ✅

---

## Aula 11 — Validar que está tudo OK

### Comando 1 — Buscar jogo específico

```bash
python3 live_daemon.py --find-game corinthians atletico-mg
```

Mostra TUDO sobre um jogo específico: se está na watchlist, se é premium, qual liga, etc.

### Comando 2 — Ver heartbeat (saúde do sistema)

```bash
cat logs/heartbeat.json
```

Procure pelos campos:

- `"status": "alive"` ✅
- `"telegram_ready": true` ✅
- `"errors_last_cycle": 0` ✅
- `"last_scan_at"` — deve ser de menos de 5 min atrás

### Comando 3 — Ver últimos alertas

```bash
grep '"should_alert": true' logs/live_daemon_decisions.jsonl | tail -10
```

Mostra os 10 últimos alertas que dispararam.

---

## Aula 12 — Parar, reiniciar, manutenção

### Como PARAR o sistema

Na janela do supervisor:

```text
Ctrl + C
```

Espere 2-3 segundos. Vai aparecer:

```text
[!] Ctrl+C — finalizando após o ciclo atual...
DAEMON FINALIZADO
```

✅ Sistema parado.

### Como REINICIAR

```bash
cd ~/Documents/trading-terminal && ./run_codigo31.sh
```

### Quando reiniciar

Reinicie quando:

- Editar `config/premium_competitions.json` (adicionar/remover liga ou time)
- Editar `.env`
- Quiser garantir um estado limpo (1× por semana é bom)

> 💡 **Não precisa** reiniciar pra:
>
> - Pegar jogos novos (o sistema descobre sozinho a cada 2min)
> - Mudar de liga ao vivo (o discovery é dinâmico)

### Manutenção semanal recomendada

1× por semana, dê uma olhada nos logs:

```bash
cd ~/Documents/trading-terminal
du -h logs/*.jsonl logs/*.log 2>/dev/null
```

Se algum arquivo passar de 500MB, considere arquivar:

```bash
mv logs/live_daemon_decisions.jsonl logs/archive/decisions_$(date +%Y%m%d).jsonl
```

E reinicie o supervisor.

\newpage

# APÊNDICES

## Apêndice A — Comandos de emergência

### "Está dando erro, quero recomeçar do zero"

```bash
cd ~/Documents/trading-terminal
# Parar tudo
pkill -f codigo31_supervisor
pkill -f live_daemon
# Limpar heartbeat antigo
rm -f logs/heartbeat.json
# Reiniciar
./run_codigo31.sh
```

### "Telegram parou de chegar"

```bash
# Confirmar credenciais
cat .env
# Reaplicar
source .env
# Testar 1 ciclo
python3 live_daemon.py --send-telegram --use-watchlist --mode codigo_3_1 --once
```

### "Quero saber se o sistema está vivo (sem ver a tela)"

```bash
cd ~/Documents/trading-terminal
python3 -c "
import json, datetime
hb = json.load(open('logs/heartbeat.json'))
t = datetime.datetime.fromisoformat(hb['last_scan_at'])
now = datetime.datetime.now(datetime.timezone.utc)
age = (now - t).total_seconds()
print(f'Status: {hb[\"status\"]}, ultima atualizacao: {age:.0f}s atras')
"
```

---

## Apêndice B — Erros comuns e soluções

| Erro | Causa provável | Solução |
|---|---|---|
| `command not found: python3` | Python não instalado | Aula 3 |
| `ModuleNotFoundError: playwright` | Playwright não instalado | `pip3 install --user playwright` |
| `Telegram: OFF` ou `ERRO` | `.env` não carregado ou credenciais erradas | Aula 6 + `source .env` antes de rodar |
| `Permission denied: ./run_codigo31.sh` | Script sem permissão | `chmod +x run_codigo31.sh` |
| `JSONDecodeError` em `premium_competitions.json` | Vírgula/aspas erradas | Refazer Aula 7, conferir vírgulas |
| Telegram chega vazio ou só com `❌` | Bot não foi iniciado | Volte e mande `/start` pro seu bot |
| Discovery não acha jogos | Internet caiu ou Flashscore mudou DOM | Aguarde 5 min, tente de novo |
| `TargetClosedError` no Ctrl+C | Cosmético | Ignorar — não afeta nada |

---

## Apêndice C — Checklist final do aluno

Marque cada item depois de fazer:

- [ ] Python 3.9+ instalado (`python3 --version`)
- [ ] Pasta `trading-terminal` em `~/Documents/`
- [ ] Bot do Telegram criado, token anotado
- [ ] Chat ID anotado (do @userinfobot)
- [ ] Mandei `/start` pro meu bot uma vez
- [ ] Playwright instalado (`pip3 install playwright`)
- [ ] Chromium baixado (`python3 -m playwright install chromium`)
- [ ] `.env` criado com token + chat_id, salvo com aspas
- [ ] `chmod 600 .env` feito
- [ ] `config/premium_competitions.json` revisado, JSON válido
- [ ] `chmod +x run_codigo31.sh` feito
- [ ] Primeira execução com `--once` rodou sem erro
- [ ] Telegram chegou
- [ ] `./run_codigo31.sh` rodando agora
- [ ] `cat logs/heartbeat.json` mostra `status: alive`
- [ ] Sei como parar (Ctrl+C) e reiniciar

---

## Apêndice D — FAQ

**P: Quanto tempo o terminal precisa ficar ligado?**
R: 24/7. Cada ciclo dura ~2 min. Sistema escaneia jogos ao vivo continuamente.

**P: Posso rodar no Mac antigo / pouca RAM?**
R: Sim. Consumo é baixo (~500MB RAM, 5-10% CPU). Funciona em Mac de 2015+.

**P: Posso rodar em VPS / servidor?**
R: Tecnicamente sim, mas este guia cobre só máquina local. Pra VPS, precisa de tutorial específico.

**P: O sistema entra em jogos de times brasileiros das séries menores?**
R: Depende do que está em `config/premium_competitions.json`. Sai com Série A e B incluídas. Pra Série C/D, adicione os times manualmente.

**P: O Telegram tem limite de mensagens?**
R: Sim — Telegram limita ~30 mensagens/segundo pra bots. Como o terminal manda no máximo 1 alerta a cada 2min por jogo, você nunca chega no limite.

**P: Posso ter mais de um bot?**
R: Sim, mas o sistema só usa 1 por vez. Pra mudar, edite `.env`.

**P: Como adiciono outro chat (ex: enviar pra um grupo do Telegram)?**
R: Por enquanto o sistema só suporta 1 chat_id. Pra grupo: adicione seu bot no grupo, descubra o chat_id do grupo (começa com `-100...`), e use esse no `.env`.

**P: O sistema funciona com torneios de seleções (Copa do Mundo, Eurocopa)?**
R: Sim, se o Flashscore destacar a competição. Adicione manualmente no config se quiser garantir.

**P: Posso modificar a Regra 3.1.2.0?**
R: **NÃO**. A regra foi calibrada com base em 3.000 jogos analisados. Mudanças quebram a integridade do sistema. Se quiser regra própria, é outro projeto.

**P: Como recebo atualizações futuras?**
R: O professor envia a nova versão da pasta. Substitua `src/`, `live_daemon.py` e arquivos do código. **NÃO substitua** `.env` nem `config/premium_competitions.json` (são seus).

**P: Posso usar pra outros esportes além de futebol?**
R: Não. O sistema é específico pra futebol (estatísticas de Big Chance, xG, etc.).

**P: O sistema "aposta sozinho"?**
R: **Não**. Ele só MONITORA e ALERTA. Toda decisão de aposta é sua. Os alertas são informação, não recomendação.

---

## Encerramento

Pronto. Seu terminal está rodando, configurado, recebendo alertas no seu Telegram.

**Próximos passos sugeridos** (para você, depois da aula):

1. Deixe rodar 24h e observe o volume de alertas
2. Confira no Telegram qual nível (WATCH / FORTE / PREMIUM) você acha mais útil
3. Cruze os alertas com os resultados finais dos jogos
4. Se notar que falta alguma liga relevante, adicione no config

**Lembre-se:** este é um TERMINAL DE INFORMAÇÃO. Ele te dá um sinal estatístico — a decisão de operar é sempre sua.

---

**Guia de Configuração v1.0** — © Material de Aula — 25 de maio de 2026.
