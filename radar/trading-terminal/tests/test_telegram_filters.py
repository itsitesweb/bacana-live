"""
Teste E — Filtros Telegram conforme protocolo operacional.

Testa os 8 cenários obrigatórios:
  1. BLOQUEADO por NO_NEW_ENTRY_AFTER_83 → NÃO envia Telegram
  2. SCORE_KILLED_GAME sem posição aberta → NÃO envia Telegram
  3. MANUAL_REVIEW → NÃO envia Telegram (NEVER_SEND)
  4. ENTER_* → envia mensagem completa
  5. EXIT_* → envia mensagem urgente
  6. REDUCE_* → envia mensagem
  7. HOLD → NÃO envia
  8. NO_ACTION → NÃO envia
"""
import sys
import os
import tempfile
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import MatchState, DerivedVars, Decision
from src.telegram_client import TelegramClient


def make_cfg():
    return {
        "telegram": {
            "enabled": True,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "chat_id_env": "TELEGRAM_CHAT_ID",
            "simulation_tag": "",
            "send_info_messages": False,
            "send_hold_messages": False,
            "anti_spam_minutes": 5,
            "manual_review_cooldown_minutes": 30,
            "state_file": "",  # empty = default path (tests use in-memory)
        }
    }


def make_cfg_with_state_file(path):
    """Config with explicit state file for persistence tests."""
    cfg = make_cfg()
    cfg["telegram"]["state_file"] = path
    return cfg


def make_ms(**kwargs):
    defaults = {
        "match_id": "test_match_1",
        "home": "TeamA", "away": "TeamB",
        "home_score": 0, "away_score": 0,
        "minute": 45,
        "home_bc": 0, "away_bc": 0,
        "home_xgot": 0.0, "away_xgot": 0.0,
        "home_xg": 0.0, "away_xg": 0.0,
        "position_type": None,
        "last_signal_action": None,
        "last_signal_minute": 0,
    }
    defaults.update(kwargs)
    return MatchState(**defaults)


def make_derived(**kwargs):
    d = DerivedVars()
    for k, v in kwargs.items():
        setattr(d, k, v)
    return d


def make_decision(**kwargs):
    dec = Decision()
    for k, v in kwargs.items():
        setattr(dec, k, v)
    return dec


# ═══════════════════════════════════════════════════════════════
# Test 1: BLOQUEADO por NO_NEW_ENTRY_AFTER_83 → NÃO envia
# ═══════════════════════════════════════════════════════════════
def test_1_blocked_no_new_entry_after_83():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=85)
    dec = make_decision(
        recommended_action="BLOCKED",
        blocked_reason="NO_NEW_ENTRY_AFTER_83"
    )
    result = tg.should_send(dec, ms)
    assert result is False, "BLOCKED NO_NEW_ENTRY_AFTER_83 NÃO deve enviar Telegram"
    print("  ✅ Test 1: BLOCKED NO_NEW_ENTRY_AFTER_83 → silêncio")


# ═══════════════════════════════════════════════════════════════
# Test 2: SCORE_KILLED_GAME sem posição aberta → NÃO envia
# ═══════════════════════════════════════════════════════════════
def test_2_score_killed_game_no_position():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=70, home_score=4, away_score=0, position_type=None)
    dec = make_decision(
        recommended_action="BLOCKED",
        blocked_reason="SCORE_KILLED_GAME"
    )
    result = tg.should_send(dec, ms)
    assert result is False, "SCORE_KILLED_GAME sem posição NÃO deve enviar"
    print("  ✅ Test 2: SCORE_KILLED_GAME sem posição → silêncio")


