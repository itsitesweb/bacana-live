---
title: "O CÓDIGO 3:1"
subtitle: "Manual Completo — Regra 3.1.2.0"
author: "O Patrimônio — Ativos Digitais"
date: "Edição 2026"
---

![](../../assets/logo_o_patrimonio.png){width=3in}

# O CÓDIGO 3:1

## Manual Completo — Regra 3.1.2.0

### Terminal de Chances Claras

---

**O PATRIMÔNIO — Ativos Digitais**

*Produtos | Sistemas | Funcionários Digitais*

---

### Sobre este manual

| | |
|---|---|
| **Sistema** | O Código 3:1 — Terminal de Chances Claras |
| **Versão da regra** | 2.0 — REGRA 3.1.2.0 |
| **Lançamento da v2.0** | 12 de maio de 2025 |
| **Em operação contínua há** | 12 meses |
| **Edição deste manual** | 25 de maio de 2026 |
| **Status** | Operacional em produção |
| **Base estatística** | 3.000 jogos premium analisados |
| **Suite de testes** | 372 testes automatizados |

### Como ler este manual

Este documento é estruturado em **5 Partes**, cada uma autoexplicativa. Você pode ler do início ao fim (recomendado) ou pular direto para a Parte 4 (Instalação) se já entende a regra.

| Parte | Conteúdo | Para quem |
|---|---|---|
| Parte 1 | Fundamentos da regra | Todos |
| Parte 2 | A Regra 3.1.2.0 em detalhe | Todos |
| Parte 3 | Arquitetura operacional | Quem quer entender a engenharia |
| **Parte 4** | **Instalação passo a passo** | **Quem vai configurar agora** |
| Parte 5 | Operação contínua | Quem vai usar no dia a dia |

### Convenções visuais

| Símbolo | Significado |
|---|---|
| 📡 | WATCH — radar inicial, não é entrada |
| 🟠 | FORTE — sinal operacional |
| 🟢 | PREMIUM — prioridade alta |
| 🏆 | Liga premium A |
| 🥈 | Liga premium B |
| 🧩 | Premium C (fallback) |
| 📋 | Cobertura passiva |
| ⚽ | Display de jogo no terminal |
| ✅ | Passo concluído |
| ⚠️ | Atenção — não pule |
| 💡 | Dica útil |
| 🛑 | Erro comum — leia com cuidado |
| 📝 | Anotar algo |

\newpage

## Sumário

**PARTE 1 — Fundamentos**

1. A tese central
2. Histórico das versões
3. Base estatística (3.000 jogos)

**PARTE 2 — A Regra 3.1.2.0**

4. Visão geral
5. Os 8 níveis de alerta
6. Prioridade entre alertas
7. Anti-spam por bucket
8. Política de Telegram
9. Textos oficiais Telegram

**PARTE 3 — Arquitetura operacional**

10. Display no terminal
11. Cobertura premium (A/B/C)
12. Watchlist (5 tiers)
13. Anti-saturação
14. Deduplicação canônica
15. Discovery
16. Supervisor e watchdog
17. Heartbeat e logs

**PARTE 4 — Instalação passo a passo**

18. Pré-requisitos
19. Como abrir o Terminal (Mac, Windows, Linux)
20. Receber o projeto
21. Instalar Python
22. Criar bot do Telegram
23. Instalar dependências
24. Configurar credenciais (.env)
25. Adicionar suas ligas
26. Primeira execução (teste)
27. Rodar 24/7 com supervisor

**PARTE 5 — Operação contínua**

28. Validar funcionamento
29. Parar, reiniciar
30. Manutenção semanal
31. Troubleshooting

**Apêndices**

A. Comandos de emergência
B. Tabela de erros comuns
C. Checklist final
D. FAQ
E. Glossário

\newpage

# PARTE 1 — FUNDAMENTOS

## 1. A tese central

> **Em ligas profissionais de futebol, uma chance clara (Big Chance) produz, em média, um gol a cada ~1,65 — mas O Código 3:1 usa o divisor 3 como gatilho operacional CONSERVADOR de "gol devendo".**

### O que é Big Chance

**Big Chance** (CC, Chance Clara) é uma estatística do Flashscore: oportunidade em que o jogador, no fluxo natural do jogo, deveria ter convertido em gol — finalização de alta probabilidade dentro da área, frente a frente com o goleiro, contra-ataque limpo, etc.

### Por que o divisor 3 e não 1,65 (que é o real)

A análise dos 3.000 jogos da base histórica mostrou que a proporção REAL de gols/CC é **1,65 CC por gol** — quase 2× mais convertido do que a tese sugere. Por que então usamos `floor(CC/3)` em vez de `floor(CC/2)`?

**Resposta: o divisor 3 é um filtro DEFENSIVO, não estatístico.** Ele dispara apenas quando o placar está MUITO abaixo da produção — pega só ~5 % da base no gatilho extremo, mas com lift forte.

### Conceito de "gol devendo"

> **Gol devendo:** `total_goals < floor(total_cc / 3)`

Mesmo aplicando o filtro conservador, o jogo ainda produziu menos do que o piso esperado. **Esse é o sinal central da regra.**

---

## 2. Histórico das versões

| Versão | Data | Mudança principal |
|---|---|---|
| v1.0 | 22/01/2024 | Dossiê inicial — 1 nível só (alerta principal + unilateral) |
| v1.1 | 15/06/2024 | Header novo, heartbeat estrutural, watchdog externo, filtro is_live_match, faxina anti-saturação |
| **v2.0** | **12/05/2025** | **REGRA 3.1.2.0** — 8 níveis, Telegram com motivo/leitura, anti-spam que respeita WATCH, sistema Tier 0.5 premium hierárquico A/B/C, cobertura passiva, walker DOM, deduplicação canônica |

---

## 3. Base estatística — 3.000 jogos premium

### Origem dos dados

Coletados em **15 ligas premium** ao longo de meses: Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Brasileirão Série A, MLS, Eredivisie, Primeira Liga, Champions League, Europa League, Conference League, Copa Libertadores, Copa Sul-Americana.

**2.918 jogos com `big_chances` válidos** (descartados 82 sem coleta).

### Total agregado

