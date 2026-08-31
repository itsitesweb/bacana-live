"""
Decision Engine — Section 5 scan sequence of V1.2.

This is the orchestrator. Each scan:
  1. Compute derived vars
  2. Check blockers (Section 6)
  3. If position open → manage position (Sections 15-16)
  4. If no position → classify profile (Section 7) → evaluate entry rules
  5. Resolve conflicts (Section 18)
  6. Set Telegram metadata (Section 23)
"""
try:
    import yaml
    def _yaml_load(stream):
        return yaml.safe_load(stream)
except ImportError:
    def _yaml_load(stream):
        if hasattr(stream, "read"):
            text = stream.read()
        else:
            text = str(stream)
        lines = text.splitlines()
        root = {}
        stack = [(0, root)]
        for line in lines:
            code_part = line.split('#')[0].rstrip()
            if not code_part.strip():
                continue
            indent = len(code_part) - len(code_part.lstrip())
            trimmed = code_part.strip()
            if ':' not in trimmed:
                continue
            key, _, val = trimmed.partition(':')
            key = key.strip().strip('"\'')
            val = val.strip()
            while stack and stack[-1][0] >= indent and len(stack) > 1:
                stack.pop()
            current_dict = stack[-1][1]
            if not val:
                new_dict = {}
                current_dict[key] = new_dict
                stack.append((indent + 2, new_dict))
            else:
                if val.lower() == 'true':
                    parsed_val = True
                elif val.lower() == 'false':
                    parsed_val = False
                elif val.lower() in ('null', 'none'):
                    parsed_val = None
                elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    parsed_val = val[1:-1]
                else:
                    try:
                        if '.' in val:
                            parsed_val = float(val)
                        else:
                            parsed_val = int(val)
                    except ValueError:
                        parsed_val = val
                current_dict[key] = parsed_val
        return root

from pathlib import Path
from .models import MatchState, DerivedVars, Decision
from .utils import compute_derived, compute_signal_valid_until
from .profile_classifier import classify_profile
from .rules_back import evaluate_back
from .rules_over import evaluate_over
from .post_position import manage_position
from .telegram_formatter import enrich_telegram_metadata


def load_config(config_path: str = None) -> dict:
    """Load config.yaml."""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return _yaml_load(f)


