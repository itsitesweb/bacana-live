"""
DOMINANT_TRAILING_PROTECTION — Blindagem da Regra 3.1.2.0 Turbo.

Problema:
  Jogos onde o lado dominante estatístico (mais CC, xG, volume) está
  PERDENDO no placar viram trap. A regra antiga interpreta "gol devendo"
  e dispara FORTE/PREMIUM, mas o dominante já perdeu o jogo na prática.

Solução (este módulo):
  Função pura validate(signal_payload, match_history=None) que devolve
  decisão estruturada SEM tocar no daemon. Modo dry-run: appendar resultado
  em logs/dominant_trailing_audit.jsonl e deixar o daemon seguir.

Política:
  - Se dominante está perdendo, exigir "reação viva confirmada" (≥2 dos 6
    critérios) DEPOIS de ficar atrás. Sem reação → bloqueia FORTE/PREMIUM.
  - Se perdendo por ≥2, só libera com pressão brutal recente.
  - Alerta no 1º tempo sem confirmação até min 55 → expira.
  - Adversário amplia após alerta → cancela.

Tudo é função pura. validate() não escreve nada por si só; o caller usa
audit_log() pra appendar em logs/dominant_trailing_audit.jsonl.

Uso típico (no daemon, modo dry-run):
    from src.dominant_trailing_protection import validate, audit_log
    decision = validate(signal_payload, match_history=snapshots)
    audit_log(signal_payload, decision)
    # Em dry-run: NÃO usa decision pra bloquear Telegram.
    # Em enforcement futuro: if not decision["entry_allowed"]: return
"""
import json
from datetime import datetime, timezone
from pathlib import Path

__version__ = "1.0.0"

# === Limiares fixos (do spec) ============================================
REACTION_BC_THRESHOLD       = 1     # ≥1 big chance dominante após trailing
REACTION_XG_THRESHOLD       = 0.45  # ≥0.45 xG dominante após trailing
REACTION_SOT_THRESHOLD      = 2     # ≥2 SOT dominante após trailing
REACTION_SHOTS_THRESHOLD    = 5     # ≥5 finalizações dominante após trailing
REACTION_MIN_CRITERIA_HIT   = 2     # precisa bater pelo menos 2 dos 6

# Pressão brutal (exceção quando trailing_by ≥ 2)
BRUTAL_LAST10_BC            = 2
BRUTAL_LAST10_XG            = 0.70
BRUTAL_LAST10_SOT           = 3

# Confirmação de tese 1º tempo após HT
HALFTIME_CONFIRM_MIN        = 55
HT_NEW_XG_AFTER_ALERT       = 0.35
HT_NEW_SOT_AFTER_ALERT      = 2

# Janelas de pressão recente
PRESSURE_WINDOW_MIN         = 15
LAST10_WINDOW_MIN           = 10


# === Statuses ============================================================
STATUS_GOAL_DEBT_ALIVE          = "GOAL_DEBT_ALIVE"
STATUS_GOAL_DEBT_DEAD           = "GOAL_DEBT_DEAD"
STATUS_DOMINANT_TRAILING_TRAP   = "DOMINANT_TRAILING_TRAP"
STATUS_DOMINANT_REACTION_CONF   = "DOMINANT_REACTION_CONFIRMED"

PRESSURE_BRUTAL  = "brutal"
PRESSURE_FORTE   = "forte"
PRESSURE_NEUTRO  = "neutro"
PRESSURE_DEAD    = "dead"

ALERT_TIER_WATCH_INTERNAL = "WATCH_INTERNAL"

BLOCK_MESSAGE = ("BLOQUEADO — dominante estatístico está perdendo e não "
                 "confirmou reação viva após ficar atrás. Produção "
                 "acumulada não autoriza entrada.")


# === Helpers =============================================================
def _num(v, default=0):
    try: return float(v) if isinstance(v, float) else int(v)
    except (TypeError, ValueError): return default


def _get(d, key, default=None):
    if d is None: return default
    v = d.get(key, default)
    return default if v is None else v


