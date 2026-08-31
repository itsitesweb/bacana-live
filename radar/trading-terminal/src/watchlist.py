"""
Watchlist priorizada — seleciona quais jogos do catálogo escanear neste ciclo.

Sistema de tiers (do mais forte ao mais fraco):
  - Tier 0   (must-include): posição aberta OU sinal ENTER recente (anti-spam window).
                              Nunca descartável, ignora stale/no_stats.
  - Tier 0.5 (premium ao vivo): jogo de liga premium (Premier League, La Liga,
                                 Bundesliga, Serie A, Ligue 1, Champions/Europa/
                                 Conference League, Eredivisie, Primeira Liga, MLS).
                                 Entra MESMO antes do min 20 — corrige o problema
                                 de jogo grande ficar 4-10min sem scan no Tier 3.
                                 Respeita finished_or_not_live, no_stats_until e
                                 stale_until. Janela operacional ampla (0-90).
                                 FIFO interna por last_scanned_at ASC.
  - Tier 1   (high):  janela operacional 20-83 AND BC>0 AND not stale AND not no_stats.
  - Tier 2   (medium): janela operacional 20-83 AND BC=0 AND ever_loaded_stats
                       AND not stale AND not no_stats.
  - Tier 3   (low/FIFO): resto, ordenado por (last_scanned_at ASC, first_seen_at ASC).
                         Slots reservados via tier3_reserved.

Tier 1, Tier 2 e Tier 0.5 respeitam stale_until E no_stats_until.
Tier 0.5 NÃO entra se já estiver em Tier 0 (deduplicação) — Tier 0 tem prioridade.

SEM lógica de regra. SEM read_match. Apenas seleção.
"""
from datetime import datetime, timezone
from typing import Optional