# ═══════════════════════════════════════════════════════════════
# Test 3: MANUAL_REVIEW → NÃO envia Telegram (NEVER_SEND)
# ═══════════════════════════════════════════════════════════════
def test_3_manual_review_never_sends():
    """MANUAL_REVIEW está em NEVER_SEND — NUNCA envia Telegram."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="match_X", home="Essen", away="Furth")
    dec = make_decision(
        recommended_action="MANUAL_REVIEW",
        blocked_reason="zona mista 3x1 com xGOT ambíguo",
    )
    result = tg.should_send(dec, ms)
    assert result is False, "MANUAL_REVIEW NÃO deve enviar Telegram (NEVER_SEND)"

    # Também com posição aberta → AINDA NÃO envia
    ms2 = make_ms(match_id="match_X", home="Essen", away="Furth",
                  position_type="BACK")
    result2 = tg.should_send(dec, ms2)
    assert result2 is False, "MANUAL_REVIEW NÃO envia mesmo com posição aberta"

    # Também com SIGNAL_TURNED_AGAINST → AINDA NÃO envia
    dec2 = make_decision(
        recommended_action="MANUAL_REVIEW",
        blocked_reason="SIGNAL_TURNED_AGAINST",
    )
    result3 = tg.should_send(dec2, ms)
    assert result3 is False, "MANUAL_REVIEW NÃO envia independente do motivo"
    print("  ✅ Test 3: MANUAL_REVIEW → NEVER_SEND (3 variantes)")


# ═══════════════════════════════════════════════════════════════
# Test 4: ENTER_* → envia mensagem completa com copy padrão
# ═══════════════════════════════════════════════════════════════
def test_4_enter_sends_complete():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=42, home_bc=3, away_bc=0,
                 home_xgot=0.8, away_xgot=0.0)
    d = make_derived(
        dominant_team="home", dominant_bc=3, opponent_bc=0,
        dominant_xgot=0.8, opponent_xgot=0.0,
        total_bc=3, min_bc=0, match_bc_rate=10.0, team_bc_rate=10.0,
    )
    dec = make_decision(
        recommended_action="ENTER_BACK_T1_MAIN",
        confidence_tier="A",
        signal_valid_until=47,
        game_profile="UNILATERAL_BACK",
        market_target="BACK_DOMINANT_TEAM",
    )
    # should_send
    assert tg.should_send(dec, ms) is True, "ENTER_BACK_T1_MAIN deve enviar"
    # Format
    msg = tg.format_message(dec, ms, d)
    assert "ACTION | ENTRAR BACK" in msg, f"Falta 'ACTION | ENTRAR BACK' na msg"
    assert "Jogo: TeamA x TeamB" in msg, "Falta 'Jogo:'"
    assert "Mercado:" in msg, "Falta 'Mercado:'"
    assert "Comando:" in msg, "Falta 'Comando:'"
    assert "Motivo:" in msg, "Falta 'Motivo:'"
    assert "Válido até:" in msg, "Falta 'Válido até:'"
    print("  ✅ Test 4: ENTER_BACK_T1_MAIN → mensagem completa")
    print(f"     Copy:\n{_indent(msg)}")


# ═══════════════════════════════════════════════════════════════
# Test 5: EXIT_* → envia mensagem URGENT
# ═══════════════════════════════════════════════════════════════
def test_5_exit_sends_urgent():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=60, position_type="BACK", position_team="TeamA")
    d = make_derived(
        dominant_team="home", dominant_bc=3, opponent_bc=3,
        dominant_xgot=0.8, opponent_xgot=0.6,
        team_bc_since_entry=1, opponent_bc_since_entry=3,
    )
    dec = make_decision(
        recommended_action="EXIT_BACK",
        blocked_reason="ADV_3_CC",
    )
    assert tg.should_send(dec, ms) is True, "EXIT_BACK deve enviar"
    msg = tg.format_message(dec, ms, d)
    assert "URGENT" in msg, "EXIT deve ter URGENT"
    assert "FECHAR POSIÇÃO AGORA" in msg, "Falta comando de fechar"
    assert "Jogo:" in msg, "Falta 'Jogo:'"
    print("  ✅ Test 5: EXIT_BACK → mensagem URGENT")
    print(f"     Copy:\n{_indent(msg)}")


# ═══════════════════════════════════════════════════════════════
# Test 6: REDUCE_* → envia mensagem
# ═══════════════════════════════════════════════════════════════
def test_6_reduce_sends():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=65, position_type="OVER")
    d = make_derived(minutes_since_last_match_bc=17)
    dec = make_decision(recommended_action="REDUCE_OVER")
    assert tg.should_send(dec, ms) is True, "REDUCE_OVER deve enviar"
    msg = tg.format_message(dec, ms, d)
    assert "REDUZIR" in msg, "Falta 'REDUZIR'"
    assert "Comando:" in msg, "Falta 'Comando:'"
    print("  ✅ Test 6: REDUCE_OVER → envia")
    print(f"     Copy:\n{_indent(msg)}")


# ═══════════════════════════════════════════════════════════════
# Test 7: HOLD → NÃO envia
# ═══════════════════════════════════════════════════════════════
def test_7_hold_does_not_send():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=50, position_type="BACK")
    dec = make_decision(recommended_action="HOLD_BACK")
    assert tg.should_send(dec, ms) is False, "HOLD_BACK NÃO deve enviar"

    dec2 = make_decision(recommended_action="HOLD_OVER")
    assert tg.should_send(dec2, ms) is False, "HOLD_OVER NÃO deve enviar"

    dec3 = make_decision(recommended_action="HOLD_BACK_WITH_CAUTION")
    assert tg.should_send(dec3, ms) is False, "HOLD_BACK_WITH_CAUTION NÃO deve enviar"
    print("  ✅ Test 7: HOLD_* → silêncio (3 variantes)")


# ═══════════════════════════════════════════════════════════════
# Test 8: NO_ACTION → NÃO envia
# ═══════════════════════════════════════════════════════════════
def test_8_no_action_does_not_send():
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=30)
    dec = make_decision(recommended_action="NO_ACTION")
    assert tg.should_send(dec, ms) is False, "NO_ACTION NÃO deve enviar"
    print("  ✅ Test 8: NO_ACTION → silêncio")


# ═══════════════════════════════════════════════════════════════
# Testes extra de segurança
# ═══════════════════════════════════════════════════════════════
def test_extra_blocked_with_position_sends():
    """BLOCKED com posição aberta → DEVE enviar (risco operacional)."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=85, position_type="BACK")
    dec = make_decision(
        recommended_action="BLOCKED",
        blocked_reason="SCORE_KILLED_GAME"
    )
    result = tg.should_send(dec, ms)
    assert result is True, "BLOCKED com posição aberta DEVE enviar"
    print("  ✅ Extra: BLOCKED + posição aberta → envia")


