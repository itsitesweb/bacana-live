---
title: "O Código 3:1 — Regra 3.1.2.0"
subtitle: "Terminal de Chances Claras — Dossiê Oficial v2.0"
author: "Trading Terminal — Edição Curso"
date: "25 de maio de 2026"
---

# O Código 3:1 — Regra 3.1.2.0

## Terminal de Chances Claras

**Dossiê Oficial — Versão 2.0**

---

### Sobre este documento

| Campo | Valor |
|---|---|
| Versão | 2.0 — REGRA 3.1.2.0 |
| Lançamento da v2.0 | 12 de maio de 2025 |
| Em operação contínua há | 12 meses |
| Edição deste material | 25 de maio de 2026 |
| Status | Operacional em produção |
| Cobertura | Documento auditável completo |
| Suite de testes | 372 testes / 0 falhas |
| Versões anteriores | v1.0 e v1.1 arquivadas em `docs/archive/` |

### Como ler este documento

Este material é estruturado para leitura **sequencial em aula** ou consulta pontual. Cada capítulo é independente; a Parte I cobre conceito, a Parte II cobre a regra, a Parte III cobre arquitetura, a Parte IV cobre operação.

| Símbolo | Significado |
|---|---|
| 📡 | WATCH — radar inicial, ainda não é entrada |
| 🟠 | FORTE — sinal operacional confiável |
| 🟢 | PREMIUM — sinal de alta prioridade |
| 🏆 | Premium A — liga de elite |
| 🥈 | Premium B — cobertura secundária |
| 🧩 | Premium C — fallback por time grande |
| 📋 | Cobertura passiva — visível mas não escaneado |
| ⚽ | Display por jogo no terminal |

\newpage

## Sumário

**Parte I — Fundamentos**

1. Tese central
2. Histórico das versões
3. Base estatística (3.000 jogos)

**Parte II — A Regra 3.1.2.0**

4. Visão geral
5. Os 8 níveis de alerta
6. Prioridade entre alertas
7. Anti-spam por bucket
8. Política de Telegram (WATCH = radar)
9. Textos oficiais Telegram

**Parte III — Arquitetura operacional**

10. Display no terminal
11. Cobertura premium (A/B/C)
12. Watchlist (5 tiers)
13. Anti-saturação
14. Deduplicação canônica
15. Discovery (walker DOM)
16. Supervisor e watchdog
17. Heartbeat
18. Logs JSONL

**Parte IV — Operação**

19. Comandos CLI
20. Procedimento de restart
21. Suite de testes
22. Arquivos da arquitetura
23. Glossário
24. Changelog
25. Apêndice — exemplos reais

\newpage

# PARTE I — FUNDAMENTOS

## 1. Tese central

> **Em ligas profissionais de futebol, uma chance clara (Big Chance) produz, em média, um gol a cada ~1,65 — mas O Código 3:1 usa o divisor 3 como gatilho operacional CONSERVADOR de "gol devendo".**

### O que é Big Chance

**Big Chance** (CC, Chance Clara) é uma estatística do Flashscore: oportunidade em que o jogador, no fluxo natural do jogo, deveria ter convertido em gol — finalização de alta probabilidade dentro da área, frente a frente com o goleiro, etc.

### Por que o divisor 3 e não 1,65 (que é o real)?

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
| v1.1 | 15/06/2024 | Header novo, defaults 120 s/120 s, heartbeat estrutural, watchdog externo, filtro `is_live_match`, faxina anti-saturação |
| **v2.0** | **12/05/2025** | **REGRA 3.1.2.0** — 8 níveis (WATCH/FORTE/PREMIUM OVER + BACK + BILATERAL + PREMIUM xG), Telegram com motivo/leitura, anti-spam que respeita WATCH, sistema Tier 0.5 premium hierárquico A/B/C, cobertura passiva, walker DOM, deduplicação canônica |

### O que foi preservado intacto

**NÃO mexer** (módulos críticos do sistema):

- Supervisor externo (`codigo31_supervisor.py`)
- Radar13 (agente paralelo, `radar13/`)
- Motor V1.2 dormente (`src/decision_engine.py`, pronto para rollback)
- Telegram estrutural (`src/telegram_client.py`)
- Discovery (`src/discovery.py`)
- Watchlist (`src/watchlist.py`)
- Scraping (`src/flashscore_adapter.py`)
- Projeto histórico (`historical/`)

---

## 3. Base estatística — 3.000 jogos premium

### Origem dos dados

Coletados via `historical/historical_flashscore_collector.py` em **15 ligas premium**:

- Premier League, La Liga, Bundesliga, Serie A, Ligue 1
- Brasileirão Série A
- MLS, Eredivisie, Primeira Liga
- Champions League, Europa League, Conference League
- Copa Libertadores, Copa Sul-Americana

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

