"""
signals_persistence — banco estruturado e DEDUPLICADO da Regra 3.1.2.0 (v2.7).

Persiste cada SINAL LÓGICO único em `logs/rule_3_1_2_signals.jsonl`. Chave
de deduplicação: `(match_id, alert_type, bucket)`. Isso impede que um WATCH
no bucket 1 grave 14 linhas (uma por ciclo de scan) — fica uma linha só.

Política preservada:
  - WATCH NÃO consome bucket operacional (regra inalterada)
  - WATCH NÃO envia Telegram (política inalterada)
  - FORTE/PREMIUM enviam Telegram normalmente
  - Anti-spam por bucket continua para FORTE/PREMIUM

Política NOVA:
  - Cada sinal único (match+type+bucket) gera UMA linha no JSONL
  - Linhas existentes recebem updates de last_seen_minute/score/gol_after_alert
    a cada novo scan do mesmo match (sem criar nova linha)
  - Quando jogo é finalizado, marca result_finalized=True

Coverage Guard, supervisor e Motor V1.2 NÃO escrevem aqui.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─── Mapeamentos de alert_type ────────────────────────────────────────

LEVEL_BY_TYPE = {
    "over_watch": "WATCH",
    "back_watch": "WATCH",
    "over_forte": "FORTE",
    "back_forte": "FORTE",
    "over_premium": "PREMIUM",
    "back_premium": "PREMIUM",
    "over_premium_xg": "PREMIUM",
    "over_bilateral_premium": "PREMIUM",
}

MARKET_BY_TYPE = {
    "over_watch": "OVER",
    "over_forte": "OVER",
    "over_premium": "OVER",
    "over_premium_xg": "OVER",
    "over_bilateral_premium": "OVER",
    "back_watch": "BACK",
    "back_forte": "BACK",
    "back_premium": "BACK",
}

WATCH_TYPES = frozenset({"over_watch", "back_watch"})


# ─── Helpers ──────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_brt_from_utc_iso(utc_iso: str) -> str:
    """Converte timestamp UTC pra data BRT (UTC-3) sem usar tz library."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return ""
    brt = dt.astimezone(timezone(timedelta_hours(-3)))
    return brt.strftime("%Y-%m-%d")


def timedelta_hours(h: int):
    from datetime import timedelta
    return timedelta(hours=h)


def signal_key(match_id: str, alert_type: str, bucket) -> tuple:
    """Chave de dedup: (match_id, alert_type, bucket)."""
    return (str(match_id or ""), str(alert_type or ""), int(bucket or 0))