def test_extra_signal_expired_without_prior():
    """SIGNAL_EXPIRED sem sinal anterior → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(last_signal_action=None)
    dec = make_decision(recommended_action="SIGNAL_EXPIRED")
    assert tg.should_send(dec, ms) is False
    print("  ✅ Extra: SIGNAL_EXPIRED sem sinal prévio → silêncio")


def test_extra_signal_expired_with_prior():
    """SIGNAL_EXPIRED com sinal anterior → envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(last_signal_action="ENTER_BACK_T1_MAIN", last_signal_minute=40)
    dec = make_decision(recommended_action="SIGNAL_EXPIRED")
    assert tg.should_send(dec, ms) is True
    print("  ✅ Extra: SIGNAL_EXPIRED com sinal prévio → envia")


def test_extra_enter_anti_spam_maintained():
    """ENTER repetido → SIGNAL_MAINTAINED (1 vez), depois SPAM_FILTERED."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="m1", home="Arsenal", away="Fulham")
    # First
    r1 = tg.check_anti_spam("m1", "ENTER_BACK_T1_MAIN", 40, "", ms=ms)
    assert r1 == "ENTER_BACK_T1_MAIN"
    # Repeat → SIGNAL_MAINTAINED
    r2 = tg.check_anti_spam("m1", "ENTER_BACK_T1_MAIN", 42, "", ms=ms)
    assert r2 == "SIGNAL_MAINTAINED"
    # Repeat again → SPAM_FILTERED (already sent maintained)
    r3 = tg.check_anti_spam("m1", "ENTER_BACK_T1_MAIN", 43, "", ms=ms)
    assert r3 == "SPAM_FILTERED"
    print("  ✅ Extra: ENTER anti-spam → maintained → filtered")


def test_extra_over_copy():
    """Over Premium copy tem ACTION | e Mercado:"""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=42, home_bc=2, away_bc=1)
    d = make_derived(
        dominant_team="home", dominant_bc=2, opponent_bc=1,
        dominant_xgot=0.5, opponent_xgot=0.3,
        total_bc=3, min_bc=1, match_bc_rate=10.0,
    )
    dec = make_decision(
        recommended_action="ENTER_OVER_PREMIUM",
        signal_valid_until=47,
    )
    msg = tg.format_message(dec, ms, d)
    assert "ACTION | ENTRAR OVER" in msg
    assert "Mercado:" in msg
    assert "Válido até:" in msg
    assert "Comando:" in msg
    print("  ✅ Extra: ENTER_OVER_PREMIUM copy padrão OK")


# ═══════════════════════════════════════════════════════════════
# Test simulation_tag: modo definitivo vs simulação
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# F) TESTES OBRIGATÓRIOS — ANTI-SPAM DEFINITIVO
# ═══════════════════════════════════════════════════════════════

def test_F1_manual_review_repeated_same_game_same_reason():
    """F1: MANUAL_REVIEW repetido mesmo jogo + mesmo motivo → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="essen_v_furth", home="RW Essen", away="Furth")
    r1 = tg.check_anti_spam("essen_v_furth", "MANUAL_REVIEW", 45,
                             "zona mista 3x1 com xGOT ambíguo", ms=ms)
    assert r1 == "MANUAL_REVIEW"
    r2 = tg.check_anti_spam("essen_v_furth", "MANUAL_REVIEW", 50,
                             "zona mista 3x1 com xGOT ambíguo", ms=ms)
    assert r2 == "SPAM_FILTERED", f"Repetido deveria ser filtrado, got {r2}"
    print("  ✅ F1: MANUAL_REVIEW repetido mesmo jogo+motivo → filtrado")