### Jogos que disparariam o gatilho, por divisor

| Divisor | Jogos com gol devendo |
|---|---:|
| CC/2,0 | 20,1 % |
| CC/2,5 | 9,2 % |
| **CC/3,0** (atual) | **5,4 %** |
| CC/3,5 | 2,6 % |

A Regra 3.1.2.0 mantém CC/3 como base e adiciona **níveis** (WATCH ≤ 15 rate, FORTE/PREMIUM ≤ 12 rate, BILATERAL 3×3+) que refinam ainda mais a seleção.

\newpage

# PARTE II — A REGRA 3.1.2.0

## 4. Visão geral

Evolução da regra original em **8 níveis operacionais**, organizados em 3 famílias:

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

### Regra fundamental

> Por scan, **só 1 alerta dispara por jogo** — o de maior prioridade entre todos que casaram.

### Variáveis derivadas a cada scan

```text
total_cc          = home_bc + away_bc
total_goals       = home_score + away_score
cc_rate           = minute / total_cc        (∞ se cc = 0)
expected_over     = total_cc // 3             (piso de gol)
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

### 5.1 📡 WATCH OVER (`over_watch`) — prioridade 7

```text
total_cc        >= 3
cc_rate         <= 15
placar_abaixo   == True
```

> Bucket = `total_cc // 3`. Equivale à regra original v1.0.

### 5.2 📡 WATCH BACK (`back_watch`) — prioridade 8

```text
dominant_team   != None
dom_lead        < 2            (bloqueio universal BACK)
dom_cc          >= 3
opp_cc          <= 1
cc_diff         >= 3
dominant_score  < expected_back
```

> Bucket = `expected_back`.

### 5.3 🟠 FORTE OVER (`over_forte`) — prioridade 5

```text
total_cc        >= 4
cc_rate         <= 12          (mais qualificado que WATCH)
placar_abaixo   == True
```

> Bucket = `expected_over`.

### 5.4 🟠 FORTE BACK (`back_forte`) — prioridade 6

```text
dom_lead        < 2
dom_cc          >= 4
opp_cc          <= 1
cc_diff         >= 4
dominant_score  < expected_back
```

> Bucket = `expected_back`.

### 5.5 🟢 PREMIUM OVER (`over_premium`) — prioridade 3

```text
total_cc        >= 6
cc_rate         <= 12
placar_abaixo   == True
```

> Bucket = `expected_over`.

### 5.6 🟢 PREMIUM BACK (`back_premium`) — prioridade 4

```text
dom_lead        < 2
dom_cc          >= 6
opp_cc          == 0           (zero CC do adversário)
cc_diff         >= 6
dominant_score  < expected_back
```

> Bucket = `expected_back`.

### 5.7 🟢 PREMIUM OVER xG (`over_premium_xg`) — prioridade 2

```text
total_cc        >= 6
cc_rate         <= 12
placar_abaixo   == True
total_xg        >= 2.5         (xG confirma CC)
```

> Bucket = `expected_over`. **Duas métricas independentes confirmam** — sinal máximo de Over.

### 5.8 🟢 PREMIUM OVER BILATERAL PESADO (`over_bilateral_premium`) — prioridade 1

```text
home_bc         >= 3
away_bc         >= 3
total_cc        >= 6
placar_abaixo   == True
```

> Bucket = `expected_over`. **Sem critério de rate** — jogo bilateral 3×3+ é sinal forte por si só.

---

## 6. Prioridade entre alertas

A função `evaluate_codigo_3_1(match_state, previous_alert_state)` em `src/codigo_3_1.py` avalia TODOS os 8 padrões em paralelo. Se mais de um casar, **prevalece o de menor prioridade numérica** (1 = mais forte):

| Prio | alert_type | Emoji | Label |
|---:|---|:---:|---|
| 1 | `over_bilateral_premium` | 🟢 | PREMIUM 3.1.2 — OVER BILATERAL PESADO |
| 2 | `over_premium_xg` | 🟢 | PREMIUM 3.1.2 — CC + xG CONFIRMADOS |
| 3 | `over_premium` | 🟢 | PREMIUM 3.1.2 — GOL MUITO DEVENDO |
| 4 | `back_premium` | 🟢 | PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO |
| 5 | `over_forte` | 🟠 | FORTE 3.1.2 — GOL DEVENDO |
| 6 | `back_forte` | 🟠 | FORTE 3.1.2 — BACK DOMINANTE |
| 7 | `over_watch` | 📡 | WATCH 3.1.2 — RADAR DE GOL |
| 8 | `back_watch` | 📡 | WATCH 3.1.2 — RADAR DE BACK DOMINANTE |

