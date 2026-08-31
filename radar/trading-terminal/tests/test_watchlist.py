"""
Testes do build_watchlist (src/watchlist.py).

Cobre:
  W1. Tier 0 (posição aberta) entra sempre — mesmo com max_size=0.
  W2. Tier 0 ignora stale_until E no_stats_until.
  W3. ENTER recente (dentro de anti_spam) entra no Tier 0.
  W4. ENTER antigo (fora do anti_spam) NÃO entra no Tier 0.
  W5. Tier 1 (janela + BC>0) respeita stale_until.
  W6. Tier 1 (janela + BC>0) respeita no_stats_until (AJUSTE OBRIGATÓRIO).
  W7. Tier 2 só com ever_loaded_stats.
  W8. Tier 3 round-robin (last_scanned_at ASC, never_scanned primeiro).
  W9. max_size respeitado quando não há Tier 0.
  W10. tier3_reserved garante slots mínimos pro Tier 3.
  W11. Se Tier 3 esgotou, slots reservados voltam pra Tier 1+2.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.catalog import Catalog
from src.watchlist import build_watchlist


def _make_catalog(games: list) -> Catalog:
    """Helper: cria Catalog populado com `games` (lista de dicts representando entries)."""
    cat = Catalog(persist_path=None)
    for g in games:
        mid = g["match_id"]
        cat._games[mid] = {
            "match_id": mid,
            "url": g.get("url", f"http://x/{mid}/"),
            "first_seen_at": g.get("first_seen_at", "2026-01-01T00:00:00+00:00"),
            "last_seen_at": g.get("last_seen_at", "2026-01-01T00:00:00+00:00"),
            "last_scanned_at": g.get("last_scanned_at"),
            "last_minute": g.get("last_minute"),
            "last_score": g.get("last_score"),
            "ever_loaded_stats": g.get("ever_loaded_stats", False),
            "no_stats_count": g.get("no_stats_count", 0),
            "no_stats_until": g.get("no_stats_until"),
            "last_stale_at": g.get("last_stale_at"),
            "stale_until": g.get("stale_until"),
            "has_open_position": g.get("has_open_position", False),
            "last_signal_action": g.get("last_signal_action", ""),
            "last_signal_minute": g.get("last_signal_minute", 0),
            "last_bc_sum": g.get("last_bc_sum", 0),
            "finished_or_not_live": g.get("finished_or_not_live", False),
            "finished_or_not_live_at": g.get("finished_or_not_live_at"),
            "finished_or_not_live_until": g.get("finished_or_not_live_until"),
            "not_live_reason": g.get("not_live_reason", ""),
            "is_premium": g.get("is_premium", False),
            "premium_reason": g.get("premium_reason", ""),
            "premium_level": g.get("premium_level", "NONE"),
            "premium_league_name": g.get("premium_league_name", ""),
            "premium_country": g.get("premium_country", ""),
            "league_meta_raw": g.get("league_meta_raw", {}),
        }
    return cat


_NOW = datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
_FUTURE = (_NOW + timedelta(minutes=10)).isoformat()
_PAST = (_NOW - timedelta(minutes=10)).isoformat()


class TestWatchlist(unittest.TestCase):

    def test_W1_tier0_position_always_included_even_with_max_zero(self):
        cat = _make_catalog([
            {"match_id": "FS_pos", "has_open_position": True, "last_minute": 50, "last_bc_sum": 3},
            {"match_id": "FS_other", "last_minute": 50, "last_bc_sum": 3},
        ])
        result = build_watchlist(cat, max_size=0, tier3_reserved=0, now=_NOW)
        self.assertIn("FS_pos", result)
        # max_size=0 não impede Tier 0
        self.assertEqual(result, ["FS_pos"])

    def test_W2_tier0_ignores_stale_and_no_stats(self):
        cat = _make_catalog([
            {"match_id": "FS_pos_stale", "has_open_position": True,
             "last_minute": 50, "last_bc_sum": 0,
             "stale_until": _FUTURE, "no_stats_until": _FUTURE},
        ])
        result = build_watchlist(cat, max_size=15, now=_NOW)
        self.assertIn("FS_pos_stale", result,
                      "Tier 0 deve incluir mesmo com stale/no_stats ativos")

    def test_W3_recent_enter_included_in_tier0(self):
        cat = _make_catalog([
            {"match_id": "FS_recent", "last_signal_action": "ENTER_BACK_T1_MAIN",
             "last_signal_minute": 40, "last_minute": 42,
             "last_bc_sum": 0, "last_scanned_at": "z"},
        ])
        result = build_watchlist(cat, max_size=15, anti_spam_minutes=5, now=_NOW)
        self.assertIn("FS_recent", result)

    def test_W4_old_enter_NOT_in_tier0(self):
        # Sinal foi no min 40, agora minuto é 60 → fora da anti_spam window de 5
        cat = _make_catalog([
            {"match_id": "FS_old", "last_signal_action": "ENTER_BACK_T1_MAIN",
             "last_signal_minute": 40, "last_minute": 60,
             "last_bc_sum": 0, "last_scanned_at": "z"},
        ])
        result = build_watchlist(cat, max_size=15, anti_spam_minutes=5,
                                  tier3_reserved=0, now=_NOW)
        # Como bc_sum=0 e ever_loaded_stats=False, cai em Tier 3 (não Tier 0)
        # Garantir que apareça mas NÃO no topo (Tier 0)
        self.assertIn("FS_old", result)

    def test_W5_tier1_respects_stale(self):
        cat = _make_catalog([
            {"match_id": "FS_stale", "last_minute": 50, "last_bc_sum": 3,
             "stale_until": _FUTURE},
            {"match_id": "FS_ok", "last_minute": 50, "last_bc_sum": 3},
        ])
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        self.assertNotIn("FS_stale", result, "stale ativo deve excluir do Tier 1")
        self.assertIn("FS_ok", result)

    def test_W6_tier1_respects_no_stats(self):
        """AJUSTE OBRIGATÓRIO: Tier 1 deve respeitar no_stats_until ativo."""
        cat = _make_catalog([
            {"match_id": "FS_nostats", "last_minute": 50, "last_bc_sum": 3,
             "no_stats_until": _FUTURE},
            {"match_id": "FS_ok", "last_minute": 50, "last_bc_sum": 3},
        ])
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        self.assertNotIn("FS_nostats", result,
                         "no_stats ativo deve excluir do Tier 1 (ajuste obrigatório)")
        self.assertIn("FS_ok", result)

    def test_W7_tier2_requires_ever_loaded_stats(self):
        cat = _make_catalog([
            # Janela ok, sem BC, mas nunca carregou stats → vai pra Tier 3
            {"match_id": "FS_never", "last_minute": 50, "last_bc_sum": 0,
             "ever_loaded_stats": False, "last_scanned_at": ""},
            # Janela ok, sem BC, já carregou stats → Tier 2
            {"match_id": "FS_loaded", "last_minute": 50, "last_bc_sum": 0,
             "ever_loaded_stats": True, "last_scanned_at": "zzz"},
        ])
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        # Ambos podem entrar; mas FS_loaded vem antes (Tier 2 > Tier 3)
        idx_loaded = result.index("FS_loaded")
        idx_never = result.index("FS_never")
        self.assertLess(idx_loaded, idx_never,
                        "Tier 2 (FS_loaded) deve vir antes de Tier 3 (FS_never)")

    def test_W8_tier3_round_robin_never_scanned_first(self):
        # Jogos fora da janela operacional → vão pra Tier 3
        cat = _make_catalog([
            {"match_id": "FS_a", "last_minute": 5, "last_scanned_at": "2026-05-22T19:00:00+00:00"},
            {"match_id": "FS_b", "last_minute": 5, "last_scanned_at": ""},  # nunca escaneado
            {"match_id": "FS_c", "last_minute": 5, "last_scanned_at": "2026-05-22T19:30:00+00:00"},
        ])
        result = build_watchlist(cat, max_size=15, tier3_reserved=15, now=_NOW)
        # FS_b nunca escaneado deve vir primeiro
        self.assertEqual(result[0], "FS_b")
        # FS_a (escaneado 19:00) vem antes de FS_c (19:30)
        self.assertLess(result.index("FS_a"), result.index("FS_c"))

    def test_W9_max_size_respected_without_tier0(self):
        # 5 jogos Tier 1
        games = [{"match_id": f"FS_t1_{i}", "last_minute": 40, "last_bc_sum": 2}
                 for i in range(5)]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=3, tier3_reserved=0, now=_NOW)
        self.assertEqual(len(result), 3)

    def test_W10_tier3_reserved_slots(self):
        # 10 jogos Tier 1, 5 jogos Tier 3 (fora da janela)
        games = []
        for i in range(10):
            games.append({"match_id": f"FS_t1_{i}", "last_minute": 40, "last_bc_sum": 2})
        for i in range(5):
            games.append({"match_id": f"FS_t3_{i}", "last_minute": 5,
                          "last_scanned_at": ""})
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=10, tier3_reserved=3, now=_NOW)
        self.assertEqual(len(result), 10)
        # Pelo menos 3 slots foram pra Tier 3
        tier3_count = sum(1 for mid in result if mid.startswith("FS_t3_"))
        self.assertGreaterEqual(tier3_count, 3,
                                f"Esperado >= 3 do Tier 3 reservados, veio {tier3_count}")

    def test_W13_finished_or_not_live_excluded_even_with_position(self):
        """Jogo marcado como finished_or_not_live NUNCA entra na watchlist,
        nem mesmo como Tier 0 (jogo terminado não tem posição operacional)."""
        games = [
            # Jogo "finalizado" no catalog
            {"match_id": "FS_done", "last_minute": 90, "last_bc_sum": 2,
             "ever_loaded_stats": True, "finished_or_not_live": True,
             "finished_or_not_live_until": _FUTURE,
             "has_open_position": True},  # tenta forçar Tier 0
            # Jogo limpo, deve entrar
            {"match_id": "FS_ok", "last_minute": 50, "last_bc_sum": 2,
             "ever_loaded_stats": True},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        self.assertNotIn("FS_done", result,
                          "Jogo finished_or_not_live NÃO pode entrar na watchlist")
        self.assertIn("FS_ok", result)

    def test_W14_finished_TTL_expired_returns_to_eligibility(self):
        """Após TTL de finished, jogo volta à elegibilidade normal."""
        games = [
            {"match_id": "FS_done", "last_minute": 50, "last_bc_sum": 2,
             "ever_loaded_stats": True, "finished_or_not_live": True,
             # TTL no PASSADO — expirou
             "finished_or_not_live_until": _PAST},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        self.assertIn("FS_done", result,
                       "TTL expirado deve liberar o jogo de volta")

    def test_W12_no_stats_active_excluded_from_all_tiers(self):
        """Ajuste pós-v1.1: jogos em backoff de no_stats NÃO entram em Tier 1/2/3,
        liberando slots da watchlist pra jogos com stats reais."""
        # 5 jogos em backoff ativo, 3 jogos com stats e CC
        games = []
        for i in range(5):
            games.append({
                "match_id": f"FS_back_{i}",
                "last_minute": 50,
                "last_bc_sum": 2,
                "ever_loaded_stats": True,
                "no_stats_until": _FUTURE,  # backoff ativo
            })
        for i in range(3):
            games.append({
                "match_id": f"FS_ok_{i}",
                "last_minute": 50,
                "last_bc_sum": 2,
                "ever_loaded_stats": True,
            })
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=0, now=_NOW)
        # Apenas os 3 OK entram. Watchlist menor que 15 é OK (qualidade > quantidade).
        self.assertEqual(len(result), 3,
                         f"Watchlist deve ter só 3 (FS_ok_*). Veio: {result}")
        for mid in result:
            self.assertTrue(mid.startswith("FS_ok_"))

    def test_W11_tier3_empty_falls_back_to_tier1(self):
        # 12 jogos Tier 1, 0 jogos Tier 3
        games = [{"match_id": f"FS_t1_{i}", "last_minute": 40, "last_bc_sum": 2}
                 for i in range(12)]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=10, tier3_reserved=3, now=_NOW)
        # Sem Tier 3, todos os slots viram Tier 1
        self.assertEqual(len(result), 10)
        for mid in result:
            self.assertTrue(mid.startswith("FS_t1_"))

    # ────────────────────────────────────────────────────────────────────
    # TIER 3 FIFO — jogo descoberto antes é escaneado antes
    # (faxina remove jogos não vistos há >30min)
    # ────────────────────────────────────────────────────────────────────
    def test_W12_FIFO_oldest_never_scanned_first(self):
        """Tier 3 é FIFO: jogo nunca-escaneado descoberto ANTES entra antes
        do mais novo. Resolve starvation de jogos importantes por fluxo
        contínuo de novos descobertos."""
        games = [
            {"match_id": "FS_BAYERN_EARLY",
             "first_seen_at": "2026-05-22T19:00:00+00:00",
             "last_seen_at":  "2026-05-22T19:30:00+00:00",
             "last_scanned_at": None, "last_minute": None},
            {"match_id": "FS_NEW_LATER_1",
             "first_seen_at": "2026-05-22T19:25:00+00:00",
             "last_seen_at":  "2026-05-22T19:30:00+00:00",
             "last_scanned_at": None, "last_minute": None},
            {"match_id": "FS_NEW_LATER_2",
             "first_seen_at": "2026-05-22T19:28:00+00:00",
             "last_seen_at":  "2026-05-22T19:30:00+00:00",
             "last_scanned_at": None, "last_minute": None},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=15,
                                  now=datetime(2026, 5, 22, 19, 31, 0, tzinfo=timezone.utc))
        # FIFO: BAYERN_EARLY (descoberto primeiro) vem ANTES dos NEW_LATER
        idx_bayern = result.index("FS_BAYERN_EARLY")
        idx_n1 = result.index("FS_NEW_LATER_1")
        idx_n2 = result.index("FS_NEW_LATER_2")
        self.assertLess(idx_bayern, idx_n1,
                        f"Bayern (early) deve vir antes de FS_NEW_LATER_1. Order: {result}")
        self.assertLess(idx_bayern, idx_n2,
                        "Bayern (early) deve vir antes de FS_NEW_LATER_2")
        self.assertLess(idx_n1, idx_n2,
                        "Entre os novos, descoberto antes vem primeiro (FIFO)")

    def test_W13_scanned_order_preserved_after_never_scanned(self):
        """Jogos escaneados vêm DEPOIS dos nunca-escaneados, ordenados por
        last_scanned_at ASC (mais antigo escaneado primeiro = round-robin)."""
        games = [
            {"match_id": "FS_scanned_new",
             "last_scanned_at": "2026-05-22T19:00:00+00:00",
             "first_seen_at": "2026-05-22T19:00:00+00:00",
             "last_minute": None},
            {"match_id": "FS_scanned_old",
             "last_scanned_at": "2026-05-22T15:00:00+00:00",
             "first_seen_at": "2026-05-22T15:00:00+00:00",
             "last_minute": None},
            {"match_id": "FS_never_recent",
             "last_scanned_at": None,
             "first_seen_at": "2026-05-22T19:30:00+00:00",
             "last_minute": None},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=10, tier3_reserved=10,
                                  now=datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc))
        idx_never = result.index("FS_never_recent")
        idx_old = result.index("FS_scanned_old")
        idx_new = result.index("FS_scanned_new")
        self.assertLess(idx_never, idx_old, "Nunca-escaneado vem antes de escaneado")
        self.assertLess(idx_old, idx_new, "Entre escaneados, mais antigo vem primeiro")

    def test_W14_finished_match_stays_out_of_watchlist(self):
        """Jogo marcado como finished_or_not_live NUNCA entra no Tier 3."""
        from datetime import timedelta as _td
        now = datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        games = [
            {"match_id": "FS_FINISHED",
             "first_seen_at": "2026-05-22T15:00:00+00:00",  # antigo
             "last_scanned_at": None, "last_minute": None,
             "finished_or_not_live": True,
             "finished_or_not_live_at": now.isoformat(),
             "finished_or_not_live_until": (now + _td(hours=12)).isoformat(),
             "not_live_reason": "FINISHED_MATCH"},
            {"match_id": "FS_LIVE",
             "first_seen_at": "2026-05-22T19:30:00+00:00",
             "last_scanned_at": None, "last_minute": None},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=15, now=now)
        self.assertIn("FS_LIVE", result)
        self.assertNotIn("FS_FINISHED", result,
                          "Jogo marcado finished NUNCA pode entrar na watchlist")

    def test_W15_no_stats_backoff_stays_out(self):
        """Jogo em backoff de no_stats fica fora do Tier 3 enquanto TTL ativo."""
        from datetime import timedelta as _td
        now = datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        games = [
            {"match_id": "FS_BACKOFF",
             "first_seen_at": "2026-05-22T15:00:00+00:00",
             "last_scanned_at": "2026-05-22T19:50:00+00:00",
             "last_minute": None,
             "no_stats_count": 2,
             "no_stats_until": (now + _td(minutes=10)).isoformat()},
            {"match_id": "FS_OK",
             "first_seen_at": "2026-05-22T19:30:00+00:00",
             "last_scanned_at": None, "last_minute": None},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=15, now=now)
        self.assertIn("FS_OK", result)
        self.assertNotIn("FS_BACKOFF", result,
                          "Jogo em backoff no_stats não pode entrar")


    # ────────────────────────────────────────────────────────────────────
    # TIER 0.5 — Premium ao vivo (Premier League, La Liga, etc.)
    # ────────────────────────────────────────────────────────────────────

    def test_W16_premium_min5_enters_tier05(self):
        """Premier League min 5 (fora da janela 20-83) DEVE entrar — via Tier 0.5."""
        games = [
            {"match_id": "FS_PL", "is_premium": True,
             "last_minute": 5, "last_bc_sum": 0,
             "first_seen_at": "2026-05-22T19:30:00+00:00"},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3, now=_NOW)
        self.assertIn("FS_PL", result,
                       "Jogo premium min 5 deve entrar via Tier 0.5 mesmo fora da janela 20-83")

    def test_W17_premium_min5_comes_before_common_tier1(self):
        """Premium min 5 (Tier 0.5) entra ANTES de jogo comum Tier 1 (janela + BC)."""
        games = [
            # 12 comuns em Tier 1 (janela 20-83, BC>0)
            *[{"match_id": f"FS_t1_{i}", "last_minute": 40, "last_bc_sum": 2}
              for i in range(12)],
            # 1 premium fora da janela
            {"match_id": "FS_PL_LIVERPOOL", "is_premium": True,
             "last_minute": 5, "last_bc_sum": 0,
             "first_seen_at": "2026-05-22T19:30:00+00:00"},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3, now=_NOW)
        self.assertIn("FS_PL_LIVERPOOL", result)
        # Premium deve aparecer ANTES dos Tier 1 (que ficam atrás de Tier 0.5)
        idx_premium = result.index("FS_PL_LIVERPOOL")
        idx_first_t1 = min(result.index(f"FS_t1_{i}") for i in range(12)
                            if f"FS_t1_{i}" in result)
        self.assertLess(idx_premium, idx_first_t1,
                         f"Premium deve vir ANTES de Tier 1. Order: {result}")

    def test_W18_premium_finished_does_not_enter(self):
        """Jogo premium MARCADO finished_or_not_live NÃO entra (Tier raiz filtra)."""
        from datetime import timedelta as _td
        now = datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        games = [
            {"match_id": "FS_PL_FINISHED", "is_premium": True,
             "last_minute": 95,
             "finished_or_not_live": True,
             "finished_or_not_live_at": now.isoformat(),
             "finished_or_not_live_until": (now + _td(hours=12)).isoformat(),
             "not_live_reason": "FINISHED_MATCH"},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=15, now=now)
        self.assertNotIn("FS_PL_FINISHED", result,
                          "Premium finalizado NUNCA pode entrar (nem por Tier 0.5)")

    def test_W19_premium_in_no_stats_backoff_does_not_enter(self):
        """Premium em no_stats_until ativo NÃO entra (mesmo princípio dos demais tiers)."""
        from datetime import timedelta as _td
        now = datetime(2026, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        games = [
            {"match_id": "FS_PL_BACKOFF", "is_premium": True,
             "last_minute": 10,
             "no_stats_count": 2,
             "no_stats_until": (now + _td(minutes=15)).isoformat()},
            # Sentinela: premium normal pra garantir que o tier funciona
            {"match_id": "FS_PL_OK", "is_premium": True, "last_minute": 10},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3, now=now)
        self.assertIn("FS_PL_OK", result, "Premium OK deve entrar")
        self.assertNotIn("FS_PL_BACKOFF", result,
                          "Premium em backoff de no_stats NÃO pode entrar")

    def test_W20_non_premium_min5_still_in_tier3(self):
        """Jogo NÃO premium em min 5 (fora janela 20-83) continua em Tier 3."""
        games = [
            {"match_id": "FS_OBSCURA", "is_premium": False,
             "last_minute": 5, "last_bc_sum": 0,
             "first_seen_at": "2026-05-22T19:30:00+00:00"},
            # Sentinela premium pra contrastar
            {"match_id": "FS_PL", "is_premium": True,
             "last_minute": 5, "last_bc_sum": 0,
             "first_seen_at": "2026-05-22T19:30:00+00:00"},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3, now=_NOW)
        # Ambos entram, mas premium vem antes (Tier 0.5 > Tier 3)
        self.assertIn("FS_PL", result)
        self.assertIn("FS_OBSCURA", result)
        self.assertLess(result.index("FS_PL"), result.index("FS_OBSCURA"),
                         f"Premium Tier 0.5 deve vir antes de não-premium Tier 3. Order: {result}")

    def test_W21_ten_premium_games_all_enter_fifo(self):
        """10 jogos premium simultâneos: TODOS devem entrar (até max_size).
        Os 6 primeiros via reserved=6; os 4 restantes via leftover_premium na quota alta.
        Nenhum deve ficar 10 minutos sem scan."""
        games = []
        # 10 premiums com diferentes last_scanned_at (FIFO por mais antigo primeiro)
        for i in range(10):
            games.append({
                "match_id": f"FS_PL_{i:02d}",
                "is_premium": True,
                "last_minute": 5,
                "last_bc_sum": 0,
                # last_scanned_at crescente: FS_PL_00 mais antigo (deve vir 1º)
                "last_scanned_at": f"2026-05-22T19:{30+i:02d}:00+00:00",
                "first_seen_at": "2026-05-22T19:00:00+00:00",
            })
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3,
                                  premium_reserved=6, now=_NOW)
        # Todos os 10 devem estar presentes (max_size=15, sobra slot)
        for i in range(10):
            self.assertIn(f"FS_PL_{i:02d}", result,
                           f"FS_PL_{i:02d} ausente — premium não pode ser dropado")
        # FIFO: PL_00 (mais antigo escaneado) vem antes de PL_09
        self.assertLess(result.index("FS_PL_00"), result.index("FS_PL_09"),
                         "FIFO: premium escaneado há mais tempo vem primeiro")

    def test_W22_tier0_still_above_tier05(self):
        """Posição aberta (Tier 0) continua tendo prioridade absoluta sobre Tier 0.5."""
        games = [
            {"match_id": "FS_POSITION_OPEN", "has_open_position": True,
             "last_minute": 50, "last_bc_sum": 3},
            {"match_id": "FS_PL_LIVE", "is_premium": True,
             "last_minute": 5, "last_bc_sum": 0},
        ]
        cat = _make_catalog(games)
        result = build_watchlist(cat, max_size=15, tier3_reserved=3, now=_NOW)
        self.assertEqual(result[0], "FS_POSITION_OPEN",
                          "Tier 0 (posição aberta) deve vir antes de Tier 0.5")
        self.assertIn("FS_PL_LIVE", result, "Tier 0.5 também entra, mas após Tier 0")
        self.assertLess(result.index("FS_POSITION_OPEN"), result.index("FS_PL_LIVE"))


    # ────────────────────────────────────────────────────────────────────
    # HIERARQUIA A > B no Tier 0.5
    # ────────────────────────────────────────────────────────────────────

    def test_W23_premium_A_wins_over_premium_B_with_cap(self):
        """Cap=2, 1 A + 3 B → A entra primeiro, B preenche o restante."""
        games = [
            # Premium A com stats
            {"match_id": "FS_PL_A1", "is_premium": True, "premium_level": "A",
             "last_minute": 30, "last_bc_sum": 3, "ever_loaded_stats": True},
            # 3 premium B com stats
            {"match_id": "FS_PB1", "is_premium": True, "premium_level": "B",
             "last_minute": 30, "last_bc_sum": 3, "ever_loaded_stats": True},
            {"match_id": "FS_PB2", "is_premium": True, "premium_level": "B",
             "last_minute": 30, "last_bc_sum": 3, "ever_loaded_stats": True},
            {"match_id": "FS_PB3", "is_premium": True, "premium_level": "B",
             "last_minute": 30, "last_bc_sum": 3, "ever_loaded_stats": True},
        ]
        cat = _make_catalog(games)
        wl = build_watchlist(cat, max_size=15, tier3_reserved=0,
                              premium_reserved=2, now=_NOW)
        # Com cap=2, dois primeiros são Tier 0.5: A obrigatoriamente primeiro
        self.assertEqual(wl[0], "FS_PL_A1",
                          f"Premium A deve abrir o Tier 0.5. WL: {wl}")

    def test_W24_premium_A_no_stats_still_beats_B_no_stats(self):
        """Mesmo sem stats, A passa antes de B (regra crítica)."""
        games = [
            {"match_id": "FS_A_nostats", "is_premium": True, "premium_level": "A",
             "last_minute": 5, "last_bc_sum": 0, "ever_loaded_stats": False},
            {"match_id": "FS_B_nostats", "is_premium": True, "premium_level": "B",
             "last_minute": 5, "last_bc_sum": 0, "ever_loaded_stats": False},
        ]
        cat = _make_catalog(games)
        wl = build_watchlist(cat, max_size=15, tier3_reserved=0,
                              premium_reserved=2, now=_NOW)
        idx_a = wl.index("FS_A_nostats")
        idx_b = wl.index("FS_B_nostats")
        self.assertLess(idx_a, idx_b, "A NUNCA pode perder slot pra B")

    def test_W25_premium_overflow_appears_in_audit(self):
        """Premium fora da WL por cap aparece em premium_audit_by_level."""
        # Cria 5 A (cap reduzido pra forçar overflow)
        games = []
        for i in range(5):
            games.append({
                "match_id": f"FS_A{i}", "is_premium": True, "premium_level": "A",
                "last_minute": 30, "last_bc_sum": 3, "ever_loaded_stats": True,
                "premium_league_name": "Brasileirão Betano",
                "premium_country": "Brasil",
            })
        cat = _make_catalog(games)
        wl = build_watchlist(cat, max_size=3, tier3_reserved=0,
                              premium_reserved=3, now=_NOW)
        self.assertEqual(len(wl), 3)
        wl_set = set(wl)
        audit = cat.premium_audit_by_level(wl_set, now=_NOW)
        self.assertEqual(len(audit["A"]), 1)
        # 2 jogos viram passivos com motivo premium_overflow
        passive = [p for p in audit["passive_entries"]
                   if p["passive_reason"] == "premium_overflow"]
        self.assertEqual(len(passive), 2,
                          f"2 premium A devem virar passive_overflow: {audit['passive_entries']}")


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestWatchlist)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