def test_F1b_manual_review_different_match_id_same_teams():
    """F1b: Mesmo MANUAL_REVIEW com match_id DIFERENTE mas mesmos times → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms1 = make_ms(match_id="FS_ABC123", home="RW Essen", away="Furth")
    ms2 = make_ms(match_id="FS_XYZ789", home="RW Essen", away="Furth")  # ID diferente!
    r1 = tg.check_anti_spam("FS_ABC123", "MANUAL_REVIEW", 1,
                             "zona mista 3x1 com xGOT ambíguo", ms=ms1)
    assert r1 == "MANUAL_REVIEW"
    # Mesmo jogo, match_id mudou → chave estável (home|away) deve filtrar
    r2 = tg.check_anti_spam("FS_XYZ789", "MANUAL_REVIEW", 1,
                             "zona mista 3x1 com xGOT ambíguo", ms=ms2)
    assert r2 == "SPAM_FILTERED", f"Match_id diferente mas mesmos times deveria filtrar, got {r2}"
    print("  ✅ F1b: match_id diferente + mesmos times → filtrado (chave estável)")


def test_F2_manual_review_within_30min():
    """F2: MANUAL_REVIEW repetido dentro de 30 min real → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="m1", home="TeamX", away="TeamY")
    tg.check_anti_spam("m1", "MANUAL_REVIEW", 10, "reason_a", ms=ms)
    # Immediately again (0 seconds later) → SPAM_FILTERED
    r = tg.check_anti_spam("m1", "MANUAL_REVIEW", 35, "reason_a", ms=ms)
    assert r == "SPAM_FILTERED", f"Dentro de 30 min real, got {r}"
    print("  ✅ F2: MANUAL_REVIEW dentro de 30 min real → filtrado")