### Constantes do código

```python
ALERT_OVER_BILATERAL_PREMIUM = "over_bilateral_premium"   # prio 1
ALERT_OVER_PREMIUM_XG        = "over_premium_xg"          # prio 2
ALERT_OVER_PREMIUM           = "over_premium"             # prio 3
ALERT_BACK_PREMIUM           = "back_premium"             # prio 4
ALERT_OVER_FORTE             = "over_forte"               # prio 5
ALERT_BACK_FORTE             = "back_forte"               # prio 6
ALERT_OVER_WATCH             = "over_watch"               # prio 7
ALERT_BACK_WATCH             = "back_watch"               # prio 8
```

---

## 7. Anti-spam por bucket

### O que é bucket

| Mercado | Definição | State persistido |
|---|---|---|
| OVER | `bucket_over = total_cc // 3` | `main_bucket_last` |
| BACK | `bucket_back = dom_cc // 3` | `unilateral_bucket_last` |

Persistência em `logs/live_daemon_state.json`:

```json
{
  "FS_xxx": {
    "codigo_3_1": {
      "main_bucket_last": 2,
      "unilateral_bucket_last": 0
    }
  }
}
```

### Regra de gatilho

> **Alerta só dispara se `bucket_atual > bucket_last`.**
> Se bate condição mas bucket ≤ last → `filter_reason = "bucket_already_sent"`.

### Exceção crítica: WATCH não consome bucket

WATCH OVER e WATCH BACK **enviam Telegram** mas **NÃO atualizam** `main_bucket_last` / `unilateral_bucket_last`. Isso garante que:

- Jogo passou WATCH no bucket 1 → Telegram radar
- Mesmo jogo evolui pra FORTE bucket 1 → Telegram operacional dispara também
- Não há "engasgo" entre níveis

---

## 8. Política de Telegram — WATCH = radar

| Nível | Telegram | Consome bucket | Linguagem |
|---|:-:|:-:|---|
| 📡 WATCH OVER | **SIM** | **NÃO** | Radar — "não é entrada automática" |
| 📡 WATCH BACK | **SIM** | **NÃO** | Radar — idem |
| 🟠 FORTE OVER | SIM | SIM | Operacional — "avaliar entrada" |
| 🟠 FORTE BACK | SIM | SIM | Operacional — Back dominante |
| 🟢 PREMIUM OVER | SIM | SIM | "prioridade alta para análise" |
| 🟢 PREMIUM BACK | SIM | SIM | "reação do dominante" |
| 🟢 PREMIUM OVER xG | SIM | SIM | "prioridade máxima — 2 métricas" |
| 🟢 BILATERAL PESADO | SIM | SIM | "padrão Over/BTTS — não é Back" |

### Como funciona no código

A função `send_alert(tg, decision)` envia para todos os tipos. A função `update_state_after_alert(state, decision)` só grava bucket se `alert_type NOT IN {over_watch, back_watch}` — implementado via `is_watch_only()` em `src/codigo_3_1.py`.

```python
WATCH_ONLY_ALERTS = frozenset({ALERT_OVER_WATCH, ALERT_BACK_WATCH})
is_watch_only(alert_type) -> bool
is_telegram_eligible(alert_type) -> bool   # True pra todos
```

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

> **Garantia:** Nenhuma mensagem contém termos do Motor V1.2 (`ENTER_OVER`, `EXIT_OVER`, `REDUCE`, `LOCK_PROFIT`, `HOLD`, `MANUAL_REVIEW`). Testes `test_TG11` e `test_20` validam.

\newpage

# PARTE III — ARQUITETURA OPERACIONAL

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
   - MLS | Estados Unidos | live=1 | watchlist=1 | passiva=0 | sem_stats=0

🥈 PREMIUM B — COBERTURA SECUNDÁRIA
   - MLS Next Pro | Estados Unidos | live=2 | watchlist=1 | passiva=1 | sem_stats=0

🧩 PREMIUM C — FALLBACK POR TIME/SLUG
   - FS_xxx | min=45 1-1 | watchlist

📋 COBERTURA PREMIUM PASSIVA (2)
   - [B] FS_yyy | MLS Next Pro | min=30 0-0 | motivo=premium_overflow