def run_scan(ms: MatchState, cfg: dict = None) -> tuple:
    """
    Run a single scan decision cycle.

    Returns:
        (Decision, DerivedVars) tuple
    """
    if cfg is None:
        cfg = load_config()

    decision = Decision()
    mode = cfg.get("engine", {}).get("mode", "simulation")

    # === STEP 1-2: Validate data ===
    decision.add_trace(f"Scan: {ms.home} vs {ms.away}, min {ms.minute}, "
                       f"score {ms.home_score}-{ms.away_score}")

    if ms.scan_delay_seconds > cfg.get("engine", {}).get("data_delay_block_seconds", 180):
        decision.recommended_action = "BLOCKED"
        decision.blocked_reason = "DATA_DELAY"
        decision.add_trace(f"BLOCKED: data delay {ms.scan_delay_seconds}s > 180s")
        enrich_telegram_metadata(decision)
        return decision, DerivedVars()

    if not ms.data_is_valid:
        decision.recommended_action = "BLOCKED"
        decision.blocked_reason = "DATA_INVALID"
        decision.add_trace("BLOCKED: data_is_valid = False")
        enrich_telegram_metadata(decision)
        return decision, DerivedVars()

    # === STEP 3: Compute derived variables ===
    d = compute_derived(ms)
    decision.add_trace(
        f"Derived: dom={d.dominant_team}, bc={d.dominant_bc}x{d.opponent_bc}, "
        f"xgot={d.dominant_xgot:.2f}x{d.opponent_xgot:.2f}, "
        f"total_bc={d.total_bc}, rate_dom={d.team_bc_rate:.1f}, rate_match={d.match_bc_rate:.1f}"
    )

    # === STEP 3b: Data quality warning (Section 20) ===
    if ms.prev_home_bc >= 0 and ms.prev_away_bc >= 0:
        home_jump = ms.home_bc - ms.prev_home_bc
        away_jump = ms.away_bc - ms.prev_away_bc
        if home_jump >= 2 or away_jump >= 2:
            decision.add_trace(
                f"DATA_QUALITY_WARNING: BC saltou {home_jump}/{away_jump} "
                f"num scan (prev {ms.prev_home_bc}x{ms.prev_away_bc} → "
                f"now {ms.home_bc}x{ms.away_bc})"
            )

    # === STEP 4: Global blockers (Section 6) ===
    if _check_global_blockers(ms, d, decision, cfg):
        enrich_telegram_metadata(decision)
        return decision, d

    # === STEP 4b: SIGNAL_EXPIRED check (Section 23.11) ===
    if _check_signal_expired(ms, decision, cfg):
        enrich_telegram_metadata(decision)
        return decision, d

    # === STEP 5: If position open → manage ===
    if ms.position_type in ("BACK", "OVER"):
        decision.add_trace(f"Position open: {ms.position_type} on {ms.position_team}")
        manage_position(ms, d, decision, cfg)
        # After EXIT → set COOLDOWN state transition
        if decision.recommended_action in ("EXIT_BACK", "EXIT_OVER"):
            cooldown_min = cfg.get("engine", {}).get("cooldown_minutes_after_exit", 5)
            decision.new_state = "COOLDOWN"
            decision.add_trace(f"State → COOLDOWN until min {ms.minute + cooldown_min}")
        enrich_telegram_metadata(decision)
        return decision, d

    # === STEP 6: Classify profile ===
    decision.game_profile = classify_profile(ms, d, decision, cfg)

    if decision.game_profile == "NO_TRADE":
        decision.recommended_action = "NO_ACTION"
        decision.add_trace("No trade signal")
        enrich_telegram_metadata(decision)
        return decision, d

    # === STEP 6b: Emit explicit block reasons from profile rejection ===
    # Se estamos no window 76-83 e LATE_LIMIT foi rejeitado, emitir blocked_reason
    gl_cfg = cfg.get("over", {}).get("gol_limite", {})
    if (gl_cfg.get("min_minute", 76) <= ms.minute <= gl_cfg.get("max_minute", 83)
        and d.total_bc >= gl_cfg.get("min_total_bc", 7)
        and d.min_bc >= gl_cfg.get("min_min_bc", 2)):
        # Tem CC suficiente para Gol Limite mas algo falhou
        if d.score_diff == 0:
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "DRAW_BLOCKS_GOL_LIMITE"
            decision.add_trace("BLOCKED: empate invalida Over Gol Limite")
            enrich_telegram_metadata(decision)
            return decision, d
        if d.minutes_since_last_match_bc > gl_cfg.get("max_minutes_since_last_bc", 12):
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "LAST_BC_TOO_OLD"
            decision.add_trace(f"BLOCKED: ultima CC ha {d.minutes_since_last_match_bc}min > 12")
            enrich_telegram_metadata(decision)
            return decision, d

    # === STEP 7: Evaluate entry rules ===
    # Try Back first for UNILATERAL_BACK and MIXED
    back_found = False
    over_found = False

    if decision.game_profile in ("UNILATERAL_BACK", "MIXED"):
        back_found = evaluate_back(ms, d, decision, cfg)

    if not back_found and decision.game_profile in ("BILATERAL_OVER", "MIXED", "LATE_LIMIT"):
        # ─── ANTI-REENTRY OVER: bloquear se total_bc não aumentou desde o último EXIT ──
        # Após EXIT_OVER/LOCK_PROFIT, total_bc_at_exit é salvo no state.
        # Nova entrada Over só pode ocorrer se houver nova CC desde o exit
        # (total_bc atual > total_bc_at_exit). Sem isso, é entrada repetitiva
        # no mesmo cenário que já saiu.
        if ms.total_bc_at_exit > 0 and d.total_bc <= ms.total_bc_at_exit:
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "NO_NEW_BC_SINCE_OVER_EXIT"
            decision.add_trace(
                f"BLOCKED Over re-entry: total_bc={d.total_bc} <= "
                f"total_bc_at_exit={ms.total_bc_at_exit} (sem nova CC desde o exit)"
            )
            enrich_telegram_metadata(decision)
            return decision, d
        over_found = evaluate_over(ms, d, decision, cfg)

    if not back_found and not over_found:
        decision.recommended_action = "NO_ACTION"
        decision.add_trace(f"Profile {decision.game_profile} but no rule matched")

    # === STEP 8: Signal validity ===
    if decision.recommended_action.startswith("ENTER_"):
        max_min = cfg.get("engine", {}).get("max_entry_minute", 83)
        gl_min = cfg.get("engine", {}).get("signal_valid_minutes_gol_limite", 2)
        def_min = cfg.get("engine", {}).get("signal_valid_minutes_default", 5)
        decision.signal_valid_until = compute_signal_valid_until(
            decision.recommended_action, ms.minute, max_min, gl_min, def_min
        )

    # === STEP 9: Signal repeat check ===
    cooldown_min = cfg.get("engine", {}).get("signal_repeat_cooldown_minutes", 5)
    if (decision.recommended_action == ms.last_signal_action
        and ms.minute - ms.last_signal_minute < cooldown_min
        and decision.recommended_action != "NO_ACTION"):
        decision.add_trace(f"Signal repeat suppressed ({decision.recommended_action}, "
                           f"last at min {ms.last_signal_minute})")
        decision.recommended_action = "SIGNAL_MAINTAINED"

    # === STEP 10: Telegram metadata ===
    enrich_telegram_metadata(decision)

    return decision, d