def test_F3_manual_review_after_30min():
    """F3: MANUAL_REVIEW após 30 min real → pode enviar."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="m1", home="TeamX", away="TeamY")
    stable_key = tg._stable_key(ms)
    spam_key = f"{stable_key}|MANUAL_REVIEW|reason_a"
    # Simulate: registered 31 min ago
    past = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
    tg._last_signal[spam_key] = [past, False]
    r = tg.check_anti_spam("m1", "MANUAL_REVIEW", 41, "reason_a", ms=ms)
    assert r == "MANUAL_REVIEW", f"Após 30 min real deveria passar, got {r}"
    print("  ✅ F3: MANUAL_REVIEW após 30 min real → passa")


def test_F4_no_data_evolution():
    """F4: Mesmo jogo sem evolução por 2 scans → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="essen_v_furth", minute=45,
                 home_bc=3, away_bc=1,
                 home_xgot=0.5, away_xgot=0.3)
    dec = make_decision(recommended_action="MANUAL_REVIEW",
                        blocked_reason="zona mista")

    # Scan 1 → registra estado
    r1 = tg.check_stale_match(ms, dec)
    assert r1 == "", f"Primeiro scan deveria passar, got {r1}"

    # Scan 2 → dados idênticos → NO_DATA_EVOLUTION
    r2 = tg.check_stale_match(ms, dec)
    assert r2 == "NO_DATA_EVOLUTION", f"Scan idêntico deveria ser filtrado, got {r2}"
    print("  ✅ F4: Jogo sem evolução por 2 scans → filtrado")


def test_F5_stale_match():
    """F5: Jogo stale (minuto parado) → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(match_id="stale_game", minute=1,
                 home_score=1, away_score=0)
    dec = make_decision(recommended_action="MANUAL_REVIEW",
                        blocked_reason="test")

    # Scan 1 → registra
    r1 = tg.check_stale_match(ms, dec)
    assert r1 == "", f"Primeiro scan deveria passar, got {r1}"

    # Scan 2 → min 1 + placar > 0 repetido → STALE
    r2 = tg.check_stale_match(ms, dec)
    # Segundo scan com dados idênticos → NO_DATA_EVOLUTION
    # (stale check precisa de 2 scans consecutivos em min <= 1 com gol)
    assert r2 in ("STALE_MATCH", "NO_DATA_EVOLUTION"), f"Stale deveria ser filtrado, got {r2}"
    print("  ✅ F5: Jogo stale → filtrado")


def test_F6_minute1_score1_0_repeated():
    """F6: Minuto 1 + placar 1-0 repetido → STALE_MATCH."""
    tg = TelegramClient(make_cfg())
    ms1 = make_ms(match_id="rw_essen", minute=1,
                  home_score=1, away_score=0,
                  home_bc=3, away_bc=1)
    dec1 = make_decision(recommended_action="MANUAL_REVIEW",
                         blocked_reason="zona mista")
    # Scan 1
    tg.check_stale_match(ms1, dec1)

    # Scan 2 — mesmos dados básicos mas check stale detecta min1+gol repetido
    ms2 = make_ms(match_id="rw_essen", minute=1,
                  home_score=1, away_score=0,
                  home_bc=3, away_bc=1)
    dec2 = make_decision(recommended_action="MANUAL_REVIEW",
                         blocked_reason="zona mista")
    r = tg.check_stale_match(ms2, dec2)
    assert r == "STALE_MATCH", f"Min 1 + 1-0 repetido deveria ser STALE, got {r}"
    print("  ✅ F6: Minuto 1 + placar 1-0 repetido → STALE_MATCH")


def test_F7_no_new_entry_after_83():
    """F7: NO_NEW_ENTRY_AFTER_83 → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=85)
    dec = make_decision(recommended_action="BLOCKED",
                        blocked_reason="NO_NEW_ENTRY_AFTER_83")
    assert tg.should_send(dec, ms) is False
    print("  ✅ F7: NO_NEW_ENTRY_AFTER_83 → silêncio")