```

---

## 11. Cobertura premium (A/B/C)

### 11.1 Detecção em 3 níveis — REGRAS A > B > C

A função `classify_premium(url, league_name, league_country, league_css_classes)` em `src/premium_leagues.py` aplica três regras em ordem de prioridade:

| Prioridade | Regra | `reason` | Como detectar |
|---|---|---|---|
| A | CSS do header destacada | `flashscore_highlighted_league` | `headerLeague--has-star` ou `wcl-pinned_dRFvU` (estrela amarela do Flashscore) |
| B | Nome da liga bate whitelist | `premium_league_name` | substring de `_premium_league_names` no config |
| C | Slug do time bate whitelist | `premium_team_slug` | match na URL `/jogo/futebol/<slug>-<id>/` |
| — | Nenhuma | `""` (REASON_NONE) | não-premium |

### 11.2 Níveis hierárquicos A/B/C/NONE

A função `classify_premium_level(league_name, reason)` determina o nível:

| Nível | Quando | Exemplos |
|---|---|---|
| **A** | Reason A ou B + nome bate `_premium_a_leagues` | Brasileirão Betano, Brasileirão Série B, Premier League, La Liga, Bundesliga, Serie A, Ligue 1, MLS, Champions/Europa/Conference, Libertadores, Sul-Americana, Liga Pro Equador |
| **B** | Reason A ou B + nome bate `_premium_b_keywords` OU destacada mas não bate A | MLS Next Pro, NWSL, Brasileirão Feminino, Brasileirão Série D, Primera B Nacional, Intermedia |
| **C** | Reason `premium_team_slug` (sem liga detectada) | Jogo pegou só por time grande |
| **NONE** | Não-premium | Demais |

> **Ordem da checagem é importante:** keyword B é avaliada ANTES da lista A. Assim "MLS Next Pro" vira B mesmo contendo "mls" (que está em A).

### 11.3 Cobertura passiva — todo premium aparece

Todo premium FORA da watchlist aparece em `📋 COBERTURA PREMIUM PASSIVA` com motivo explícito:

| Motivo | Quando |
|---|---|
| `premium_overflow` | Premium live mas não coube no Tier 0.5 (cap = 8) |
| `no_stats_backoff` | Premium em backoff de stats (não escaneado neste ciclo) |
| `finished` | Marcado como finalizado, TTL ativo |
| `stale` | TTL stale ativo |

> **Garantia operacional:** nenhum premium some sem motivo. Implementado em `Catalog.premium_audit_by_level(wl_set)`.

### 11.4 Walker DOM — como o Flashscore é interpretado

Em `src/discovery.py`, função `_JS_EXTRACT_LEAGUE_META`. Estrutura real do Flashscore:

```text
<div class="sportName soccer">           ← container da lista de jogos
  <div class="headerLeague__wrapper">    ← header da liga A
    <div class="headerLeague__title-text">Brasileirão Betano</div>
    <div class="headerLeague__category">BRASIL:</div>
  </div>
  <div class="event__match"><a href="/jogo/...">  ← jogo A1
  <div class="event__match"><a href="/jogo/...">  ← jogo A2
  <div class="headerLeague__wrapper">    ← header da liga B
  <div class="event__match"><a href="/jogo/...">  ← jogo B1
  ...
```

Algoritmo:

1. Para cada container `[class*="sportName"]`, percorre `children` diretos em ordem documental
2. `currentLeague = null` (inicial)
3. Se filho tem classe `headerLeague__wrapper` → parseia liga e país, atualiza `currentLeague`
4. Se filho tem classe `event__match` → atribui `currentLeague` a todos os `<a>` dentro
5. Marca `star_detected=true` se classes incluem `headerLeague--has-star` ou `wcl-pinned`

Stats exibidos a cada DISCOVERY:

```text
📊 DOM LEAGUE META:
   total_links:                             82
   sportName_containers_found:               4
   headerLeague_wrappers_found:             12
   event_match_children_found:              78
   links_com_current_league_context:        78
   links_com_league_name_extraida:          78
   links_com_country_extraida:              78
   links_com_highlighted_true:              22
   links_fora_de_sportName_container:        4
```

---

## 12. Watchlist (5 tiers)

### 12.1 Os 5 tiers

Em `src/watchlist.py`, função `build_watchlist(catalog, max_size=15, tier3_reserved=3, premium_reserved=8, ...)`:

| Tier | Critério | Slot |
|---|---|---|
| **Tier 0** | `has_open_position=True` ou ENTER recente | Ilimitado, ignora stale/no_stats |
| **Tier 0.5** | `is_premium=True` + janela 0-90 | Cap = 8 (`premium_reserved`) |
| **Tier 1** | `minute` em 20-83 + `bc_sum > 0` | Quota alta |
| **Tier 2** | `minute` em 20-83 + `bc_sum == 0` + `ever_loaded_stats=True` | Quota alta |
| **Tier 3** | Resto (FIFO por `last_scanned_at`) | 3 slots fixos |

### 12.2 Tier 0.5 hierárquico (A > C-stats > B)

Ordenação interna do Tier 0.5 por **rank tuple** (menor = entra primeiro):

| Rank | Combinação |
|---:|---|
| 1 | Premium A com stats |
| 2 | Premium A sem stats |
| 3 | Premium C com stats |
| 4 | Premium B com stats + BC>0 |
| 5 | Premium B com stats |
| 6 | Premium B sem stats |

Tie-break: jogo em janela 1-83 > `last_scanned_at` ASC (FIFO).

> **Garantia operacional (teste W24):** Premium A NUNCA perde slot para Premium B, mesmo sem stats.

### 12.3 Composição da watchlist

```text
max_size               = 15  (slots totais)
premium_reserved       = 8   (Tier 0.5)
tier3_reserved         = 3   (Tier 3)