| Métrica | Valor |
|---|---|
| Jogos válidos | 2.918 |
| Total Big Chances | 14.189 |
| Total gols | 8.604 |
| **CC / gol (REAL)** | **1,65** |
| Média CC por jogo | 4,86 |
| Média gols por jogo | 2,95 |

### Conversão por bucket de CC

| Bucket | n | CC/gol | Over 2,5 |
|---|---:|---:|---:|
| 0-2 CC | 487 | 0,92 | 26 % |
| 3-5 CC | 1.409 | 1,48 | 52 % |
| 6-8 CC | 766 | 1,85 | 75 % |
| 9-11 CC | 218 | 2,22 | 90 % |
| 12+ CC | 38 | 2,25 | 90 % |

> **Insight surpreendente:** quanto MAIS CC, PIOR a conversão. Em jogos pequenos a conversão é alta (gol oportunista compensa baixa produção). Em jogos grandes, defesa/goleiro segura mais.

### Jogos que disparariam, por divisor

| Divisor | Jogos com gol devendo |
|---|---:|
| CC/2,0 | 20,1 % |
| CC/2,5 | 9,2 % |
| **CC/3,0** (atual) | **5,4 %** |
| CC/3,5 | 2,6 % |

\newpage

# PARTE 2 — A REGRA 3.1.2.0

## 4. Visão geral

Evolução em **8 níveis operacionais**, organizados em 3 famílias:

```
OVER (gol esperado total):
   📡 WATCH OVER       — radar inicial
   🟠 FORTE OVER       — sinal operacional
   🟢 PREMIUM OVER     — prioridade alta
   🟢 PREMIUM OVER xG  — prioridade máxima (CC + xG concordam)
   🟢 BILATERAL PESADO — jogo aberto dos dois lados (3×3+)

BACK (dominante atrasado):
   📡 WATCH BACK       — radar inicial de domínio
   🟠 FORTE BACK       — sinal operacional de Back
   🟢 PREMIUM BACK     — domínio extremo
```

> Por scan, **só 1 alerta dispara por jogo** — o de maior prioridade entre todos que casaram.

### Variáveis derivadas a cada scan

```text
total_cc          = home_bc + away_bc
total_goals       = home_score + away_score
cc_rate           = minute / total_cc        (∞ se cc = 0)
expected_over     = total_cc // 3
placar_abaixo     = total_goals < expected_over

dominant_team     = home se home_bc > away_bc, senão away
dom_cc            = max(home_bc, away_bc)
opp_cc            = min(home_bc, away_bc)
cc_diff           = dom_cc - opp_cc
expected_back     = dom_cc // 3 (se dom_cc >= 3, senão 0)
dom_lead          = dominant_score - opp_score   (>=2 BLOQUEIA back)

total_xg          = home_xg + away_xg            (opcional)
```

### Bloqueios universais

- `data_is_valid = False` → sem alerta
- `scan_delay_seconds > 180` → sem alerta
- `minute <= 0` → sem alerta

---

## 5. Os 8 níveis de alerta — condições exatas

### 5.1 📡 WATCH OVER — prioridade 7

```text
total_cc        >= 3
cc_rate         <= 15
placar_abaixo   == True
```

> Bucket = `total_cc // 3`. Equivale à regra original v1.0.

### 5.2 📡 WATCH BACK — prioridade 8

```text
dominant_team   != None
dom_lead        < 2            (bloqueio universal BACK)
dom_cc          >= 3
opp_cc          <= 1
cc_diff         >= 3
dominant_score  < expected_back
```

### 5.3 🟠 FORTE OVER — prioridade 5

```text
total_cc        >= 4
cc_rate         <= 12          (mais qualificado que WATCH)
placar_abaixo   == True
```

### 5.4 🟠 FORTE BACK — prioridade 6

```text
dom_lead        < 2
dom_cc          >= 4
opp_cc          <= 1
cc_diff         >= 4
dominant_score  < expected_back
```

### 5.5 🟢 PREMIUM OVER — prioridade 3

```text
total_cc        >= 6
cc_rate         <= 12
placar_abaixo   == True
```

### 5.6 🟢 PREMIUM BACK — prioridade 4

```text
dom_lead        < 2
dom_cc          >= 6
opp_cc          == 0           (zero CC do adversário)
cc_diff         >= 6
dominant_score  < expected_back
```

### 5.7 🟢 PREMIUM OVER xG — prioridade 2

```text
total_cc        >= 6
cc_rate         <= 12
placar_abaixo   == True
total_xg        >= 2.5         (xG confirma CC)
```

> Duas métricas independentes confirmam — sinal máximo de Over.

### 5.8 🟢 PREMIUM OVER BILATERAL PESADO — prioridade 1

```text
home_bc         >= 3
away_bc         >= 3
total_cc        >= 6
placar_abaixo   == True
```

> Sem critério de rate — jogo bilateral 3×3+ é sinal forte por si só.

---

## 6. Prioridade entre alertas

Quando mais de um padrão casa, **prevalece o de menor prioridade numérica** (1 = mais forte):

| Prio | Tipo | Emoji | Label |
|---:|---|:---:|---|
| 1 | over_bilateral_premium | 🟢 | PREMIUM 3.1.2 — OVER BILATERAL PESADO |
| 2 | over_premium_xg | 🟢 | PREMIUM 3.1.2 — CC + xG CONFIRMADOS |
| 3 | over_premium | 🟢 | PREMIUM 3.1.2 — GOL MUITO DEVENDO |
| 4 | back_premium | 🟢 | PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO |
| 5 | over_forte | 🟠 | FORTE 3.1.2 — GOL DEVENDO |
| 6 | back_forte | 🟠 | FORTE 3.1.2 — BACK DOMINANTE |
| 7 | over_watch | 📡 | WATCH 3.1.2 — RADAR DE GOL |
| 8 | back_watch | 📡 | WATCH 3.1.2 — RADAR DE BACK DOMINANTE |

---

## 7. Anti-spam por bucket

| Mercado | Definição | State persistido |
|---|---|---|
| OVER | `bucket_over = total_cc // 3` | `main_bucket_last` |
| BACK | `bucket_back = dom_cc // 3` | `unilateral_bucket_last` |

**Regra:** alerta só dispara se `bucket_atual > bucket_last`. Se bate condição mas bucket ≤ last → `filter_reason = "bucket_already_sent"`.