def compute_dominant_side(payload):
    """Determina dominant_side pelo critério hierárquico:
       1. mais big_chances; 2. desempate por xG; 3. SOT; 4. shots."""
    if not payload: return None
    explicit = (payload.get("dominant_side") or "").strip().lower()
    if explicit in ("home", "away"):
        return explicit
    h_bc = _num(payload.get("home_bc_at_alert"))
    a_bc = _num(payload.get("away_bc_at_alert"))
    if h_bc != a_bc:
        return "home" if h_bc > a_bc else "away"
    h_xg = float(_num(payload.get("home_xg_at_alert"), 0.0))
    a_xg = float(_num(payload.get("away_xg_at_alert"), 0.0))
    if h_xg != a_xg:
        return "home" if h_xg > a_xg else "away"
    h_sot = _num(payload.get("home_sot_at_alert"))
    a_sot = _num(payload.get("away_sot_at_alert"))
    if h_sot != a_sot:
        return "home" if h_sot > a_sot else "away"
    h_sh = _num(payload.get("home_shots_at_alert"))
    a_sh = _num(payload.get("away_shots_at_alert"))
    if h_sh != a_sh:
        return "home" if h_sh > a_sh else "away"
    return None  # empate total — sem dominante


def _side_get(side, payload, key_home, key_away, default=0):
    return _num(payload.get(key_home if side == "home" else key_away), default)


def _find_minute_trailing_started(side, snapshots):
    """Primeira ocorrência (em ordem cronológica) onde dominante começou a
    perder após estar empate/à frente. None se nunca ficou atrás."""
    if not snapshots: return None
    snaps = sorted(snapshots, key=lambda s: _num(s.get("minute"), 0))
    was_trailing = False
    for snap in snaps:
        h = _num(snap.get("home_score"))
        a = _num(snap.get("away_score"))
        if side == "home":
            trailing = a > h
        else:
            trailing = h > a
        if trailing and not was_trailing:
            return _num(snap.get("minute"), 0)
        was_trailing = trailing
    return None


def _accumulate_dominant_stats(side, snapshots, *, after_minute=None,
                                 before_minute=None, window_size=None):
    """Soma BC/xG/SOT/shots do dominante numa janela.

    after_minute: usa apenas snapshots com minute > after_minute
    before_minute: usa apenas snapshots com minute < before_minute
    window_size: pega só os últimos N minutos antes do snapshot final
    """
    if not snapshots: return {"bc":0,"xg":0.0,"sot":0,"shots":0}
    snaps = sorted(snapshots, key=lambda s: _num(s.get("minute"), 0))
    # after_minute/before_minute INCLUSIVOS no marco — o snapshot do minuto
    # da virada serve como base p/ "after" e como teto p/ "before", de modo
    # que (last_after - first_after) represente o ganho REAL desde a virada.
    if after_minute is not None:
        snaps = [s for s in snaps if _num(s.get("minute"), 0) >= after_minute]
    if before_minute is not None:
        snaps = [s for s in snaps if _num(s.get("minute"), 0) <= before_minute]
    if window_size and snaps:
        last_min = _num(snaps[-1].get("minute"), 0)
        snaps = [s for s in snaps if _num(s.get("minute"), 0) >= last_min - window_size]
    if not snaps: return {"bc":0,"xg":0.0,"sot":0,"shots":0}
    # Last snapshot na janela tem o cumulativo. Subtrai o primeiro (antes da janela).
    # Como snapshots são CUMULATIVOS, "ganho na janela" = last - first_inside.
    bc_key  = "home_bc" if side == "home" else "away_bc"
    xg_key  = "home_xg" if side == "home" else "away_xg"
    sot_key = "home_sot" if side == "home" else "away_sot"
    sh_key  = "home_shots" if side == "home" else "away_shots"
    first, last = snaps[0], snaps[-1]
    return {
        "bc":    max(0, _num(last.get(bc_key))  - _num(first.get(bc_key))),
        "xg":    max(0.0, float(_num(last.get(xg_key), 0.0))
                          - float(_num(first.get(xg_key), 0.0))),
        "sot":   max(0, _num(last.get(sot_key)) - _num(first.get(sot_key))),
        "shots": max(0, _num(last.get(sh_key))  - _num(first.get(sh_key))),
    }