Ordem de preenchimento:
  1. Tier 0       (todos)
  2. Tier 0.5     (até cap = 8)
  3. Tier 1 + 2   (até quota_high = available - tier3_reserved)
  4. Tier 3       (até tier3_reserved = 3)
  5. Sobras
```

Filtros raiz (excluem em qualquer tier):

- `g["excluded_duplicate"] == True` → skip
- `catalog.is_finished_or_not_live` → skip
- `catalog.is_stale_active` → skip (Tier 1/2/3)
- `catalog.is_no_stats_active` → skip (Tier 1/2/3)

---

## 13. Anti-saturação

Quatro mecanismos protegem o sistema de saturar com jogos ruins:

### 13.1 Stale

`mark_stale()` + `stale_until`. Quando um scan falha em retornar minute/score válidos, marca por TTL (default `--stale-ttl-min=15`). Enquanto ativo, o jogo é pulado pelos tiers 1/2/3.

### 13.2 No-stats backoff

`mark_no_stats()` + `no_stats_until`. Quando o scan retorna `None` (sem stats), incrementa `no_stats_count` e seta TTL exponencial:

```text
1ª falha → 10 min
2ª falha → 20 min
3ª+ falha → 30 min
```

`should_use_short_timeout(mid)` retorna `True` após 1ª falha — o daemon usa timeout reduzido pra não gastar 18 s confirmando o que provavelmente falhará de novo.

### 13.3 Finished or not live

`mark_finished_or_not_live()`. Quando `is_live_match(ms.status_raw)` retorna `False` (FT, FINISHED, SUSPENDED, POSTPONED, CANCELLED, SCHEDULED, AET, PENALTIES), marca por TTL longo (default 12 h). Jogo desaparece até o TTL expirar.

### 13.4 Faxina do catálogo

`prune_stale_entries()` roda a cada ciclo:

```python
catalog.prune_stale_entries(
    not_seen_ttl_minutes=30,    # jogo sumiu do discovery há 30+ min
    finished_ttl_hours=12,      # finalizado há 12 h
)
```

> **Proteção absoluta:** NUNCA remove jogo com `has_open_position=True`.

---

## 14. Deduplicação canônica

### O problema

Flashscore às vezes retorna o mesmo jogo com 2 URLs:

```text
/jogo/futebol/atletico-mg-hGLC5Bah/corinthians-QBGfQbSe          (sem ?mid=)
/jogo/futebol/atletico-mg-hGLC5Bah/corinthians-QBGfQbSe/?mid=A3c2Hc54
```

Cada URL gera `match_id` diferente, mas ambas têm o MESMO **fingerprint** = `home_id_away_id` = `hGLC5Bah_QBGfQbSe`.

### Algoritmo de canonização

Em `src/catalog.py`:

```python
_match_fingerprint(url) → "home_id_away_id"
_is_mid_based(mid)      → True se mid NÃO tem "_" depois de "FS_"

_pick_canonical(entries) — prioridade:
  A) mid-based (URL tem ?mid=...)
  B) last_seen_at mais recente
  C) last_scanned_at mais recente
  D) last_minute maior
  E) ever_loaded_stats = True
  F) URL mais longa
```

### Marcação automática

`Catalog.recompute_duplicates()` roda a cada `upsert_discovered` e a cada `load()`. Marca não-canônicos:

```python
entry["excluded_duplicate"] = True
entry["duplicate_of"] = "<canonical_match_id>"
```

> **Watchlist filtra `excluded_duplicate=True` na raiz:** duplicado NUNCA entra, NÃO consome slot, NÃO gera alerta.

---

## 15. Discovery — walker DOM

`discover_live_games()` em `src/discovery.py`:

1. `page.goto(base_url)` no Flashscore
2. Aceita cookies (privacy-friendly)
3. Aguarda `.filters__tab` e clica em **"AO VIVO"**
4. Executa `_JS_EXPAND_LEAGUES` (clica em expander / "exibir jogos")
5. Coleta todos `a[href*="/jogo/"]`
6. Normaliza URL com hash `#/match-summary/match-statistics/0`
7. Extrai `match_id` via regex (`?mid=` ou par de slugs)
8. Executa `_JS_EXTRACT_LEAGUE_META` (walker DOM hierárquico)
9. Retorna `{games, league_meta, league_stats, league_failures, ...}`