**Exceção crítica:** WATCH não consome bucket. Permite que um jogo passe por WATCH e depois evolua pra FORTE/PREMIUM no mesmo bucket que dispara Telegram normalmente.

---

## 8. Política de Telegram

| Nível | Telegram | Consome bucket | Linguagem |
|---|:-:|:-:|---|
| 📡 WATCH OVER | **SIM** | **NÃO** | Radar — "não é entrada automática" |
| 📡 WATCH BACK | **SIM** | **NÃO** | Radar |
| 🟠 FORTE OVER | SIM | SIM | Operacional — "avaliar entrada" |
| 🟠 FORTE BACK | SIM | SIM | Operacional — Back dominante |
| 🟢 PREMIUM OVER | SIM | SIM | "prioridade alta" |
| 🟢 PREMIUM BACK | SIM | SIM | "reação do dominante" |
| 🟢 PREMIUM OVER xG | SIM | SIM | "prioridade máxima" |
| 🟢 BILATERAL PESADO | SIM | SIM | "padrão Over/BTTS" |

---

## 9. Textos oficiais Telegram

### 📡 WATCH OVER

```text
📡 WATCH 3.1.2 — RADAR DE GOL
{home} {home_score}-{away_score} {away}
Min {minute} | CC: {home_bc}x{away_bc} = {total_cc} | Rate: {cc_rate}
Esperado por CC: {expected_goals_by_cc} | Gols reais: {total_goals}

Motivo:
Produção suficiente para gol, mas o placar ainda não pagou.

Leitura:
Radar ativo. Não é entrada automática. Aguardar nova CC ou evolução para FORTE/PREMIUM.
```

### 📡 WATCH BACK

```text
📡 WATCH 3.1.2 — RADAR DE BACK DOMINANTE
{home} {home_score}-{away_score} {away}
Min {minute} | Dominante: {dominant_team}
CC: {home_bc}x{away_bc} | Diff CC: {cc_diff}
Esperado dominante: {expected_dominant_goals_by_cc} | Gols dominante: {dominant_score}

Motivo:
Um time começou a abrir vantagem em chances claras, mas o placar ainda não refletiu.

Leitura:
Radar ativo. Não é entrada automática. Aguardar confirmação de domínio para FORTE/PREMIUM.
```

### 🟠 FORTE OVER

```text
🟠 FORTE 3.1.2 — GOL DEVENDO

Motivo:
Produção ofensiva forte, rate qualificado e placar abaixo da produção.

Leitura:
Sinal operacional. Avaliar entrada em gol/Over conforme odd e contexto.
```

### 🟠 FORTE BACK

```text
🟠 FORTE 3.1.2 — BACK DOMINANTE

Motivo:
Dominante tem vantagem clara em chances, mas o placar ainda não pagou essa produção.

Leitura:
Sinal operacional para Back do dominante. Confirmar pressão atual antes da entrada.
```

### 🟢 PREMIUM OVER

```text
🟢 PREMIUM 3.1.2 — GOL MUITO DEVENDO

Motivo:
Volume alto de chances claras e placar claramente atrasado.

Leitura:
Sinal premium de gol atrasado. Prioridade alta para análise de entrada.
```

### 🟢 PREMIUM OVER xG

```text
🟢 PREMIUM 3.1.2 — CC + xG CONFIRMADOS
xG total: {total_xg}

Motivo:
Chances claras e xG confirmam alta produção ofensiva com placar abaixo.

Leitura:
Sinal premium confirmado por duas métricas. Prioridade máxima.
```

### 🟢 BILATERAL PESADO

```text
🟢 PREMIUM 3.1.2 — OVER BILATERAL PESADO

Motivo:
Os dois times já criaram 3+ chances claras. Jogo aberto dos dois lados.

Leitura:
Padrão forte para Over/BTTS. Não é sinal de Back; é sinal de jogo aberto.
```

### 🟢 PREMIUM BACK

```text
🟢 PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO

Motivo:
Domínio extremo em chances claras, adversário sem produção relevante e placar contra a lógica do jogo.

Leitura:
Sinal premium para reação do dominante. Prioridade alta.
```

\newpage

# PARTE 3 — ARQUITETURA OPERACIONAL

## 10. Display no terminal

### Bloco por jogo escaneado

```text
⚽ {home} {home_score}-{away_score} {away} | {half} min {minute}
   CC: {home_bc}x{away_bc} | Total={total_cc} | Rate={cc_rate}
   Gols reais: {total_goals} | Esperado por CC: {expected_by_cc}
   Placar abaixo da produção: SIM/NÃO
   Status 3.1.2: {emoji} {label}            ← se disparar alerta
   ✅ Telegram enviado (RADAR)              ← WATCH
   ✅ Telegram enviado (bucket=N)           ← FORTE/PREMIUM
```

### Bloco de cobertura por SCAN

```text
SCAN #N — HH:MM:SS — Watchlist: 15 jogos (catálogo: 76)
🏆 Premium ao vivo na watchlist: 8

🏆 PREMIUM A — PRIORIDADE MÁXIMA
   - Brasileirão Betano | Brasil | live=2 | watchlist=2 | passiva=0 | sem_stats=0

🥈 PREMIUM B — COBERTURA SECUNDÁRIA
   - MLS Next Pro | EUA | live=2 | watchlist=1 | passiva=1 | sem_stats=0

🧩 PREMIUM C — FALLBACK POR TIME/SLUG
   - FS_XXXXXXXX | min=45 1-1 | watchlist

📋 COBERTURA PREMIUM PASSIVA (2)
   - [B] FS_YYYYYYYY | MLS Next Pro | min=30 0-0 | motivo=premium_overflow
```

---

## 11. Cobertura premium (A/B/C)

### 11.1 Detecção em 3 níveis (A > B > C)

| Prio | Regra | Reason | Como detectar |
|---|---|---|---|
| A | CSS do header destacada | `flashscore_highlighted_league` | estrela amarela do Flashscore |
| B | Nome da liga bate whitelist | `premium_league_name` | substring no config |
| C | Slug do time bate whitelist | `premium_team_slug` | match na URL |

### 11.2 Níveis hierárquicos