def _classify_pressure(stats, *, window):
    """Classifica pressão na janela. window é descritivo (15 ou 10)."""
    bc, xg, sot = stats["bc"], stats["xg"], stats["sot"]
    if window == 10:
        if bc >= BRUTAL_LAST10_BC or xg >= BRUTAL_LAST10_XG or sot >= BRUTAL_LAST10_SOT:
            return PRESSURE_BRUTAL
    # janela 15 e fallback genérico
    if bc >= 2 or xg >= 0.60 or sot >= 3:
        return PRESSURE_BRUTAL
    if bc >= 1 or xg >= 0.30 or sot >= 2:
        return PRESSURE_FORTE
    if bc == 0 and xg < 0.10 and sot == 0:
        return PRESSURE_DEAD
    return PRESSURE_NEUTRO


def _count_opponent_goals_after(side, snapshots, alert_minute):
    """Quantos gols o adversário do dominante marcou após alert_minute."""
    if not snapshots: return 0
    snaps = sorted(snapshots, key=lambda s: _num(s.get("minute"), 0))
    opp_key = "away_score" if side == "home" else "home_score"
    at_alert = None
    final_val = None
    for s in snaps:
        m = _num(s.get("minute"), 0)
        sc = _num(s.get(opp_key), 0)
        if at_alert is None and m >= alert_minute:
            at_alert = sc
        final_val = sc
    if at_alert is None: at_alert = 0
    return max(0, (final_val or 0) - at_alert)