def build_signal_record(*, match_id: str, url: str, home: str, away: str,
                         alert_type: str, bucket: int,
                         minute_at_alert: int, status_raw: str,
                         home_score: int, away_score: int,
                         home_bc: int, away_bc: int,
                         total_cc: int, cc_rate: float,
                         expected_goals_by_cc: int,
                         home_xgot: float = 0.0, away_xgot: float = 0.0,
                         home_xg: float = 0.0, away_xg: float = 0.0,
                         league_name: str = "", country: str = "",
                         premium_level: str = "NONE",
                         premium_reason: str = "",
                         telegram_sent: bool = False,
                         filter_reason: str = "") -> dict:
    """Monta o dicionário canônico de um sinal da Regra 3.1.2.0."""
    ts = _utc_now_iso()
    level = LEVEL_BY_TYPE.get(alert_type, "OTHER")
    market = MARKET_BY_TYPE.get(alert_type, "?")
    is_watch = alert_type in WATCH_TYPES

    dom_side, dom_bc, opp_bc, dom_goals_at, cc_diff = "", 0, 0, 0, 0
    if market == "BACK":
        if home_bc >= away_bc:
            dom_side = "home"
            dom_bc = home_bc; opp_bc = away_bc
            dom_goals_at = home_score
        else:
            dom_side = "away"
            dom_bc = away_bc; opp_bc = home_bc
            dom_goals_at = away_score
        cc_diff = abs(home_bc - away_bc)

    placar_abaixo = (home_score + away_score) < expected_goals_by_cc and expected_goals_by_cc > 0

    return {
        # Identificação
        "signal_id": f"sig_{uuid.uuid4().hex[:12]}",
        "timestamp_alert_utc": ts,
        "date_brt": _date_brt_from_utc_iso(ts),
        "match_id": match_id,
        "url": url,
        "home": home, "away": away,
        "league_name": league_name, "country": country,
        "premium_level": premium_level,
        "premium_reason": premium_reason,

        # Tipo de sinal
        "alert_type": alert_type,
        "level": level, "market": market,
        "telegram_sent": bool(telegram_sent),
        "is_watch_only": bool(is_watch),
        "bucket": int(bucket or 0),
        "filter_reason": filter_reason,

        # Estado no alerta
        "minute_at_alert": int(minute_at_alert or 0),
        "status_raw": status_raw or "",
        "home_score_at_alert": int(home_score or 0),
        "away_score_at_alert": int(away_score or 0),
        "total_goals_at_alert": int((home_score or 0) + (away_score or 0)),
        "home_bc_at_alert": int(home_bc or 0),
        "away_bc_at_alert": int(away_bc or 0),
        "total_bc_at_alert": int((home_bc or 0) + (away_bc or 0)),
        "cc_rate_at_alert": float(cc_rate or 0.0),
        "expected_goals_by_cc_at_alert": int(expected_goals_by_cc or 0),
        "placar_abaixo_producao": bool(placar_abaixo),

        # xG/xGOT
        "home_xg_at_alert": float(home_xg or 0.0),
        "away_xg_at_alert": float(away_xg or 0.0),
        "total_xg_at_alert": float((home_xg or 0.0) + (away_xg or 0.0)),
        "home_xgot_at_alert": float(home_xgot or 0.0),
        "away_xgot_at_alert": float(away_xgot or 0.0),

        # BACK
        "dominant_side": dom_side,
        "dominant_team": (home if dom_side == "home"
                          else away if dom_side == "away" else ""),
        "dominant_bc": int(dom_bc),
        "opponent_bc": int(opp_bc),
        "cc_diff": int(cc_diff),
        "dominant_goals_at_alert": int(dom_goals_at),
        "expected_goals_dominant": int(expected_goals_by_cc or 0),

        # Resultado posterior — inicialmente null
        "final_home_score": None,
        "final_away_score": None,
        "final_total_goals": None,
        "last_seen_minute": int(minute_at_alert or 0),
        "last_seen_score": f"{int(home_score or 0)}-{int(away_score or 0)}",
        "goal_after_alert": False,
        "goal_within_10m": False,
        "goal_within_20m": False,
        "goal_within_30m": False,
        "dominant_scored_after_alert": False,
        "dominant_won": None,
        "dominant_not_lost": None,
        "dominant_improved_score": False,
        "over_1_5_result": None,
        "over_2_5_result": None,
        "result_finalized": False,
        "result_auditable": False,
        "result_audit_reason": "",
        "closed_at_utc": None,
    }


# ─── Persistência ─────────────────────────────────────────────────────

_FILE_LOCK = threading.Lock()


def _load_index(path: Path) -> tuple:
    """Carrega arquivo existente: retorna (lista_records, set_keys, dict_pos)."""
    records = []
    keys = set()
    pos = {}   # signal_key → índice no arquivo (linha)
    if not path.exists():
        return records, keys, pos
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line: continue
                try: r = json.loads(line)
                except json.JSONDecodeError: continue
                records.append(r)
                k = signal_key(r.get("match_id"), r.get("alert_type"), r.get("bucket"))
                keys.add(k)
                pos[k] = i
    except OSError:
        pass
    return records, keys, pos


