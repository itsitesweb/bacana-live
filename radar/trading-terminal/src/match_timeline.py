"""
MATCH_TIMELINE — Captura temporal + engine de derivadas.

A cada scan (~2 min), o daemon chama append_snapshot(match_state).
A função guarda em logs/timelines/<match_id>.jsonl e expõe derivadas:
  - delta_2m, delta_15m, delta_30m por métrica
  - velocity, acceleration
  - inflection (subindo/estável/caindo)

NÃO toma decisão. Só fornece dados pra quem decide (turbo_score, reader).
Função pura sobre disco — escrita atômica.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

__version__ = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
TIMELINES_DIR = _ROOT / "logs" / "timelines"


# Métricas da Quádrupla + auxiliares que entram no funil
FUNNEL_METRICS = (
    "home_cc","away_cc",
    "home_xg","away_xg",
    "home_xgot","away_xgot",
    "home_xa","away_xa",
    "home_shots","away_shots",
    "home_sot","away_sot",
)


def _timeline_path(match_id: str) -> Path:
    return TIMELINES_DIR / f"{match_id}.jsonl"


def append_snapshot(ms_dict: dict) -> Path:
    """Salva snapshot do MatchState em disco. Retorna o caminho do arquivo.

    Snapshot inclui métricas funil + bag de contexto (all_stats).
    """
    mid = ms_dict.get("match_id") or "FS_UNKNOWN"
    minute = ms_dict.get("minute", 0)
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "minute": minute,
        "home": ms_dict.get("home", ""),
        "away": ms_dict.get("away", ""),
        "home_score": ms_dict.get("home_score", 0),
        "away_score": ms_dict.get("away_score", 0),
        # Funil — Quádrupla + auxiliares
        "home_cc": ms_dict.get("home_bc", 0) or ms_dict.get("home_cc", 0),
        "away_cc": ms_dict.get("away_bc", 0) or ms_dict.get("away_cc", 0),
        "home_xg": ms_dict.get("home_xg", 0.0),
        "away_xg": ms_dict.get("away_xg", 0.0),
        "home_xgot": ms_dict.get("home_xgot", 0.0),
        "away_xgot": ms_dict.get("away_xgot", 0.0),
        "home_xa": ms_dict.get("home_xa", 0.0),
        "away_xa": ms_dict.get("away_xa", 0.0),
        "home_shots": ms_dict.get("home_shots", 0),
        "away_shots": ms_dict.get("away_shots", 0),
        "home_sot": ms_dict.get("home_sot", 0),
        "away_sot": ms_dict.get("away_sot", 0),
        # Contexto — bag completo pra leitura
        "all_stats": ms_dict.get("all_stats", {}),
    }
    p = _timeline_path(mid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return p


def load_timeline(match_id: str, *, max_snapshots: int = 60) -> List[dict]:
    """Carrega últimos N snapshots do match_id."""
    p = _timeline_path(match_id)
    if not p.exists():
        return []
    with open(p) as f:
        lines = f.readlines()[-max_snapshots:]
    out = []
    for ln in lines:
        try: out.append(json.loads(ln))
        except: continue
    return out


def _value(snapshot: dict, metric: str) -> float:
    v = snapshot.get(metric, 0)
    try: return float(v)
    except: return 0.0


# v4.1 — Métricas cumulativas (delta entre snapshots inicial/final = bloco)
_CUMULATIVE_METRICS = (
    "home_cc","away_cc",
    "home_xg","away_xg",
    "home_xgot","away_xgot",
    "home_xa","away_xa",
    "home_shots","away_shots",
    "home_sot","away_sot",
)


def compute_block_delta(timeline: List[dict], block_start: int,
                          block_end: int) -> dict:
    """Retorna métricas PRODUZIDAS dentro do intervalo [block_start, block_end].

    Métricas cumulativas (CC, xG, xGOT, xA, shots, SOT) viram delta entre
    snapshot do fim e snapshot do início do bloco — assim "xG do bloco"
    é o xG criado NESSES 15 min, não o acumulado do jogo.

    Métricas de contexto (posse, toques_area) NÃO são cumulativas — pegamos
    o valor no snapshot do fim do bloco (estado atual).

    Returns dict tipo:
      {minute (=block_end), home_score (no fim), away_score, ...,
       home_cc (delta), home_cc_acc (cumulativo do jogo), ...,
       home_score_block (gols só nesse bloco), all_stats (do fim do bloco)}
    """
    if not timeline:
        return {"minute": block_end, "_block_start": block_start,
                "_block_end": block_end, "_no_data": True}

    tl = sorted(timeline, key=lambda s: s.get("minute", 0))

    # snapshot inicial = último snapshot com minute <= block_start
    s_start = None
    for s in tl:
        if s.get("minute", 0) <= block_start:
            s_start = s
        else:
            break
    # snapshot final = último com minute <= block_end
    s_end = None
    for s in tl:
        if s.get("minute", 0) <= block_end:
            s_end = s

    if s_end is None:
        s_end = tl[-1]
    if s_start is None:
        # primeiro bloco: tudo o que existe é "do bloco"
        s_start = {m: 0 for m in _CUMULATIVE_METRICS}
        s_start["home_score"] = 0; s_start["away_score"] = 0
        s_start["minute"] = 0

    block = {
        # "minute" representa o FIM do bloco — não o último snapshot
        # (importante pra cenários que dependem de minute >= X)
        "minute": block_end,
        "_actual_minute_end": s_end.get("minute", block_end),
        "_block_start": block_start,
        "_block_end": block_end,
        "home": s_end.get("home", ""),
        "away": s_end.get("away", ""),
        # Placar atual (no fim do bloco)
        "home_score": s_end.get("home_score", 0),
        "away_score": s_end.get("away_score", 0),
        # Placar acumulado (igual ao acima — fica explícito)
        "home_score_acc": s_end.get("home_score", 0),
        "away_score_acc": s_end.get("away_score", 0),
        # Gols feitos DENTRO desse bloco
        "home_score_block":
            s_end.get("home_score", 0) - s_start.get("home_score", 0),
        "away_score_block":
            s_end.get("away_score", 0) - s_start.get("away_score", 0),
        # Contexto (não-cumulativo) — pega do final
        "all_stats": s_end.get("all_stats", {}),
    }
    # Métricas cumulativas viram delta
    # NOTA: métricas cumulativas (xG, xGOT, CC, etc.) só CRESCEM ao longo do
    # jogo. Delta negativo é impossível fisicamente — sinaliza ajuste do
    # parser (Flashscore às vezes corrige métricas anteriormente medidas).
    # Clamp em zero pra evitar valores absurdos como "xGOT -0.09".
    for m in _CUMULATIVE_METRICS:
        v_end = s_end.get(m, 0) or 0
        v_start = s_start.get(m, 0) or 0
        try:
            delta = round(float(v_end) - float(v_start), 3)
            block[m] = max(0, delta)  # clamp em zero
        except Exception:
            block[m] = 0
        # Mantém acumulado disponível
        block[f"{m}_acc"] = v_end
    return block


def compute_derivatives(timeline: List[dict], *, current_minute: int) -> dict:
    """Calcula deltas/velocity/acceleration pra cada métrica funil.

    Returns dict:
      {
        "home_cc": {"delta_2m": .., "delta_15m": .., "delta_30m": ..,
                   "velocity": .., "acceleration": ..,
                   "inflection": "subindo|estavel|caindo"},
        ...
      }
    """
    if not timeline:
        return {m: {"delta_2m": 0, "delta_15m": 0, "delta_30m": 0,
                    "velocity": 0, "acceleration": 0,
                    "inflection": "indef"} for m in FUNNEL_METRICS}

    # Ordena por minuto
    timeline = sorted(timeline, key=lambda s: s.get("minute", 0))
    last = timeline[-1]
    last_min = last.get("minute", current_minute)

    def _snap_at_or_before(target_min: int) -> Optional[dict]:
        """Snapshot mais próximo de target_min, sem ultrapassar."""
        candidates = [s for s in timeline if s.get("minute", 0) <= target_min]
        return candidates[-1] if candidates else None

    out = {}
    for m in FUNNEL_METRICS:
        v_now = _value(last, m)
        s_2m  = _snap_at_or_before(last_min - 2)
        s_15m = _snap_at_or_before(last_min - 15)
        s_30m = _snap_at_or_before(last_min - 30)
        v_2m  = _value(s_2m, m)  if s_2m  else 0.0
        v_15m = _value(s_15m, m) if s_15m else 0.0
        v_30m = _value(s_30m, m) if s_30m else 0.0

        delta_2m  = round(v_now - v_2m, 3)
        delta_15m = round(v_now - v_15m, 3)
        delta_30m = round(v_now - v_30m, 3)
        velocity  = round(delta_15m / 15.0, 3) if delta_15m else 0.0

        # Acceleration: comparar velocity últimos 15min vs anteriores 15min
        v_30m_to_15m = _value(s_15m, m) - v_30m if (s_15m and s_30m) else 0.0
        prev_velocity = v_30m_to_15m / 15.0 if v_30m_to_15m else 0.0
        acceleration = round(velocity - prev_velocity, 3)

        # Inflection
        if delta_2m > 0 and acceleration > 0:
            inflection = "acelerando"
        elif delta_2m > 0 and acceleration <= 0:
            inflection = "subindo_desacelerando"
        elif delta_2m == 0:
            inflection = "estavel"
        else:
            inflection = "caindo"

        out[m] = {
            "value_now": v_now,
            "delta_2m":  delta_2m,
            "delta_15m": delta_15m,
            "delta_30m": delta_30m,
            "velocity":  velocity,
            "acceleration": acceleration,
            "inflection":   inflection,
        }
    return out