# === Núcleo: validate() ==================================================
def validate(signal_payload, match_history=None):
    """Avalia um sinal sob a política DOMINANT_TRAILING_PROTECTION.

    Args:
        signal_payload: dict com chaves do banco limpo
            (home_score_at_alert, away_score_at_alert, home_bc_at_alert,
             away_bc_at_alert, minute_at_alert, level, alert_type, ...)
            Campos opcionais ricos: home_sot_at_alert, away_sot_at_alert,
             home_shots_at_alert, away_shots_at_alert.
        match_history: lista opcional de snapshots cumulativos do jogo.
            Cada snapshot:
              {minute, home_score, away_score,
               home_bc, away_bc, home_xg, away_xg,
               home_sot, away_sot, home_shots, away_shots}
            Se None: o módulo opera em modo degradado (só sabe do estado no
            alerta, sem informação sobre BEFORE/AFTER trailing).

    Returns: dict com os 17 campos obrigatórios + entry_allowed + block_reason
             + alert_tier + statuses + telegram_sent_recommended + meta.
    """
    p = signal_payload or {}
    alert_minute = _num(p.get("minute_at_alert"), 0)
    level = (p.get("level") or "").upper()
    alert_type = (p.get("alert_type") or "").lower()

    out = {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dominant_side": None, "dominant_score": 0, "opponent_score": 0,
        "dominant_is_trailing": False, "dominant_trailing_by": 0,
        "minute_when_dominant_started_trailing": None,
        "dominant_big_chances_before_trailing": 0,
        "dominant_big_chances_after_trailing":  0,
        "dominant_xg_before_trailing":  0.0,
        "dominant_xg_after_trailing":   0.0,
        "dominant_sot_before_trailing": 0,
        "dominant_sot_after_trailing":  0,
        "dominant_shots_after_trailing": 0,
        "opponent_goals_after_alert":   0,
        "live_pressure_status": PRESSURE_NEUTRO,
        "dominant_reaction_status": "unknown",
        "entry_allowed": True,
        "block_reason": "",
        "alert_tier": level or "",
        "status": STATUS_GOAL_DEBT_ALIVE,
        "telegram_sent_recommended": True,
        "block_message": "",
        "history_provided": match_history is not None,
        "criteria_hit_count": 0,
        "criteria_breakdown": {},
    }

    # 1. Determinar dominante
    side = compute_dominant_side(p)
    out["dominant_side"] = side
    if side is None:
        # Sem dominante = sem trailing trap possível. Deixa passar.
        out["dominant_reaction_status"] = "no_dominant"
        return out

    # 2. Placar dominante vs adversário no alerta
    h_sc = _num(p.get("home_score_at_alert"))
    a_sc = _num(p.get("away_score_at_alert"))
    dom_sc = h_sc if side == "home" else a_sc
    opp_sc = a_sc if side == "home" else h_sc
    out["dominant_score"] = dom_sc
    out["opponent_score"] = opp_sc
    is_trailing = opp_sc > dom_sc
    out["dominant_is_trailing"] = is_trailing
    out["dominant_trailing_by"] = max(0, opp_sc - dom_sc)

    # Se não está perdendo: passa direto (regra é PROTEÇÃO de trailing)
    if not is_trailing:
        out["dominant_reaction_status"] = "not_trailing"
        return out

    # === Está perdendo → ativa proteção ====================================
    out["status"] = STATUS_DOMINANT_TRAILING_TRAP

    # 3. Quando começou a perder + janelas before/after
    started = (_find_minute_trailing_started(side, match_history)
               if match_history else None)
    out["minute_when_dominant_started_trailing"] = started

    if match_history and started is not None:
        before = _accumulate_dominant_stats(side, match_history,
                                              before_minute=started)
        after = _accumulate_dominant_stats(side, match_history,
                                             after_minute=started)
        out["dominant_big_chances_before_trailing"] = before["bc"]
        out["dominant_big_chances_after_trailing"]  = after["bc"]
        out["dominant_xg_before_trailing"]  = round(before["xg"], 2)
        out["dominant_xg_after_trailing"]   = round(after["xg"], 2)
        out["dominant_sot_before_trailing"] = before["sot"]
        out["dominant_sot_after_trailing"]  = after["sot"]
        out["dominant_shots_after_trailing"] = after["shots"]

    # Sobreposição: se payload tiver campos explícitos, respeita-os
    for k in ("dominant_big_chances_after_trailing",
              "dominant_xg_after_trailing",
              "dominant_sot_after_trailing",
              "dominant_shots_after_trailing"):
        if k in p and p[k] is not None:
            out[k] = p[k]

    # 4. Pressão last_15 e last_10 (do dominante)
    if match_history:
        last15 = _accumulate_dominant_stats(side, match_history,
                                             window_size=PRESSURE_WINDOW_MIN)
        last10 = _accumulate_dominant_stats(side, match_history,
                                             window_size=LAST10_WINDOW_MIN)
        out["live_pressure_status"] = _classify_pressure(last15, window=15)
        pressure_last_10 = _classify_pressure(last10, window=10)
    else:
        # Sem history: aceita override explícito do payload, senão neutro
        out["live_pressure_status"] = (p.get("pressure_last_15")
                                        or PRESSURE_NEUTRO)
        pressure_last_10 = p.get("pressure_last_10") or PRESSURE_NEUTRO

    # 5. Adversário marcou após alerta?
    if match_history:
        opp_goals_after = _count_opponent_goals_after(side, match_history,
                                                       alert_minute)
        out["opponent_goals_after_alert"] = opp_goals_after
    else:
        opp_goals_after = _num(p.get("opponent_goals_after_alert"), 0)
        out["opponent_goals_after_alert"] = opp_goals_after

    # 6. Filtro de reação (≥2 dos 6 critérios)
    crit = {
        "bc_after_ge_1":  out["dominant_big_chances_after_trailing"] >= REACTION_BC_THRESHOLD,
        "xg_after_ge_45": float(out["dominant_xg_after_trailing"]) >= REACTION_XG_THRESHOLD,
        "sot_after_ge_2": out["dominant_sot_after_trailing"] >= REACTION_SOT_THRESHOLD,
        "shots_after_ge_5": out["dominant_shots_after_trailing"] >= REACTION_SHOTS_THRESHOLD,
        "pressure_15_strong": out["live_pressure_status"] in (PRESSURE_FORTE, PRESSURE_BRUTAL),
        "no_dangerous_counter": opp_goals_after == 0,
    }
    hit = sum(1 for v in crit.values() if v)
    out["criteria_hit_count"] = hit
    out["criteria_breakdown"] = crit
    reaction_confirmed = hit >= REACTION_MIN_CRITERIA_HIT
    out["dominant_reaction_status"] = ("confirmed" if reaction_confirmed
                                        else "not_confirmed")

    # 7. Cancelamento direto: adversário ampliou após alerta
    if opp_goals_after > 0:
        out["entry_allowed"] = False
        out["block_reason"]  = "opponent_extended_lead_after_alert"
        out["alert_tier"]    = ALERT_TIER_WATCH_INTERNAL
        out["status"]        = STATUS_GOAL_DEBT_DEAD
        out["telegram_sent_recommended"] = False
        out["block_message"] = BLOCK_MESSAGE
        return out

    # 8. Trailing_by ≥ 2: bloqueia, salvo pressão brutal recente
    if out["dominant_trailing_by"] >= 2:
        if pressure_last_10 != PRESSURE_BRUTAL:
            out["entry_allowed"] = False
            out["block_reason"]  = "dominant_trailing_by_two_or_more"
            out["alert_tier"]    = ALERT_TIER_WATCH_INTERNAL
            out["status"]        = STATUS_DOMINANT_TRAILING_TRAP
            out["telegram_sent_recommended"] = False
            out["block_message"] = BLOCK_MESSAGE
            return out
        # exceção: pressão brutal → exige reação ainda
        if not reaction_confirmed:
            out["entry_allowed"] = False
            out["block_reason"]  = "dominant_trailing_by_two_brutal_but_no_reaction"
            out["alert_tier"]    = ALERT_TIER_WATCH_INTERNAL
            out["status"]        = STATUS_DOMINANT_TRAILING_TRAP
            out["telegram_sent_recommended"] = False
            out["block_message"] = BLOCK_MESSAGE
            return out

    # 9. Alerta no 1º tempo: validade até min 55
    if alert_minute <= 45 and match_history:
        # Olha snapshots após alerta + até min 55
        snaps = sorted(match_history, key=lambda s: _num(s.get("minute"), 0))
        after_alert = [s for s in snaps if _num(s.get("minute"),0) > alert_minute]
        if after_alert and _num(after_alert[-1].get("minute"), 0) >= HALFTIME_CONFIRM_MIN:
            ga = _accumulate_dominant_stats(side, after_alert)
            has_new_bc    = ga["bc"] >= 1
            has_new_xg    = ga["xg"] >= HT_NEW_XG_AFTER_ALERT
            has_new_sot   = ga["sot"] >= HT_NEW_SOT_AFTER_ALERT
            if not (has_new_bc or has_new_xg or has_new_sot):
                out["entry_allowed"] = False
                out["block_reason"]  = "first_half_alert_not_confirmed_after_halftime"
                out["alert_tier"]    = ALERT_TIER_WATCH_INTERNAL
                out["status"]        = STATUS_GOAL_DEBT_DEAD
                out["live_pressure_status"] = PRESSURE_DEAD
                out["telegram_sent_recommended"] = False
                out["block_message"] = BLOCK_MESSAGE
                return out

    # 10. Sem reação confirmada → bloqueia FORTE/PREMIUM
    if not reaction_confirmed:
        out["entry_allowed"] = False
        out["block_reason"]  = "dominant_trailing_without_confirmed_reaction"
        out["alert_tier"]    = ALERT_TIER_WATCH_INTERNAL
        out["status"]        = STATUS_DOMINANT_TRAILING_TRAP
        out["telegram_sent_recommended"] = False
        out["block_message"] = BLOCK_MESSAGE
        return out

    # 11. Reação confirmada — libera, marca status apropriado
    out["status"] = STATUS_DOMINANT_REACTION_CONF
    # alert_tier permanece o original (level original)
    return out


# === Audit log (dry-run) =================================================
AUDIT_LOG = (Path(__file__).resolve().parent.parent
             / "logs" / "dominant_trailing_audit.jsonl")


def audit_log(signal_payload, decision, *, path=None):
    """Appenda decisão em logs/dominant_trailing_audit.jsonl.
    Não toca em nenhum outro arquivo. Cria pasta se preciso.
    """
    p = Path(path) if path else AUDIT_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "signal_id":   (signal_payload or {}).get("signal_id"),
        "match_id":    (signal_payload or {}).get("match_id"),
        "home":        (signal_payload or {}).get("home"),
        "away":        (signal_payload or {}).get("away"),
        "minute":      (signal_payload or {}).get("minute_at_alert"),
        "level":       (signal_payload or {}).get("level"),
        "alert_type":  (signal_payload or {}).get("alert_type"),
        "decision":    decision,
    }
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