def test_F8_score_killed_no_position():
    """F8: SCORE_KILLED_GAME sem posição → NÃO envia."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=70, home_score=4, away_score=0, position_type=None)
    dec = make_decision(recommended_action="BLOCKED",
                        blocked_reason="SCORE_KILLED_GAME")
    assert tg.should_send(dec, ms) is False
    print("  ✅ F8: SCORE_KILLED_GAME sem posição → silêncio")


def test_F9_enter_back_sends():
    """F9: ENTER_BACK_T1_MAIN continua enviando."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=42)
    dec = make_decision(recommended_action="ENTER_BACK_T1_MAIN")
    assert tg.should_send(dec, ms) is True
    print("  ✅ F9: ENTER_BACK_T1_MAIN → envia")


def test_F10_enter_over_sends():
    """F10: ENTER_OVER_PREMIUM continua enviando."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=42)
    dec = make_decision(recommended_action="ENTER_OVER_PREMIUM")
    assert tg.should_send(dec, ms) is True
    print("  ✅ F10: ENTER_OVER_PREMIUM → envia")


def test_F11_exit_back_sends():
    """F11: EXIT_BACK continua enviando."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=60, position_type="BACK")
    dec = make_decision(recommended_action="EXIT_BACK")
    assert tg.should_send(dec, ms) is True
    print("  ✅ F11: EXIT_BACK → envia")


def test_F12_reduce_over_sends():
    """F12: REDUCE_OVER continua enviando."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=65, position_type="OVER")
    dec = make_decision(recommended_action="REDUCE_OVER")
    assert tg.should_send(dec, ms) is True
    print("  ✅ F12: REDUCE_OVER → envia")


def test_F13_lock_profit_sends():
    """F13: LOCK_PROFIT continua enviando."""
    tg = TelegramClient(make_cfg())
    ms = make_ms(minute=60, position_type="OVER")
    dec = make_decision(recommended_action="LOCK_PROFIT")
    assert tg.should_send(dec, ms) is True
    print("  ✅ F13: LOCK_PROFIT → envia")


def test_F_persist_state_survives_restart():
    """Reiniciar TelegramClient e tentar mesmo MANUAL_REVIEW → NÃO envia (estado em arquivo)."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        state_path = f.name
    try:
        # Client 1: envia MANUAL_REVIEW
        cfg1 = make_cfg_with_state_file(state_path)
        tg1 = TelegramClient(cfg1)
        ms = make_ms(match_id="persist_test", home="RW Essen", away="Furth")
        r1 = tg1.check_anti_spam("persist_test", "MANUAL_REVIEW", 1,
                                  "zona mista", ms=ms)
        assert r1 == "MANUAL_REVIEW", f"Primeiro deveria passar, got {r1}"

        # Client 2: NOVO TelegramClient (simula daemon restart)
        cfg2 = make_cfg_with_state_file(state_path)
        tg2 = TelegramClient(cfg2)
        r2 = tg2.check_anti_spam("persist_test", "MANUAL_REVIEW", 1,
                                  "zona mista", ms=ms)
        assert r2 == "SPAM_FILTERED", f"Após restart deveria filtrar, got {r2}"
        print("  ✅ F_persist: estado sobrevive restart do daemon")
    finally:
        os.unlink(state_path)