---

## 16. Supervisor e watchdog

### Supervisor externo (`codigo31_supervisor.py`)

Processo pai. Sobe o daemon como filho via `subprocess.Popen` com `os.setsid`. A cada loop:

1. Lê `logs/heartbeat.json`
2. Se `last_scan_at` está `> stale_heartbeat_seconds` atrás (default 600 s = 10 min) → mata grupo de processos (SIGTERM → SIGKILL) e reinicia
3. Se daemon não chega a escrever heartbeat em `startup_timeout_s` (default 420 s = 7 min) → mata e reinicia
4. Rate limit: `max_restarts_per_hour` (default 10)
5. Telegram crítico em cada restart

Comando único de início: `./run_codigo31.sh` (caffeinate + supervisor).

### Self-watchdog (dentro do daemon)

Thread em background. Se não receber `mark_alive()` em 8 min, manda SIGTERM no PID e o supervisor reinicia.

> **Dupla camada:** self-watchdog (interno, rápido) + supervisor externo (lento, robusto).

---

## 17. Heartbeat

`logs/heartbeat.json`, atualizado a cada ciclo:

```json
{
  "status": "alive",
  "terminal_name": "O Código 3:1",
  "mode": "codigo_3_1",
  "last_scan_at": "2026-05-25T...",
  "last_scan_duration_seconds": 56.4,
  "actual_cycle_duration_seconds": 56.4,
  "target_scan_interval_seconds": 120,
  "cycle_over_target": false,
  "scan_delay_seconds": 0,
  "scan_number": 8,
  "total_live_games_discovered": 75,
  "games_with_cc_available": 60,
  "games_scanned": 13,
  "games_skipped_this_cycle": 47,
  "no_stats_backoff_count": 40,
  "games_excluded_finished_or_not_live": 5,
  "premium_live_games_in_watchlist": 8,
  "premium_live_games_scanned_this_cycle": 7,
  "coverage": {
    "total": 76, "in_watchlist": 15,
    "excluded_duplicate": 1, "excluded_finished": 5,
    "excluded_no_stats": 39, "excluded_stale": 0,
    "included_tier0": 0, "included_tier05": 8,
    "included_tier1": 3, "included_tier2": 1, "included_tier3": 3,
    "excluded_tier3_overflow": 9, "excluded_other_overflow": 7
  },
  "telegram_ready": true,
  "telegram_sent_last_cycle": 1,
  "errors_last_cycle": 0
}
```

---

## 18. Logs JSONL

| Arquivo | Conteúdo |
|---|---|
| `logs/live_daemon_decisions.jsonl` | Uma linha por scan: timestamp, match_id, home/away, minute, score, CC, alert_type, bucket, should_alert, telegram_sent, filter_reason |
| `logs/codigo31_supervisor.log` | Eventos do supervisor: started, killed, telegram_critical_sent, rate_limit_hit |
| `logs/live_daemon_catalog.json` | Catálogo persistido — entries com 30+ campos |
| `logs/live_daemon_state.json` | State volátil: anti-spam buckets, posições abertas, cooldowns |

\newpage

# PARTE IV — OPERAÇÃO

## 19. Comandos CLI operacionais

### Iniciar daemon (recomendado)

```bash
cd ~/Documents/trading-terminal && ./run_codigo31.sh
```

### Comandos de debug

```bash
# DEBUG: localiza jogo no catálogo + verdict
python3 live_daemon.py --find-game corinthians atletico-mg

# DEBUG: abre Flashscore real e dumpa DOM
python3 live_daemon.py --debug-dom-game corinthians atletico-mg

# DEBUG: roda walker idêntico ao discovery + stats
python3 live_daemon.py --debug-league-walker corinthians atletico-mg
```

### Outros

```bash
# Modo direto (sem supervisor)
python3 live_daemon.py --send-telegram --use-watchlist --mode codigo_3_1

# Watchdog em terminal separado (opcional)
python3 watchdog.py

# Rollback para Motor V1.2 (dormente)
python3 live_daemon.py --send-telegram --use-watchlist --mode motor_v12
```

---

## 20. Procedimento de restart

```bash
# 1. Ctrl+C na janela do CÓDIGO 3:1 — SUPERVISOR
# 2. Reiniciar:
cd ~/Documents/trading-terminal && ./run_codigo31.sh
```