| Nível | Quando | Exemplos |
|---|---|---|
| **A** | Reason A/B + nome bate `_premium_a_leagues` | Brasileirão Betano, Premier League, La Liga, Bundesliga, MLS, Champions League |
| **B** | Reason A/B + nome bate `_premium_b_keywords` ou destacada mas não bate A | MLS Next Pro, NWSL, Brasileirão Feminino, Série D, Primera B |
| **C** | Reason `premium_team_slug` | Jogo só por time grande |
| **NONE** | Não-premium | Demais |

### 11.3 Cobertura passiva

Todo premium FORA da watchlist aparece com `passive_reason`:

| Motivo | Quando |
|---|---|
| `premium_overflow` | Premium live mas não coube no Tier 0.5 |
| `no_stats_backoff` | Premium em backoff de stats |
| `finished` | Marcado como finalizado |
| `stale` | TTL stale ativo |

> Nenhum premium some sem motivo.

---

## 12. Watchlist (5 tiers)

| Tier | Critério | Slot |
|---|---|---|
| Tier 0 | `has_open_position=True` ou ENTER recente | Ilimitado |
| **Tier 0.5** | `is_premium=True` + janela 0-90 | Cap = 8 |
| Tier 1 | `minute` 20-83 + `bc_sum > 0` | Quota alta |
| Tier 2 | `minute` 20-83 + sem BC + ever_loaded | Quota alta |
| Tier 3 | Resto (FIFO) | 3 slots fixos |

### Ordenação interna do Tier 0.5

| Rank | Combinação |
|---:|---|
| 1 | Premium A com stats |
| 2 | Premium A sem stats |
| 3 | Premium C com stats |
| 4 | Premium B com stats + BC>0 |
| 5 | Premium B com stats |
| 6 | Premium B sem stats |

> Premium A NUNCA perde slot pra Premium B.

---

## 13. Anti-saturação

4 mecanismos:

1. **Stale** — TTL após scan inválido (default 15min)
2. **No-stats backoff** — exponencial (10 / 20 / 30 min)
3. **Finished_or_not_live** — TTL longo (12h) pra FT/SUSPENDED/POSTPONED/CANCELLED
4. **Faxina** — remove jogos não vistos há >30 min (preserva posição aberta)

---

## 14. Deduplicação canônica

Flashscore às vezes lista o mesmo jogo com 2 URLs (com e sem `?mid=`). O sistema:

1. Extrai **fingerprint** = `home_id_away_id`
2. Quando há colisão, escolhe **canônico** (mid-based ganha)
3. Marca o outro como `excluded_duplicate=True`
4. Watchlist NUNCA pega duplicado

---

## 15. Discovery

A cada ciclo:

1. Abre Flashscore
2. Clica em "AO VIVO"
3. Expande ligas colapsadas
4. Coleta todos os links `/jogo/`
5. Walker DOM identifica liga de cada jogo
6. Detecta destaque (estrela amarela)

---

## 16. Supervisor e watchdog

- **Supervisor externo** (`codigo31_supervisor.py`): processo pai que reinicia daemon se travar
- **Self-watchdog**: thread interna que mata daemon se não responder em 8 min
- **Watchdog independente** (`watchdog.py`, opcional): segunda camada

---

## 17. Heartbeat e logs

| Arquivo | Conteúdo |
|---|---|
| `logs/heartbeat.json` | Estado atual (alive, scan_number, telegram_ready, etc.) |
| `logs/live_daemon_decisions.jsonl` | Uma linha por scan |
| `logs/codigo31_supervisor.log` | Eventos do supervisor |
| `logs/live_daemon_catalog.json` | Catálogo persistido |

\newpage

# PARTE 4 — INSTALAÇÃO PASSO A PASSO

> **Esta parte é o coração prático.** Cada passo está minuciosamente detalhado. Não importa se você tem 18 ou 70 anos, se sabe ou não de tecnologia, se usa Mac, Windows ou Linux — siga em ordem e tudo vai funcionar.
>
> Reserve cerca de 1 hora para fazer a primeira vez com calma.

## 18. Pré-requisitos

### O que VOCÊ precisa antes de começar

| Item | Por quê | Você tem? |
|---|---|---|
| Computador (Mac, Windows ou Linux) | Onde o terminal vai rodar | ☐ |
| Internet estável | Pra ler o Flashscore continuamente | ☐ |
| Smartphone com app Telegram | Pra receber alertas | ☐ |
| Conta Telegram (com número de telefone) | Pra criar o bot | ☐ |
| ~1 hora livre, sem pressa | Pra configurar com calma | ☐ |
| ~2 GB de espaço em disco | Python + browser + projeto | ☐ |

### O que NÃO é necessário

- ❌ Saber programar (vou explicar cada comando)
- ❌ Conta paga em nenhum serviço
- ❌ Servidor / VPS (roda no seu próprio computador)
- ❌ Conhecimento de banco de dados

### Quanto tempo cada etapa leva

| Etapa | Tempo médio |
|---|---|
| 19. Abrir Terminal | 1 min |
| 20. Receber projeto | 5 min |
| 21. Instalar Python | 10 min (se não tem) |
| 22. Criar bot Telegram | 5 min |
| 23. Instalar dependências | 10 min |
| 24. Configurar `.env` | 5 min |
| 25. Adicionar suas ligas | 5 min (opcional) |
| 26. Primeira execução | 5 min |
| 27. Rodar 24/7 | 2 min |
| **Total** | **~50 min** |

---

## 19. Como abrir o Terminal

O **Terminal** é o programa onde você vai digitar todos os comandos. Em cada sistema operacional ele tem nome e cara diferentes.

### 19.1 No Mac (macOS)

**Opção A — Spotlight (rápido):**

1. Aperte `Cmd + Espaço` (a tecla `⌘` ao lado da barra de espaço + Espaço)
2. Vai abrir uma caixa de busca no centro da tela
3. Digite `terminal`
4. Aperte `Enter`
5. ✅ Janela preta com texto branco abre — esse é o Terminal

**Opção B — Launchpad:**

1. Clique no Launchpad (ícone do foguete na barra inferior)
2. Procure pela pasta "Outros" ou "Utilitários"
3. Clique em "Terminal"

> 💡 **Dica:** depois de abrir uma vez, clique com botão direito no ícone do Terminal na barra inferior e escolha "Manter no Dock". Da próxima vez é 1 clique.

### 19.2 No Windows

> ⚠️ **Importante:** este sistema funciona melhor em **Mac ou Linux**. No Windows, você precisa instalar o **WSL2 (Windows Subsystem for Linux)** primeiro. Sem WSL, o Playwright pode dar problema.