def test_simulation_tag_absent_in_definitive():
    """Modo definitivo (tag vazia) → mensagem NÃO tem [SIMULAÇÃO]."""
    cfg = make_cfg()
    cfg["telegram"]["simulation_tag"] = ""  # definitivo
    tg = TelegramClient(cfg)
    ms = make_ms(minute=42, home_bc=3, away_bc=0,
                 home_xgot=0.8, away_xgot=0.0)
    d = make_derived(
        dominant_team="home", dominant_bc=3, opponent_bc=0,
        dominant_xgot=0.8, opponent_xgot=0.0,
        total_bc=3, min_bc=0, match_bc_rate=10.0, team_bc_rate=10.0,
    )
    dec = make_decision(
        recommended_action="ENTER_BACK_T1_MAIN",
        confidence_tier="A",
        signal_valid_until=47,
    )
    msg = tg.format_message(dec, ms, d)
    assert "[SIMULAÇÃO]" not in msg, "Modo definitivo NÃO deve ter tag"
    assert "ACTION" in msg, "Deve ter ACTION na mensagem"
    print("  ✅ Simulation tag: modo definitivo → sem tag")


def test_simulation_tag_present_in_simulation():
    """Modo simulação (tag presente) → mensagem TEM [SIMULAÇÃO]."""
    cfg = make_cfg()
    cfg["telegram"]["simulation_tag"] = "[SIMULAÇÃO]"
    tg = TelegramClient(cfg)
    ms = make_ms(minute=42, home_bc=3, away_bc=0,
                 home_xgot=0.8, away_xgot=0.0)
    d = make_derived(
        dominant_team="home", dominant_bc=3, opponent_bc=0,
        dominant_xgot=0.8, opponent_xgot=0.0,
        total_bc=3, min_bc=0, match_bc_rate=10.0, team_bc_rate=10.0,
    )
    dec = make_decision(
        recommended_action="ENTER_BACK_T1_MAIN",
        confidence_tier="A",
        signal_valid_until=47,
    )
    msg = tg.format_message(dec, ms, d)
    assert "[SIMULAÇÃO]" in msg, "Modo simulação DEVE ter tag"
    print("  ✅ Simulation tag: modo simulação → com tag")


# ─── Helper ──────────────────────────────────────────────────
def _indent(text, prefix="       "):
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))


# ─── Runner ──────────────────────────────────────────────────
if __name__ == "__main__":
    # Set dummy env vars for TelegramClient init
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy")

    print("\n" + "=" * 60)
    print("  TESTE E — Filtros Telegram (protocolo operacional)")
    print("=" * 60)

    tests = [
        test_1_blocked_no_new_entry_after_83,
        test_2_score_killed_game_no_position,
        test_3_manual_review_never_sends,
        test_4_enter_sends_complete,
        test_5_exit_sends_urgent,
        test_6_reduce_sends,
        test_7_hold_does_not_send,
        test_8_no_action_does_not_send,
        test_extra_blocked_with_position_sends,
        test_extra_signal_expired_without_prior,
        test_extra_signal_expired_with_prior,
        test_extra_enter_anti_spam_maintained,
        test_extra_over_copy,
        # F) Testes obrigatórios anti-spam definitivo
        test_F1_manual_review_repeated_same_game_same_reason,
        test_F1b_manual_review_different_match_id_same_teams,
        test_F2_manual_review_within_30min,
        test_F3_manual_review_after_30min,
        test_F4_no_data_evolution,
        test_F5_stale_match,
        test_F6_minute1_score1_0_repeated,
        test_F7_no_new_entry_after_83,
        test_F8_score_killed_no_position,
        test_F9_enter_back_sends,
        test_F10_enter_over_sends,
        test_F11_exit_back_sends,
        test_F12_reduce_over_sends,
        test_F13_lock_profit_sends,
        test_F_persist_state_survives_restart,
        # Simulation tag
        test_simulation_tag_absent_in_definitive,
        test_simulation_tag_present_in_simulation,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1

    print("\n" + "-" * 60)
    print(f"  RESULTADO: {passed}/{len(tests)} passed, {failed} failed")
    if failed == 0:
        print("  ✅ TODOS OS TESTES PASSARAM")
    else:
        print(f"  ❌ {failed} TESTES FALHARAM")
    print("=" * 60)