def record_signal(signal: dict, persist_path) -> bool:
    """Grava um sinal novo SE (match_id, alert_type, bucket) ainda não existe.

    Returns:
        True se o sinal foi gravado (novo); False se duplicado/ignorado.
    """
    p = Path(persist_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    k = signal_key(signal.get("match_id"), signal.get("alert_type"),
                    signal.get("bucket"))
    with _FILE_LOCK:
        _, keys, _ = _load_index(p)
        if k in keys:
            return False
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
    return True


def update_signal_observations(match_id: str, *, current_minute: int,
                                current_home_score: int,
                                current_away_score: int,
                                persist_path) -> int:
    """Atualiza os campos de observação posterior para TODOS os sinais
    não-finalizados deste match_id.

    Reescreve o arquivo (operação O(n) — JSONL é pequeno).

    Returns:
        Número de registros atualizados.
    """
    p = Path(persist_path)
    if not p.exists(): return 0
    updated = 0
    with _FILE_LOCK:
        records, _, _ = _load_index(p)
        if not records: return 0
        cur_total = int(current_home_score or 0) + int(current_away_score or 0)
        for r in records:
            if r.get("match_id") != match_id: continue
            if r.get("result_finalized"): continue
            # Atualiza last_seen
            r["last_seen_minute"] = int(current_minute or 0)
            r["last_seen_score"] = f"{int(current_home_score or 0)}-{int(current_away_score or 0)}"
            # Métrica: gol após alerta
            g_at = int(r.get("total_goals_at_alert", 0) or 0)
            min_at = int(r.get("minute_at_alert", 0) or 0)
            delta_min = int(current_minute or 0) - min_at
            gol_after = cur_total > g_at
            if gol_after:
                r["goal_after_alert"] = True
                if delta_min <= 10: r["goal_within_10m"] = True
                if delta_min <= 20: r["goal_within_20m"] = True
                if delta_min <= 30: r["goal_within_30m"] = True
            # BACK: dominante marcou?
            if r.get("market") == "BACK":
                dom_side = r.get("dominant_side")
                dom_at = int(r.get("dominant_goals_at_alert", 0) or 0)
                if dom_side == "home":
                    dom_now = int(current_home_score or 0)
                    opp_now = int(current_away_score or 0)
                else:
                    dom_now = int(current_away_score or 0)
                    opp_now = int(current_home_score or 0)
                opp_at = (int(r["away_score_at_alert"]) if dom_side == "home"
                          else int(r["home_score_at_alert"]))
                dom_g_after = dom_now - dom_at
                opp_g_after = opp_now - opp_at
                if dom_g_after > 0:
                    r["dominant_scored_after_alert"] = True
                if dom_g_after > opp_g_after:
                    r["dominant_improved_score"] = True
            updated += 1
        # Reescreve atomicamente
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, p)
    return updated


def finalize_signals_for_match(match_id: str, *, final_home_score: int,
                                final_away_score: int, final_minute: int,
                                reason: str, persist_path) -> int:
    """Marca todos os sinais do match_id como result_finalized=True.

    Calcula métricas finais (over_1_5_result, over_2_5_result,
    dominant_won, dominant_not_lost, result_auditable).
    """
    p = Path(persist_path)
    if not p.exists(): return 0
    finalized = 0
    with _FILE_LOCK:
        records, _, _ = _load_index(p)
        if not records: return 0
        fh = int(final_home_score or 0); fa = int(final_away_score or 0)
        ft = fh + fa
        is_auditable = int(final_minute or 0) >= 90 or reason == "FINISHED_MATCH"
        for r in records:
            if r.get("match_id") != match_id: continue
            if r.get("result_finalized"): continue
            r["final_home_score"] = fh
            r["final_away_score"] = fa
            r["final_total_goals"] = ft
            r["last_seen_minute"] = int(final_minute or r["last_seen_minute"])
            r["last_seen_score"] = f"{fh}-{fa}"
            r["over_1_5_result"] = bool(ft >= 2)
            r["over_2_5_result"] = bool(ft >= 3)
            # BACK: resolve dominant_won/dominant_not_lost
            if r.get("market") == "BACK":
                dom_side = r.get("dominant_side")
                if dom_side == "home":
                    r["dominant_won"] = bool(fh > fa)
                    r["dominant_not_lost"] = bool(fh >= fa)
                elif dom_side == "away":
                    r["dominant_won"] = bool(fa > fh)
                    r["dominant_not_lost"] = bool(fa >= fh)
            # Confirma goal_after_alert com placar final
            g_at = int(r.get("total_goals_at_alert", 0) or 0)
            if ft > g_at:
                r["goal_after_alert"] = True
            r["result_finalized"] = True
            r["result_auditable"] = is_auditable
            r["result_audit_reason"] = reason
            r["closed_at_utc"] = _utc_now_iso()
            finalized += 1
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, p)
    return finalized


def load_all(persist_path) -> list:
    """Lê todos os sinais do arquivo (uso por scripts de análise)."""
    p = Path(persist_path)
    records, _, _ = _load_index(p)
    return records


def has_signal(match_id: str, alert_type: str, bucket, persist_path) -> bool:
    """True se o sinal já foi gravado (dedup check)."""
    p = Path(persist_path)
    _, keys, _ = _load_index(p)
    return signal_key(match_id, alert_type, bucket) in keys