**Instalar WSL2 (1 vez só):**

1. Aperte tecla `Windows` no teclado, digite `cmd`
2. Clique com botão direito em "Prompt de Comando" → "Executar como administrador"
3. Cole o comando:

   ```text
   wsl --install
   ```

4. Aperte Enter
5. Reinicie o computador quando ele pedir
6. Ao reiniciar, vai abrir uma janela do Ubuntu pedindo pra criar usuário
7. Crie um usuário e senha (anote!)
8. ✅ Ubuntu instalado dentro do Windows

**Abrir o Terminal (WSL Ubuntu):**

1. Aperte tecla `Windows`
2. Digite `ubuntu`
3. Clique no "Ubuntu" que aparece
4. ✅ Terminal aberto

A partir daqui, siga este guia como se fosse um sistema Linux.

### 19.3 No Linux

1. Geralmente está em `Atividades` → `Terminal`
2. Ou aperte `Ctrl + Alt + T` na maioria das distros (Ubuntu, Mint, Pop!_OS)
3. ✅ Pronto

### 19.4 Como confirmar que abriu

Você verá uma janela escura (geralmente fundo preto/branco) com algo como:

```text
seu-nome-de-usuario@nome-do-computador ~ %
```

Ou:

```text
seu-usuario@maquina:~$
```

O `%` ou `$` no final é onde você digita os comandos. Não digite o `%` nem o `$` — só o comando depois.

> 💡 **Dica de copiar/colar no Terminal:**
> - **Mac:** `Cmd + C` pra copiar, `Cmd + V` pra colar
> - **Windows (WSL):** `Ctrl + Shift + C` / `Ctrl + Shift + V`
> - **Linux:** `Ctrl + Shift + C` / `Ctrl + Shift + V`

---

## 20. Receber o projeto

### 20.1 Como você vai receber

Você vai receber a pasta `trading-terminal` em formato `.zip`, geralmente:

- Link de download enviado pelo professor
- Pendrive entregue na aula
- Drive compartilhado

### 20.2 Onde colocar (CRÍTICO)

> ⚠️ **A pasta DEVE ficar no caminho exato `~/Documents/trading-terminal`** (a `~` significa "sua pasta de usuário"). Alguns scripts esperam essa localização.

**No Mac:**

1. Vá em Finder → Downloads
2. Localize `trading-terminal.zip`
3. Clique 2x — Mac descompacta automaticamente
4. Aparece pasta `trading-terminal`
5. Arraste essa pasta pra `Documents` (na barra lateral do Finder)

**Confirmar no Terminal:**

```bash
cd ~/Documents/trading-terminal
ls
```

Deve listar arquivos: `live_daemon.py`, `codigo31_supervisor.py`, `run_codigo31.sh`, pasta `src/`, etc.

> 🛑 **Se aparecer `No such file or directory`:** a pasta não está no lugar certo. Volte ao Finder e mova manualmente pra `~/Documents/`.

**No Windows (WSL):**

```bash
# A pasta do Windows é montada no /mnt/c/... no WSL
mkdir -p ~/Documents
cp -r /mnt/c/Users/SEU_USUARIO_WINDOWS/Downloads/trading-terminal ~/Documents/
cd ~/Documents/trading-terminal
ls
```

Substitua `SEU_USUARIO_WINDOWS` pelo seu nome de usuário do Windows.

### 20.3 Estrutura básica (rápida explicação)

Você não precisa decorar isto. Só pra contexto:

| Pasta/Arquivo | O que faz |
|---|---|
| `live_daemon.py` | O coração do sistema |
| `codigo31_supervisor.py` | Reinicia se travar |
| `run_codigo31.sh` | Comando único pra iniciar |
| `src/` | Código interno (NÃO MEXA) |
| `config/` | Onde VOCÊ vai editar (ligas premium) |
| `logs/` | Logs (criado automaticamente) |
| `tests/` | Testes automáticos |
| `.env` | **Você vai criar** com suas credenciais |

---

## 21. Instalar Python

### 21.1 Verificar se já tem

No Terminal:

```bash
python3 --version
```

- Apareceu `Python 3.9.X`, `3.10.X`, `3.11.X` ou `3.12.X` → ✅ tem. Pule para a Aula 22.
- Apareceu `command not found` ou `Python 2.X.X` → continue.

### 21.2 Instalar no Mac (via Homebrew)

**Passo 1 — Instalar Homebrew** (gerenciador de pacotes do Mac, 1 vez só):

Cole no Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Aperte Enter. Vai pedir sua senha do Mac (a mesma de quando você loga). Ao digitar, **NÃO aparece nada na tela** — é normal. Digite e aperte Enter.

Aguarde 5-10 minutos. Quando voltar pro prompt (`%`), Homebrew está instalado.

**Passo 2 — Instalar Python:**

```bash
brew install python@3.11
```

Aguarde 2-5 minutos.

**Passo 3 — Confirmar:**

```bash
python3 --version
```

Deve aparecer `Python 3.11.X`. ✅

### 21.3 Instalar no Linux/WSL

```bash
sudo apt update
sudo apt install python3 python3-pip -y
python3 --version
```

Pede sua senha (a mesma de quando criou o usuário do Ubuntu/Linux).

### 21.4 Confirmar pip (gerenciador de pacotes do Python)

```bash
pip3 --version
```

Deve aparecer algo como `pip 23.X` ou similar.

> 🛑 **Se aparecer erro no pip:** no Mac, rode `python3 -m ensurepip --upgrade`. No Linux, `sudo apt install python3-pip -y`.

---

## 22. Criar bot do Telegram

Aqui você cria um **bot pessoal** no Telegram pra receber os alertas. Leva 5 minutos.

### 22.1 Abrir o BotFather

1. Abra o Telegram (no celular ou no computador)
2. Na busca do Telegram (lupa), digite: `@BotFather`
3. Toque no resultado oficial (tem ✓ azul de verificação) — chama "BotFather"
4. Aperte `/start` ou "Iniciar" no fim da tela

### 22.2 Criar o bot

Mande a mensagem:

```text
/newbot
```

Ele vai perguntar:

**Pergunta 1 — Nome do bot** (display, qualquer coisa em português é OK):

Mande:

```text
Meu Codigo 3:1
```

**Pergunta 2 — Username** (precisa terminar em `bot`, sem espaços, único no Telegram inteiro):

Tente:

```text
meu_codigo_31_bot
```

Se ele responder "Sorry, this username is already taken", tente outras combinações com seu nome ou números, ex.: `joao_codigo31_bot`, `codigo31_silva_bot`, etc.

### 22.3 Anotar o TOKEN

Após criar, BotFather manda algo como:

```text
Done! Congratulations on your new bot...

Use this token to access the HTTP API:
1234567890:AAEvxXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

Keep your token secure...
```

> 📝 **ANOTE ESSE TOKEN** (toda a parte depois de "Use this token to access..." até o final da linha). Você vai usar daqui a pouco.
>
> ⚠️ NUNCA compartilhe esse token com ninguém. Quem tem o token controla seu bot.

### 22.4 Descobrir seu CHAT_ID

Agora você precisa do seu chat_id pessoal — pra onde os alertas vão chegar.

1. No Telegram, busque por: `@userinfobot`
2. Toque no resultado oficial
3. Aperte `/start` ou "Iniciar"
4. Ele responde com algo como:

```text
👤 You
Id: 123456789
First: Joao
Username: @joaosilva
```

> 📝 **ANOTE O `Id`** (no exemplo: `123456789`). É o seu chat_id.

### 22.5 Iniciar conversa com seu bot (CRÍTICO)

> ⚠️ **MUITO IMPORTANTE:** o bot só consegue te mandar mensagem DEPOIS que você falar com ele uma vez. Se você pular esse passo, NENHUM alerta vai chegar.

1. No Telegram, busque pelo seu bot (use o username que você escolheu, ex: `@meu_codigo_31_bot`)
2. Toque nele
3. Aperte `/start` ou "Iniciar"
4. Mande qualquer mensagem, ex.: `oi`

✅ Bot pronto.

---

## 23. Instalar dependências

### 23.1 Entrar na pasta do projeto

```bash
cd ~/Documents/trading-terminal
pwd
```

A linha mostrada deve terminar em `/trading-terminal`. ✅

### 23.2 Instalar Playwright (controla o navegador)

```bash
pip3 install --user playwright
```

Aguarde 1-3 minutos. Você verá várias linhas de instalação. Quando voltar pro prompt, terminou.

> 🛑 **No macOS novo (Sonoma/Sequoia)**, se aparecer `error: externally-managed-environment`, use:
>
> ```bash
> pip3 install --break-system-packages playwright
> ```

### 23.3 Baixar o navegador Chromium

```bash
python3 -m playwright install chromium
```

Aguarde 3-5 minutos (baixa ~150 MB).

### 23.4 Confirmar instalação

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

Deve imprimir `Playwright OK`. ✅

---

## 24. Configurar credenciais (.env)

Aqui você guarda token e chat_id. Esse arquivo **fica só no seu computador**.

### 24.1 Criar o arquivo

```bash
cd ~/Documents/trading-terminal
nano .env
```

`nano` é um editor de texto dentro do Terminal. Abre uma tela com a parte de baixo mostrando comandos `^O Save`, `^X Exit`, etc. (o `^` significa `Ctrl`.)

### 24.2 Colar o conteúdo

Copie este modelo:

```text
export TELEGRAM_BOT_TOKEN="COLE_SEU_TOKEN_AQUI"
export TELEGRAM_CHAT_ID="COLE_SEU_CHAT_ID_AQUI"
```

E substitua:

- `COLE_SEU_TOKEN_AQUI` → o token que você anotou na Aula 22.3
- `COLE_SEU_CHAT_ID_AQUI` → o chat_id que você anotou na Aula 22.4

Exemplo final (com valores fictícios):

```text
export TELEGRAM_BOT_TOKEN="1234567890:AAEvxAbCdEfGhIjKlMnOpQrStUvWxYz123"
export TELEGRAM_CHAT_ID="123456789"
```

> ⚠️ As **aspas duplas são obrigatórias**. Se você escreveu sem aspas, vai dar erro depois.

### 24.3 Salvar e sair do nano

- `Ctrl + O` (salvar) → aparece `File Name to Write: .env` → aperte `Enter`
- `Ctrl + X` (sair)

### 24.4 Confirmar que ficou certo

```bash
cat .env
```

Deve aparecer o conteúdo que você colou (com seus valores). ✅

### 24.5 Proteger o arquivo

```bash
chmod 600 .env
```

Agora só você consegue ler esse arquivo no seu computador. ✅

> 🛑 **Erro comum:** copiar do PDF/Word com aspas curvas (`"..."` em vez de `"..."`). Use sempre **aspas retas**. Se copiou de algum lugar formatado, digite as aspas à mão no `nano`.

---

## 25. Adicionar suas ligas (opcional)

O projeto já vem com **Brasileirão Série A e B + ligas europeias + Libertadores/Sul-Americana** configuradas. Pule pra Aula 26 se isso te atende.

### 25.1 Quando você precisa editar

- Quer cobrir uma liga menor (ex: Série C, Série D)
- Quer adicionar um time que falta (ex: time que subiu de divisão)
- Quer cobrir uma liga internacional específica

### 25.2 Abrir o config

```bash
cd ~/Documents/trading-terminal
nano config/premium_competitions.json
```

### 25.3 Adicionar um time

Procure a seção `"brasileirao_serie_a"` (use `Ctrl + W` no nano pra buscar texto).

Adicione o slug do novo time na lista, com vírgula:

```json
"brasileirao_serie_a": [
  "atletico-mg", "athletico-pr", ...
  "vitoria", "america-mg", "nautico"
],
```

> ⚠️ Atenção à vírgula: cada item tem vírgula DEPOIS, exceto o último.

### 25.4 Como descobrir o slug correto

1. Vá em https://www.flashscore.com.br
2. Procure o time (lupa)
3. Olhe a URL no navegador
4. O slug é o nome do time na URL, antes do hífen e do ID

Exemplo, URL do Náutico:

```text
https://www.flashscore.com.br/equipe/nautico/XXXXXXXX/
                                   ^^^^^^^
                                   esse é o slug
```

### 25.5 Salvar

- `Ctrl + O` → Enter → `Ctrl + X`

### 25.6 Validar que o JSON ficou correto