O supervisor automaticamente:

- Carrega catálogo persistido (migração automática de campos novos via `Catalog.load()`)
- Reaplica `clean_league_name()` em entries antigos
- Reaplica `classify_premium()` em entries sem `premium_level`
- Recalcula `recompute_duplicates()` em todos os fingerprints
- Sobe daemon como filho com PID novo

---

## 21. Suite de testes — 372 testes / 0 falhas

| Suíte | Testes | Cobertura |
|---|---:|---|
| `test_catalog.py` | 20 | upsert, save/load, stale, no_stats, finished, prune, dedup canônico |
| `test_codigo31_supervisor.py` | 25 | Supervisor externo: lifecycle, stale heartbeat, restart, rate limit |
| `test_codigo_3_1.py` | 18 | Legado integração — compatibilidade com regra v1.1 |
| `test_codigo_3_1_v2.py` | 35 | 21 obrigatórios Regra 3.1.2.0 + 14 do log-only WATCH |
| `test_decision_engine.py` | 31 | Motor V1.2 dormente |
| `test_discovery_smoke.py` | 7 | Discovery — smoke tests |
| `test_flashscore_adapter_parser.py` | 9 | Parser do Flashscore |
| `test_heartbeat_watchdog.py` | 16 | Heartbeat estrutural + watchdog independente |
| `test_live_daemon_telegram.py` | 6 | Pipeline Telegram |
| `test_live_filter.py` | 29 | Filtro is_live_match |
| `test_post_over_state.py` | 10 | Estado pós-Over (sentinela 999) |
| `test_premium_leagues.py` | 46 | 16 limpeza + 14 níveis A/B/C + 16 classify |
| `test_self_watchdog.py` | 7 | Self-watchdog interno |
| `test_telegram_filters.py` | 30 | Filtros estruturais de mensagens |
| `test_watchlist.py` | 28 | 5 tiers + W23-W25 hierarquia premium A>B |
| `historical/tests/test_discover_finished.py` | 39 | Discovery histórico |
| `historical/tests/test_historical_collector.py` | 16 | Coletor histórico |
| **TOTAL** | **372** | **0 falhas** |

---

## 22. Arquivos da arquitetura

### Núcleo da regra

- `src/codigo_3_1.py` — regra 3.1.2.0, formatters Telegram, helpers de state
- `src/models.py` — `MatchState`

### Coleta e catalogação

- `src/discovery.py` — discovery Flashscore + walker DOM
- `src/flashscore_adapter.py` — Playwright reader (preservado)
- `src/catalog.py` — catálogo persistido + dedup + audit

### Seleção e priorização

- `src/watchlist.py` — 5 tiers + Tier 0.5 hierárquico
- `src/premium_leagues.py` — `classify_premium()`, `clean_league_name()`, levels A/B/C

### Loop operacional

- `live_daemon.py` — main loop, display, `--find-game`, `--debug-dom-game`, `--debug-league-walker`
- `codigo31_supervisor.py` — supervisor externo
- `run_codigo31.sh` — wrapper de início (caffeinate + supervisor)
- `watchdog.py` — watchdog independente (opcional)

### Configuração

- `config/premium_competitions.json` — slugs, `_premium_league_names`, `_premium_a_leagues`, `_premium_b_keywords`, `_highlighted_css_patterns`
- `.env` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### Componentes preservados (NÃO mexer)

- `src/decision_engine.py` — Motor V1.2 (rollback dormente)
- `src/telegram_client.py` — estrutural
- `radar13/radar13.py` + `radar13/radar13_watchdog.py` — agente paralelo
- `historical/` — projeto histórico (3.000 jogos)

---

## 23. Glossário

| Termo | Significado |
|---|---|
| CC | Chance Clara (`big_chance` no Flashscore) |
| BC | Big Chance (alias de CC) |
| xG | Expected goals (gols esperados) |
| xGOT | Expected goals on target |
| xA | Expected assists |
| rate | `minute / total_cc` — quanto MENOR, melhor |
| placar_abaixo_producao | `total_goals < total_cc // 3` |
| dominant_team | Time com mais BC no momento |
| dom_lead | `dominant_score - opp_score` — ≥ 2 bloqueia BACK |
| bucket | `cc // 3` — usado pra anti-spam de Telegram |
| Tier 0/0.5/1/2/3 | Camadas de prioridade da watchlist |
| Premium A/B/C | Hierarquia de cobertura premium |
| highlighted | Liga com estrela amarela no Flashscore |
| fingerprint | `home_id_away_id` — dedup canônico |
| canonical | Entry escolhido entre duplicados (mid-based vence) |
| cobertura passiva | Premium visível mas não escaneado neste ciclo |
| stale | TTL ativo de leitura inválida |
| no_stats_backoff | TTL exponencial após scan sem stats |