def build_watchlist(catalog, *,
                    max_size: int = 15,
                    tier3_reserved: int = 3,
                    premium_reserved: int = 8,
                    entry_min_minute: int = 20,
                    entry_max_minute: int = 83,
                    premium_min_minute: int = 0,
                    premium_max_minute: int = 90,
                    anti_spam_minutes: int = 5,
                    now: Optional[datetime] = None) -> list:
    """
    Constrói lista de match_ids ordenada por prioridade.

    Args:
        catalog: instância de Catalog
        max_size: tamanho máximo (Tier 0 pode estourar)
        tier3_reserved: slots mínimos reservados para Tier 3
        premium_reserved: slots máximos reservados para Tier 0.5 (premium ao vivo).
                          Se houver menos premium do que o cap, sobra retorna pros
                          tiers normais. Se houver mais, premium adicionais entram
                          pela quota normal de Tier 1/2/3 (não somem).
        entry_min_minute, entry_max_minute: janela operacional Tier 1/2.
        premium_min_minute, premium_max_minute: janela operacional Tier 0.5
                          (ampla, 0-90 por padrão; permite scan de jogos premium
                          desde o apito inicial).
        anti_spam_minutes: janela em que ENTER recente trava o jogo no Tier 0.
        now: timestamp para testes determinísticos.

    Returns:
        list[str]: match_ids ordenados (Tier 0 → Tier 0.5 → Tier 1+2 → Tier 3).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    games = catalog.all()

    tier0 = []
    tier05_pairs = []  # (mid, last_scanned_at, first_seen_at) — FIFO
    tier1 = []
    tier2 = []
    tier3_pairs = []  # (mid, last_scanned_at, first_seen_at)

    for g in games:
        mid = g["match_id"]

        # ─── Filtro raiz 1: duplicado (não-canônico) ────────────────
        # Quando o mesmo jogo aparece em 2 entries (URL com e sem ?mid=),
        # Catalog.recompute_duplicates() escolhe o canônico (mid-based vence).
        # O não-canônico recebe excluded_duplicate=True e nunca entra na
        # watchlist — não consome slot, não gera alerta.
        if g.get("excluded_duplicate"):
            continue

        # ─── Filtro raiz 1.5 (v2.10): reserva/youth marcado no upsert ──
        # Catalog detecta reserve/youth via URL/league_meta no upsert e
        # marca excluded_reserve=True. Esses NUNCA entram em watchlist.
        if g.get("excluded_reserve"):
            continue

        # ─── Filtro raiz 2: jogo finalizado/suspenso/cancelado ─────
        # Pula TODOS os tiers, incluindo Tier 0 — jogo terminado não pode
        # ter posição aberta nem alerta válido. Evita reescaneamento eterno.
        if catalog.is_finished_or_not_live_active(mid, now):
            continue

        minute = g.get("last_minute")
        bc_sum = int(g.get("last_bc_sum") or 0)
        ever_loaded = bool(g.get("ever_loaded_stats"))
        is_stale = catalog.is_stale_active(mid, now)
        is_no_stats = catalog.is_no_stats_active(mid, now)
        is_premium = bool(g.get("is_premium", False))

        # ─── Tier 0 — must-include (ignora stale/no_stats) ─────────
        if g.get("has_open_position"):
            tier0.append(mid)
            continue

        last_action = g.get("last_signal_action") or ""
        if last_action.startswith("ENTER_"):
            last_sig_min = int(g.get("last_signal_minute") or 0)
            cur_min = minute if minute is not None else last_sig_min
            if (cur_min - last_sig_min) < anti_spam_minutes:
                tier0.append(mid)
                continue

        # ─── Demais tiers respeitam stale E no_stats ────────────────
        if is_stale or is_no_stats:
            continue

        # ─── Tier 0.5 — Premium ao vivo (HIERÁRQUICO A > C(stats) > B) ──
        # Ordem de prioridade dentro de Tier 0.5 (menor rank = entra primeiro):
        #   PRIO 1: Premium A com stats
        #   PRIO 2: Premium A sem stats (mas live)
        #   PRIO 3: Premium C (slug) com stats
        #   PRIO 4: Premium B com stats e BC>0
        #   PRIO 5: Premium B com stats sem BC
        #   PRIO 6: Premium B sem stats
        # Regra crítica: Premium A nunca perde slot pra Premium B.
        if is_premium:
            in_premium_window = (
                minute is None
                or (premium_min_minute <= minute <= premium_max_minute)
            )
            if in_premium_window:
                level = g.get("premium_level", "B")
                # prio base por nível
                if level == "A":
                    prio = 1 if ever_loaded else 2
                elif level == "C":
                    prio = 3 if ever_loaded else 6
                else:  # B (ou desconhecido)
                    if ever_loaded and bc_sum > 0: prio = 4
                    elif ever_loaded: prio = 5
                    else: prio = 6
                rank = (
                    prio,                                          # 1) prio level
                    0 if (minute is not None and 1 <= minute <= 83) else 1,  # 2) janela
                    g.get("last_scanned_at") or "",                # 3) FIFO
                    g.get("first_seen_at") or "",
                )
                tier05_pairs.append((mid, rank))
                continue

        in_window = (
            minute is not None
            and entry_min_minute <= minute <= entry_max_minute
        )

        # Tier 1 — janela + BC>0
        if in_window and bc_sum > 0:
            tier1.append(mid)
            continue

        # Tier 2 — janela + sem BC + já carregou stats antes
        if in_window and bc_sum == 0 and ever_loaded:
            tier2.append(mid)
            continue

        # Tier 3 — FIFO (resto)
        # Guardamos (last_scanned_at, first_seen_at) pra ordenação:
        #   1º critério: last_scanned_at ASC — nunca-escaneados ("") vêm primeiro
        #   2º critério: first_seen_at ASC — entre nunca-escaneados, descobertos
        #                ANTES vêm primeiro (FIFO).
        tier3_pairs.append((
            mid,
            g.get("last_scanned_at") or "",
            g.get("first_seen_at") or "",
        ))

    # Tier 0.5: sort por rank tuple (menor=melhor); Tier 3: FIFO clássico
    tier05_pairs.sort(key=lambda t: t[1])
    tier3_pairs.sort(key=lambda t: (t[1], t[2]))
    tier05 = [p[0] for p in tier05_pairs]
    tier3 = [p[0] for p in tier3_pairs]

    # ─── Composição final ──────────────────────────────────────────
    result = list(tier0)  # Tier 0 entra sempre

    available = max_size - len(result)
    if available <= 0:
        return result

    # Tier 0.5 — premium ao vivo (cap em premium_reserved)
    take_premium = min(premium_reserved, len(tier05), available)
    result.extend(tier05[:take_premium])
    leftover_premium = tier05[take_premium:]  # premiums que não couberam no cap

    available = max_size - len(result)
    if available <= 0:
        return result

    # Reserva pra Tier 3 (se houver candidatos)
    reserved = min(tier3_reserved, len(tier3), available)
    quota_high = available - reserved

    # Preencher Tier 1 e Tier 2 com quota_high.
    # Leftover premium (jogos premium além do cap) entram com PRIORIDADE
    # nessa quota, antes dos Tier 1/2 comuns — premium nunca é "demovido".
    high = leftover_premium + tier1 + tier2
    take_high = min(quota_high, len(high))
    result.extend(high[:take_high])

    # Slots restantes vão pra Tier 3
    remaining = max_size - len(result)
    if remaining > 0 and tier3:
        result.extend(tier3[:remaining])

    # Se Tier 3 esgotou antes da reserva, volta pra Tier 1+2 (e leftover premium)
    leftover_high = high[take_high:]
    remaining_after = max_size - len(result)
    if remaining_after > 0 and leftover_high:
        result.extend(leftover_high[:remaining_after])

    return result