```bash
python3 -c "import json; json.load(open('config/premium_competitions.json')); print('JSON OK')"
```

- `JSON OK` → ✅
- `JSONDecodeError` → erro de vírgula/aspas, refaça e tente de novo

---

## 26. Primeira execução (teste)

### 26.1 Rodar 1 ciclo só

```bash
cd ~/Documents/trading-terminal
source .env
python3 live_daemon.py --send-telegram --use-watchlist --mode codigo_3_1 --once
```

`source .env` carrega seu token. `--once` faz rodar só 1 ciclo (≈ 2 min) e parar.

### 26.2 O que esperar no terminal

```text
╔══════════════════════════════════════════════╗
║  O CÓDIGO 3:1 — Terminal de Chances Claras  ║
║  Modo: ALERTA POR CHANCES CLARAS            ║
╚══════════════════════════════════════════════╝

  Agente: codigo_3_1
  Scan-alvo: 120s
  Telegram: PRONTO        ← tem que aparecer PRONTO
  ...

🔭 DISCOVERY — HH:MM:SS — Buscando jogos ao vivo...
🔍 N jogos descobertos

🏆 PREMIUM A — PRIORIDADE MÁXIMA
   - Brasileirão Betano | Brasil | live=X | watchlist=X ...

SCAN #1 — HH:MM:SS — Watchlist: 15 jogos
  ⚽ Time A 1-0 Time B | 2T min 56
     CC: 3x1 | Total=4 | Rate=14.0
     ...
```

### 26.3 Confirmar que está OK

✅ Apareceu `Telegram: PRONTO` (não OFF, não ERRO)
✅ Apareceu `DISCOVERY` com N jogos descobertos
✅ Apareceu pelo menos 1 jogo escaneado com `⚽`

Se algum jogo bateu a regra durante o ciclo, você recebe Telegram. Se não bateu, tudo bem — significa que naquele momento nenhum jogo tinha "gol devendo".

> 🛑 **Se aparecer `Telegram: OFF`:** o `.env` não está carregado. Rode `source .env` de novo na mesma janela e tente novamente.

---

## 27. Rodar 24/7 com o supervisor

### 27.1 Tornar o script executável (1 vez só)

```bash
cd ~/Documents/trading-terminal
chmod +x run_codigo31.sh
```

### 27.2 Iniciar o supervisor

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

[supervisor] supervisor_started
[supervisor] started_daemon  {'pid': XXXXX, ...}

  (DEPOIS DE ~10s, abre o terminal normal do CÓDIGO 3:1)
```

### 27.3 Deixar essa janela aberta

> ⚠️ **CRÍTICO:** a janela do Terminal precisa ficar **aberta** pra o sistema rodar. Se fechar a janela, o sistema para.

**Pode:**

- ✅ Minimizar a janela
- ✅ Mudar pra outras telas no computador
- ✅ Deixar o computador travado/tela apagada
- ✅ Tampa do laptop fechada? **DEPENDE** — veja 27.4 abaixo

**NÃO PODE:**

- ❌ Fechar a janela (mata o sistema)
- ❌ Desligar/reiniciar o computador
- ❌ Suspender (sleep) o computador

### 27.4 Evitar que o Mac/Notebook entre em sleep

O sistema já chama `caffeinate` no Mac automaticamente (impede sleep). Mas confirme:

**No Mac:**

- Vá em `Ajustes do Sistema → Bateria → Configurações Avançadas`
- Marque: "Impedir que o computador entre em modo de repouso automaticamente quando o monitor estiver desligado"
- Se for notebook na bateria, mude a config tanto pra "Bateria" quanto "Adaptador de energia"

**No Windows (WSL):**

- `Configurações → Sistema → Energia e Bateria`
- "Tela e modo de suspensão" → todas as opções pra "Nunca" (quando conectado)

**No Linux:**

- Geralmente `Configurações → Energia → Suspensão automática`

### 27.5 Como saber que está rodando

A cada ~2 minutos, o terminal mostra:

```text
🔭 DISCOVERY — HH:MM:SS
🔍 N jogos descobertos
🏆 PREMIUM A — ...
SCAN #N — Watchlist: 15 jogos
⚽ Jogo 1 — ...
⚽ Jogo 2 — ...
   ⏳ Dormindo XXs (Ctrl+C para parar)
```

Quando algum jogo bate a regra:

```text
Status 3.1.2: 📡 WATCH 3.1.2 — RADAR DE GOL
✅ Telegram enviado (RADAR)
```

E no celular: notificação do Telegram. ✅

\newpage

# PARTE 5 — OPERAÇÃO CONTÍNUA

## 28. Validar funcionamento

### Comando 1 — Buscar jogo específico

```bash
cd ~/Documents/trading-terminal
python3 live_daemon.py --find-game corinthians atletico-mg
```

Mostra estado completo de um jogo no catálogo: se está na watchlist, qual nível premium, qual liga.

### Comando 2 — Ver heartbeat (saúde do sistema)

```bash
cat logs/heartbeat.json
```

Procure por:

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

## 29. Parar, reiniciar

### Como PARAR

Na janela do supervisor, aperte:

```text
Ctrl + C
```

Espere 3-5 segundos. Vai aparecer:

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

- Sempre que editar `config/premium_competitions.json`
- Sempre que editar `.env`
- 1× por semana pra estado limpo
- Se ficar mais de 10 min sem aparecer nada novo no terminal

---

## 30. Manutenção semanal

1× por semana, faça:

### Verificar tamanho dos logs

```bash
cd ~/Documents/trading-terminal
du -sh logs/
```

Se passar de 1 GB, arquive os antigos:

```bash
mkdir -p logs/archive
mv logs/live_daemon_decisions.jsonl logs/archive/decisions_$(date +%Y%m%d).jsonl
```

E reinicie o supervisor.

### Verificar que tudo funciona

```bash
python3 live_daemon.py --find-game corinthians atletico-mg
```

Se mostrar info do jogo (mesmo que esteja "finished"), tudo OK.

---

## 31. Troubleshooting

### Sintoma: nenhum Telegram chegou em 2h

**Possíveis causas:**

1. Bot não foi iniciado (Aula 22.5) — abra Telegram, mande `/start` pro seu bot
2. `.env` está errado — `cat .env` e confira
3. Nenhum jogo bateu a regra — normal em horários de poucos jogos
4. Sistema travou — veja "Sistema travou" abaixo

### Sintoma: aparece "Telegram: OFF" ou "ERRO" no terminal

```bash
# Reaplica .env e testa
cd ~/Documents/trading-terminal
source .env
python3 -c "import os; print('Token:', os.environ.get('TELEGRAM_BOT_TOKEN', 'NAO CARREGADO')[:20])"
```

Se aparecer "NAO CARREGADO", seu `.env` não está sendo lido. Refaça a Aula 24.

### Sintoma: "Sistema travou" — não aparece nada novo há mais de 10 min

```bash
# Mata tudo e reinicia
pkill -f codigo31_supervisor
pkill -f live_daemon
sleep 3
cd ~/Documents/trading-terminal && ./run_codigo31.sh
```

### Sintoma: aparece "JSONDecodeError" ao iniciar

```bash
# Valida o config
python3 -c "import json; json.load(open('config/premium_competitions.json')); print('JSON OK')"
```

Se der erro, você quebrou o arquivo na Aula 25. Abra e corrija (cuidado com vírgulas e aspas).

\newpage

# APÊNDICES

## Apêndice A — Comandos de emergência

### "Está dando erro, quero recomeçar do zero"

```bash
cd ~/Documents/trading-terminal
pkill -f codigo31_supervisor
pkill -f live_daemon
rm -f logs/heartbeat.json
./run_codigo31.sh
```

### "Telegram parou de chegar"

```bash
cd ~/Documents/trading-terminal
cat .env
source .env
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

