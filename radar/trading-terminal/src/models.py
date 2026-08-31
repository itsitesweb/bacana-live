"""
Data models for the Trading Terminal Decision Engine V1.2.

All variables match the V1.2 specification document exactly.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class MatchState:
    """Raw + derived state of a match at a given scan moment."""

    # --- Identity ---
    match_id: str = ""
    home: str = ""
    away: str = ""
    league: str = ""
    country: str = ""

    # --- Raw data (Flashscore) ---
    minute: int = 0
    home_score: int = 0
    away_score: int = 0
    home_bc: int = 0
    away_bc: int = 0
    home_xgot: float = 0.0
    away_xgot: float = 0.0
    home_red_cards: int = 0
    away_red_cards: int = 0
    home_sot: int = 0
    away_sot: int = 0
    home_shots: int = 0   # v3.1 — total de finalizações (Rota B)
    away_shots: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0
    # Additional parsed stats for Dashboard
    home_corners: int = 0
    away_corners: int = 0
    home_possession: int = 50
    away_possession: int = 50
    home_dangerous_attacks: int = 0
    away_dangerous_attacks: int = 0
    home_attacks: int = 0
    away_attacks: int = 0
    home_shots_off_target: int = 0
    away_shots_off_target: int = 0
    home_blocked_shots: int = 0
    away_blocked_shots: int = 0
    home_fouls: int = 0
    away_fouls: int = 0
    home_yellow_cards: int = 0
    away_yellow_cards: int = 0
    home_saves: int = 0
    away_saves: int = 0
    # v3.2 — xA (Quádrupla: CC + xG + xGOT + xA)
    home_xa: float = 0.0
    away_xa: float = 0.0
    # v3.2 — Bag de todas as outras métricas pra leitura contextual
    # (toques área, defesas goleiro, escanteios, cartões, faltas, etc).
    # Chave = label (português Flashscore), valor = (home, away) como string|float
    all_stats: dict = field(default_factory=dict)

    # --- Optional "raw" snapshot: None = ausente no feed; 0.0 = zero real.
    # Campos legacy acima continuam sendo float (0.0 fallback) pra não
    # quebrar a regra antiga. Os Optional aqui são consumidos pela
    # TRINCA/Turbo para distinguir ausência de dado vs valor real zero.
    home_xgot_raw: Optional[float] = None
    away_xgot_raw: Optional[float] = None
    home_xg_raw:   Optional[float] = None
    away_xg_raw:   Optional[float] = None
    home_bc_raw:   Optional[int]   = None
    away_bc_raw:   Optional[int]   = None
    home_sot_raw:  Optional[int]   = None
    away_sot_raw:  Optional[int]   = None
    home_shots_raw: Optional[int]  = None
    away_shots_raw: Optional[int]  = None

    # --- Scan metadata ---
    scan_delay_seconds: int = 0
    data_is_valid: bool = True

    # --- Status textual original do Flashscore (pré-parsing de minuto) ---
    # Ex.: "2º tempo56:21", "TERMINADO", "INTERVALO", "Adiado", "Suspended",
    # "90+3'", "1st Half 23:45". Usado pelo filtro is_live_match() no
    # live_daemon para distinguir live de finished/scheduled/suspended/cancelled
    # antes de chamar a regra do Código 3:1.
    status_raw: str = ""

    # --- Previous scan state (for delta detection) ---
    # Set to -1 = "no previous scan data available"
    prev_home_bc: int = -1
    prev_away_bc: int = -1
    prev_home_score: int = -1
    prev_away_score: int = -1

    # --- CC timing (detected by delta between scans) ---
    minute_of_last_home_bc: int = 0
    minute_of_last_away_bc: int = 0
    minute_of_last_match_bc: int = 0

    # --- Position state (if any) ---
    position_type: Optional[str] = None       # "BACK" or "OVER" or None
    position_team: Optional[str] = None       # which team was backed
    entry_minute: int = 0
    entry_signal_type: str = ""
    entry_tier: str = ""
    team_bc_at_entry: int = 0
    opponent_bc_at_entry: int = 0
    team_xgot_at_entry: float = 0.0
    opponent_xgot_at_entry: float = 0.0
    target_over_line: float = 0.0

    # --- Signal repeat control ---
    last_signal_action: str = ""
    last_signal_minute: int = 0

    # --- Engine state ---
    state: str = "IDLE"  # IDLE, WATCHING_BACK, WATCHING_OVER, POSITION_BACK,
                         # POSITION_OVER, COOLDOWN, MANUAL_REVIEW, BLOCKED, COMPLETED
    cooldown_until_minute: int = 0

    # --- Anti-reentry pós-exit ---
    # total_bc no momento do último EXIT/LOCK. 0 = sem exit registrado.
    # Quando > 0, bloqueia nova entrada Over se total_bc_atual <= total_bc_at_exit.
    # Reset para 0 quando uma nova entrada é permitida (CC apareceu desde o exit).
    total_bc_at_exit: int = 0


@dataclass
class DerivedVars:
    """All derived variables computed from MatchState (Section 3.2 V1.2)."""

    dominant_team: Optional[str] = None   # "home", "away", or None (tied CC)
    dominant_bc: int = 0
    opponent_bc: int = 0
    dominant_xgot: float = 0.0
    opponent_xgot: float = 0.0
    dominant_score: int = 0
    opponent_score: int = 0

    total_bc: int = 0
    min_bc: int = 0
    max_bc: int = 0
    gap_bc: int = 0

    team_bc_rate: float = 999.0
    match_bc_rate: float = 999.0

    score_diff: int = 0
    total_goals: int = 0
    bts: bool = False

    score_allows_attack: object = False    # True, False, or "CAUTION"
    score_allows_goals: bool = False
    score_allows_late_goal_limit: bool = False

    # Red card booleans (V1.2 standardized names)
    red_card_against_dominant: bool = False
    red_card_against_backed_team: bool = False
    game_killing_red_card: bool = False

    # CC since entry (post-position)
    team_bc_since_entry: int = 0
    opponent_bc_since_entry: int = 0
    team_xgot_since_entry: float = 0.0

    # Timing
    minutes_since_team_last_bc: int = 999
    minutes_since_last_match_bc: int = 999

    # Delta detection (V1.2 Ajuste 7)
    opponent_bc_changed_since_last_scan: bool = False

    # Over post-position
    over_already_won: bool = False

    # CC tied
    cc_tied: bool = False


@dataclass
class Decision:
    """Output of the decision engine for a single scan."""

    game_profile: str = "NO_TRADE"
    recommended_action: str = "NO_ACTION"
    market_target: str = ""
    alternative_market: str = ""
    confidence_tier: str = ""
    blocked_reason: str = ""
    signal_valid_until: int = 0

    # Telegram protocol (Section 23)
    operator_instruction: str = ""
    message_severity: str = "INFO"        # INFO, WATCH, ACTION, URGENT, BLOCKED, EXPIRED
    operator_action_required: bool = False
    telegram_priority: str = "LOW"        # LOW, NORMAL, HIGH, CRITICAL

    target_over_line: float = 0.0

    # Trace for debugging
    decision_trace: List[str] = field(default_factory=list)
    rejected_rules: List[str] = field(default_factory=list)

    # State transition
    new_state: str = ""

    def add_trace(self, msg: str):
        self.decision_trace.append(msg)

    def add_rejected(self, rule: str, reason: str):
        self.rejected_rules.append(f"{rule}: {reason}")