---

## 24. Changelog (v1.1 → v2.0)

### Adicionado

- 8 níveis de alerta (WATCH/FORTE/PREMIUM OVER + BACK + BILATERAL + PREMIUM xG)
- Priorização entre alertas (1 = mais forte)
- Anti-spam que respeita WATCH (não consome bucket)
- Telegram em todos os 8 níveis com motivo/leitura
- Sistema Tier 0.5 premium hierárquico (A/B/C/NONE)
- Cobertura passiva no terminal e em `premium_audit_by_level()`
- Walker DOM com `headerLeague__wrapper` (Flashscore 2026)
- Detecção de liga via 3 regras (CSS > nome > slug)
- Limpeza definitiva de `league_name` (90+ países canônicos)
- Deduplicação canônica (`fingerprint` + 6 critérios)
- Comandos CLI `--find-game`, `--debug-dom-game`, `--debug-league-walker`
- Coverage por motivo no heartbeat
- TargetClosedError silenciado no shutdown

### Removido

- Alerta único v1.1 (substituído pelos 8 níveis)
- Walker DOM por previousSibling (substituído por children direto do sportName)

### Preservado intacto

- Motor V1.2 (dormente, `--mode motor_v12`)
- Radar13
- Supervisor externo
- Discovery "ao vivo" + expansão de ligas
- Watchdog independente
- Faxina por TTL
- No-stats backoff exponencial
- Filtro `is_live_match`

---

## 25. Apêndice — exemplos didáticos

> Os exemplos abaixo foram capturados durante a operação real em ambiente de teste. Match IDs foram anonimizados (`FS_XXXXXXXX`) para preservar a finalidade pedagógica.

### A) Alerta WATCH OVER (exemplo didático — Brasileirão)

```text
📡 WATCH 3.1.2 — RADAR DE GOL
Time Casa 0-0 Time Visitante
Min 51 | CC: 2x2 = 4 | Rate: 12.8
Esperado por CC: 1 | Gols reais: 0

Motivo:
Produção suficiente para gol, mas o placar ainda não pagou.

Leitura:
Radar ativo. Não é entrada automática. Aguardar nova CC ou evolução para FORTE/PREMIUM.
```

`telegram_sent=True`, sem consumir bucket. Anti-spam permitiu FORTE/PREMIUM no mesmo bucket depois, caso o jogo evoluísse.

### B) Dossiê de um jogo Premium A (exemplo didático)

Saída do comando `--find-game` para um jogo do Brasileirão Betano:

```text
ENTRY: FS_XXXXXXXX
  is_premium:            True
  premium_level:         A
  premium_reason:        flashscore_highlighted_league
  premium_league_name:   Brasileirão Betano
  premium_country:       Brasil
  highlighted_league_detected: True
  league_header_classes: [headerLeague, headerLeague--has-star,
                          wcl-header_HrElx, wcl-pinned_dRFvU, ...]
  league_header_text:    Brasileirão Betano BRASIL: Classificação ao vivo
  VEREDITO: ENCONTRADO E MONITORADO (na watchlist atual)
```

Duplicado antigo (`FS_AAAAAAAA_BBBBBBBB`, sem `?mid=`) marcado automaticamente:

```text
  excluded_duplicate:    True
  duplicate_of:          FS_XXXXXXXX
  VEREDITO: DUPLICADO de FS_XXXXXXXX — não entra na watchlist, não consome slot
```

### C) Seção PREMIUM A/B/C no terminal

```text
🏆 PREMIUM A — PRIORIDADE MÁXIMA
   - Brasileirão Betano | Brasil | live=2 | watchlist=2 | passiva=0 | sem_stats=0
   - Brasileirão Série B | Brasil | live=3 | watchlist=3 | passiva=0 | sem_stats=0

🥈 PREMIUM B — COBERTURA SECUNDÁRIA
   - MLS Next Pro | Estados Unidos | live=2 | watchlist=1 | passiva=1 | sem_stats=0

🧩 PREMIUM C — FALLBACK POR TIME/SLUG
   (vazio neste ciclo — todas ligas detectadas via A ou B)

📋 COBERTURA PREMIUM PASSIVA (1)
   - [B] FS_XXXXXXXX | MLS Next Pro | min=30 0-0 | motivo=premium_overflow
```

---

\newpage

## Encerramento

Este dossiê é a **fonte única de verdade** do Código 3:1 — Regra 3.1.2.0. Qualquer divergência entre código e documentação deve ser tratada como bug e reportada.

**Versão 2.0** — 25 de maio de 2026 — © Trading Terminal.