## Apêndice B — Tabela de erros comuns

| Erro | Causa provável | Solução |
|---|---|---|
| `command not found: python3` | Python não instalado | Aula 21 |
| `ModuleNotFoundError: playwright` | Playwright não instalado | `pip3 install --user playwright` |
| `Telegram: OFF` ou `ERRO` | `.env` não carregado | `source .env` antes de rodar |
| `Permission denied: ./run_codigo31.sh` | Script sem permissão | `chmod +x run_codigo31.sh` |
| `JSONDecodeError` em config | Vírgula/aspas erradas | Refazer Aula 25 |
| Telegram chega vazio | Bot não foi iniciado | Mande `/start` pro seu bot |
| Discovery não acha jogos | Internet caiu | Aguarde 5 min, tente de novo |
| `TargetClosedError` no Ctrl+C | Cosmético | Ignorar — não afeta nada |
| `error: externally-managed-environment` | macOS novo | Use `--break-system-packages` |

---

## Apêndice C — Checklist final

Marque cada item depois de fazer:

- [ ] Python 3.9+ instalado (`python3 --version`)
- [ ] Pasta `trading-terminal` em `~/Documents/`
- [ ] Bot do Telegram criado, token anotado
- [ ] Chat ID anotado (do @userinfobot)
- [ ] Mandei `/start` pro meu bot uma vez
- [ ] Playwright instalado
- [ ] Chromium baixado
- [ ] `.env` criado com token + chat_id
- [ ] `chmod 600 .env` feito
- [ ] `config/premium_competitions.json` revisado, JSON válido
- [ ] `chmod +x run_codigo31.sh` feito
- [ ] Primeira execução com `--once` rodou sem erro
- [ ] Telegram chegou (em algum ciclo)
- [ ] `./run_codigo31.sh` rodando agora
- [ ] `cat logs/heartbeat.json` mostra `status: alive`
- [ ] Sei como parar (Ctrl+C) e reiniciar
- [ ] Configurei o Mac/PC pra não dormir

---

## Apêndice D — FAQ

**P: Quanto tempo o terminal precisa ficar ligado?**
R: 24/7. Cada ciclo dura ~2 min.

**P: Posso rodar em Mac antigo?**
R: Sim. Consumo é baixo (~500MB RAM, 5-10% CPU). Funciona em Mac de 2015+.

**P: Posso rodar em VPS?**
R: Sim, mas este guia cobre só máquina local.

**P: O sistema cobre jogos de séries menores?**
R: Depende do que está em `config/premium_competitions.json`.

**P: O Telegram tem limite de mensagens?**
R: ~30 msgs/s pra bots. O terminal manda muito menos.

**P: Posso ter mais de um bot?**
R: Sim, mas o sistema só usa 1 por vez (via `.env`).

**P: O sistema "aposta sozinho"?**
R: **Não.** Ele só MONITORA e ALERTA. Toda decisão é sua.

**P: Posso modificar a Regra 3.1.2.0?**
R: Não recomendado. A regra foi calibrada com base em 3.000 jogos. Mudanças quebram a integridade.

---

## Apêndice E — Glossário

| Termo | Significado |
|---|---|
| CC | Chance Clara (Big Chance no Flashscore) |
| BC | Big Chance (alias) |
| xG | Expected goals (gols esperados) |
| xGOT | Expected goals on target |
| rate | `minute / total_cc` — quanto MENOR, melhor |
| placar_abaixo_producao | `total_goals < total_cc // 3` |
| dominant_team | Time com mais BC no momento |
| dom_lead | `dominant_score - opp_score` — ≥ 2 bloqueia BACK |
| bucket | `cc // 3` — usado pra anti-spam de Telegram |
| Tier 0/0.5/1/2/3 | Camadas de prioridade da watchlist |
| Premium A/B/C | Hierarquia de cobertura premium |
| highlighted | Liga com estrela amarela no Flashscore |
| fingerprint | `home_id_away_id` — dedup canônico |
| cobertura passiva | Premium visível mas não escaneado neste ciclo |
| stale | TTL ativo de leitura inválida |
| no_stats_backoff | TTL exponencial após scan sem stats |

---

## Encerramento

Este manual é a **fonte única de verdade** do Código 3:1 — Regra 3.1.2.0.

**Próximos passos:**

1. Deixe o sistema rodar 24h
2. Observe o volume de alertas que chegam
3. Cruze os alertas com os resultados finais dos jogos
4. Refine sua leitura: WATCH é radar, FORTE é operacional, PREMIUM é prioridade alta

**Lembre-se:** o sistema é um RADAR ESTATÍSTICO. A decisão de operar é sempre sua.

---

**O PATRIMÔNIO — Ativos Digitais**

*Produtos | Sistemas | Funcionários Digitais*

Manual Completo — Edição 2026