def _check_global_blockers(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Section 6: Global blockers. Returns True if blocked."""

    # Cooldown check (Section 19.2: 4-6 min OU até nova CC surgir)
    if ms.state == "COOLDOWN" and ms.minute < ms.cooldown_until_minute:
        # Cooldown liberta se surgiu nova CC (delta detection)
        new_cc = (ms.prev_home_bc >= 0 and ms.prev_away_bc >= 0
                  and (ms.home_bc > ms.prev_home_bc or ms.away_bc > ms.prev_away_bc))
        if new_cc:
            decision.add_trace("COOLDOWN libertado: nova CC detectada")
        else:
            decision.recommended_action = "COOLDOWN"
            decision.add_trace(f"COOLDOWN until min {ms.cooldown_until_minute}")
            return True

    # No position open — check entry blockers
    if ms.position_type is None:

        # Minute > 83: no new entry
        max_entry = cfg.get("engine", {}).get("max_entry_minute", 83)
        if ms.minute > max_entry:
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "NO_NEW_ENTRY_AFTER_83"
            decision.add_trace(f"BLOCKED: minute {ms.minute} > {max_entry}")
            return True

        # V1.2 Ajuste 7: Signal turned against
        threshold = cfg.get("score", {}).get("mixed_zone_opponent_xgot_threshold", 0.4)
        if d.opponent_bc_changed_since_last_scan and d.opponent_xgot >= threshold:
            decision.recommended_action = "MANUAL_REVIEW"
            decision.blocked_reason = "SIGNAL_TURNED_AGAINST"
            decision.add_trace(
                f"BLOCKED: opponent CC changed this scan + xgot={d.opponent_xgot} >= {threshold}"
            )
            return True

        # Section 6: NO_NEW_OVER_AFTER_75 — bloqueia Over novo após minuto 75
        # (exceto LATE_LIMIT que tem regra própria até 83)
        max_over = cfg.get("engine", {}).get("max_over_entry_minute", 75)
        if ms.minute > max_over:
            # Não bloquear aqui incondicionalmente — o profile classifier
            # já redireciona para LATE_LIMIT se aplicável.
            # Este blocker impede Over normal (Premium/Bilateral/Small).
            # LATE_LIMIT tem max_minute=83 na regra própria.
            decision.add_trace(f"Note: minute {ms.minute} > {max_over}, Over normal bloqueado")

        # Section 6: Score diff >= 3 bloqueia novas entradas (jogo morto)
        if d.score_diff >= cfg.get("post_over", {}).get("exit_score_diff", 3):
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "SCORE_KILLED_GAME"
            decision.add_trace(f"BLOCKED: score_diff={d.score_diff} >= 3, jogo morto")
            return True

    return False


def _check_signal_expired(ms: MatchState, decision: Decision, cfg: dict) -> bool:
    """Section 23.11: Se minuto > signal_valid_until e sem posição aberta, sinal expirou."""
    if (ms.last_signal_action
        and ms.last_signal_action.startswith("ENTER_")
        and ms.position_type is None
        and ms.last_signal_minute > 0):

        # Calcular signal_valid_until do sinal anterior
        max_min = cfg.get("engine", {}).get("max_entry_minute", 83)
        gl_min = cfg.get("engine", {}).get("signal_valid_minutes_gol_limite", 2)
        def_min = cfg.get("engine", {}).get("signal_valid_minutes_default", 5)
        prev_valid_until = compute_signal_valid_until(
            ms.last_signal_action, ms.last_signal_minute, max_min, gl_min, def_min
        )

        if ms.minute > prev_valid_until:
            decision.recommended_action = "SIGNAL_EXPIRED"
            decision.signal_valid_until = prev_valid_until
            decision.add_trace(
                f"SIGNAL_EXPIRED: {ms.last_signal_action} expirou "
                f"(valid_until={prev_valid_until}, now={ms.minute})"
            )
            return True

    return False
