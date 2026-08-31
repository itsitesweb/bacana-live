"""
Testes do Catalog (src/catalog.py).

Cobre:
  C1. upsert_discovered cria entry; segunda chamada atualiza last_seen_at preservando first_seen_at.
  C2. save+load round-trip preserva dados.
  C3. load com arquivo inválido (JSON quebrado / não-dict) descarta sem crashar.
  C4. mark_stale + is_stale_active (True dentro do TTL, False depois).
  C5. mark_no_stats backoff exponencial: 1→5min, 2→15min, 3+→30min.
  C6. mark_scanned reseta no_stats_count + no_stats_until.
  C7. set_position_open / mark_signal atualizam corretamente.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.catalog import Catalog, _no_stats_backoff_seconds


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "catalog.json"

    def test_C1_upsert_creates_then_updates(self):
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_aaa", "http://flashscore/jogo/aaa/")
        first = cat.get("FS_aaa")
        self.assertIsNotNone(first)
        self.assertEqual(first["url"], "http://flashscore/jogo/aaa/")
        first_seen = first["first_seen_at"]

        cat.upsert_discovered("FS_aaa", "http://flashscore/jogo/aaa-updated/")
        second = cat.get("FS_aaa")
        self.assertEqual(second["url"], "http://flashscore/jogo/aaa-updated/")
        self.assertEqual(second["first_seen_at"], first_seen,
                         "first_seen_at deve ser preservado entre upserts")

    def test_C2_save_load_roundtrip(self):
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_x", "http://a/")
        cat.upsert_discovered("FS_y", "http://b/")
        cat.set_position_open("FS_x", True)
        cat.mark_signal("FS_x", "ENTER_BACK_T1_MAIN", 42)
        cat.save()

        cat2 = Catalog(self.path)
        cat2.load()
        self.assertEqual(cat2.size(), 2)
        self.assertTrue(cat2.get("FS_x")["has_open_position"])
        self.assertEqual(cat2.get("FS_x")["last_signal_action"], "ENTER_BACK_T1_MAIN")
        self.assertEqual(cat2.get("FS_x")["last_signal_minute"], 42)

    def test_C3_load_invalid_file_discards(self):
        # Arquivo com JSON quebrado
        self.path.write_text("{not valid json")
        cat = Catalog(self.path)
        cat.load()
        self.assertEqual(cat.size(), 0)

        # Arquivo com top-level lista (não dict)
        self.path.write_text("[1,2,3]")
        cat2 = Catalog(self.path)
        cat2.load()
        self.assertEqual(cat2.size(), 0)

        # Arquivo com dict mas entries sem url
        self.path.write_text(json.dumps({"FS_ok": {"url": "h"}, "FS_bad": {"no_url": True}}))
        cat3 = Catalog(self.path)
        cat3.load()
        self.assertEqual(cat3.size(), 1)
        self.assertIsNotNone(cat3.get("FS_ok"))
        self.assertIsNone(cat3.get("FS_bad"))

    def test_C4_stale_ttl_active_then_expired(self):
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_stale", "http://x/")

        now = datetime.now(timezone.utc)
        cat.mark_stale("FS_stale", ttl_minutes=15)

        # Dentro do TTL → ativo
        self.assertTrue(cat.is_stale_active("FS_stale", now=now + timedelta(minutes=5)))
        self.assertTrue(cat.is_stale_active("FS_stale", now=now + timedelta(minutes=14)))

        # Depois do TTL → expirou
        self.assertFalse(cat.is_stale_active("FS_stale", now=now + timedelta(minutes=20)))

    def test_C5_no_stats_backoff_exponential(self):
        # Ajuste pós-v1.1: backoff mais agressivo (10/20/30 em vez de 5/15/30)
        self.assertEqual(_no_stats_backoff_seconds(1), 10 * 60)
        self.assertEqual(_no_stats_backoff_seconds(2), 20 * 60)
        self.assertEqual(_no_stats_backoff_seconds(3), 30 * 60)
        self.assertEqual(_no_stats_backoff_seconds(10), 30 * 60)

        cat = Catalog(self.path)
        cat.upsert_discovered("FS_no", "http://x/")
        cat.mark_no_stats("FS_no")
        self.assertEqual(cat.get("FS_no")["no_stats_count"], 1)
        cat.mark_no_stats("FS_no")
        self.assertEqual(cat.get("FS_no")["no_stats_count"], 2)

    def test_C8_should_use_short_timeout(self):
        """Helper que indica se daemon deve usar timeout reduzido."""
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_a", "http://x/a/")
        cat.upsert_discovered("FS_b", "http://x/b/")
        # FS_a nunca falhou → timeout normal
        self.assertFalse(cat.should_use_short_timeout("FS_a"))
        # FS_b falhou 1x → timeout reduzido
        cat.mark_no_stats("FS_b")
        self.assertTrue(cat.should_use_short_timeout("FS_b"))
        # match_id desconhecido → False (seguro)
        self.assertFalse(cat.should_use_short_timeout("FS_unknown"))

    def test_C9_count_in_backoff(self):
        """count_in_backoff retorna número de jogos com TTL ativo."""
        cat = Catalog(self.path)
        for i in range(3):
            cat.upsert_discovered(f"FS_no_{i}", f"http://x/{i}/")
            cat.mark_no_stats(f"FS_no_{i}")
        cat.upsert_discovered("FS_clean", "http://x/clean/")
        # 3 em backoff + 1 limpo
        self.assertEqual(cat.count_in_backoff(), 3)
        self.assertEqual(cat.size(), 4)

    def test_C10_mark_finished_or_not_live(self):
        """Marcação de jogo finalizado/suspenso com TTL longo (12h)."""
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_done", "http://x/done/")
        cat.upsert_discovered("FS_live", "http://x/live/")
        # Marca FS_done como finalizado
        cat.mark_finished_or_not_live("FS_done", "FINISHED_MATCH", ttl_hours=12)
        # FS_done agora ativo no TTL
        self.assertTrue(cat.is_finished_or_not_live_active("FS_done"))
        # FS_live segue limpo
        self.assertFalse(cat.is_finished_or_not_live_active("FS_live"))
        # Contador
        self.assertEqual(cat.count_finished_or_not_live(), 1)
        # Campos preenchidos
        entry = cat.get("FS_done")
        self.assertTrue(entry["finished_or_not_live"])
        self.assertEqual(entry["not_live_reason"], "FINISHED_MATCH")
        self.assertIsNotNone(entry["finished_or_not_live_until"])
        # match_id inexistente: silencioso
        cat.mark_finished_or_not_live("FS_nope", "X")
        self.assertIsNone(cat.get("FS_nope"))

    def test_C11_finished_TTL_expires(self):
        """Após TTL, jogo finalizado pode voltar à elegibilidade (segurança)."""
        from datetime import datetime, timezone, timedelta
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_done", "http://x/done/")
        cat.mark_finished_or_not_live("FS_done", "FINISHED_MATCH", ttl_hours=12)
        now = datetime.now(timezone.utc)
        # Dentro do TTL → ativo
        self.assertTrue(cat.is_finished_or_not_live_active("FS_done",
                                                            now=now + timedelta(hours=1)))
        # Após 13h → expirado
        self.assertFalse(cat.is_finished_or_not_live_active("FS_done",
                                                             now=now + timedelta(hours=13)))

    def test_C6_mark_scanned_resets_no_stats(self):
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_x", "http://x/")
        cat.mark_no_stats("FS_x")
        cat.mark_no_stats("FS_x")
        self.assertEqual(cat.get("FS_x")["no_stats_count"], 2)
        self.assertIsNotNone(cat.get("FS_x")["no_stats_until"])

        # Sucesso de extração reseta
        cat.mark_scanned("FS_x", minute=42, score="1-0", bc_sum=3)
        self.assertEqual(cat.get("FS_x")["no_stats_count"], 0)
        self.assertIsNone(cat.get("FS_x")["no_stats_until"])
        self.assertEqual(cat.get("FS_x")["last_minute"], 42)
        self.assertEqual(cat.get("FS_x")["last_bc_sum"], 3)
        self.assertTrue(cat.get("FS_x")["ever_loaded_stats"])

    def test_C7_position_and_signal_flags(self):
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_p", "http://p/")
        self.assertFalse(cat.get("FS_p")["has_open_position"])

        cat.set_position_open("FS_p", True)
        self.assertTrue(cat.get("FS_p")["has_open_position"])

        cat.mark_signal("FS_p", "ENTER_OVER_PREMIUM", 38)
        self.assertEqual(cat.get("FS_p")["last_signal_action"], "ENTER_OVER_PREMIUM")
        self.assertEqual(cat.get("FS_p")["last_signal_minute"], 38)

        # Métodos em match_id inexistente são no-op silencioso
        cat.set_position_open("FS_nope", True)
        cat.mark_signal("FS_nope", "ENTER_BACK_T1_MAIN", 50)
        cat.mark_stale("FS_nope", 5)
        cat.mark_no_stats("FS_nope")
        cat.mark_scanned("FS_nope", minute=1)
        self.assertIsNone(cat.get("FS_nope"))

    # ────────────────────────────────────────────────────────────────────
    # PRUNE — faxina do catálogo (anti-saturação Tier 3)
    # ────────────────────────────────────────────────────────────────────
    def test_C12_prune_removes_not_seen_for_30min(self):
        """Jogo não visto pelo discovery há > 30min é removido."""
        from datetime import datetime, timezone, timedelta
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_recent", "http://recent/")
        cat.upsert_discovered("FS_old", "http://old/")
        # Forçar last_seen_at do FS_old pra 1h atrás
        now = datetime.now(timezone.utc)
        cat._games["FS_old"]["last_seen_at"] = (now - timedelta(hours=1)).isoformat()
        cat._games["FS_old"]["first_seen_at"] = (now - timedelta(hours=1)).isoformat()

        stats = cat.prune_stale_entries(not_seen_ttl_minutes=30, now=now)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(stats["reason_counts"]["not_seen"], 1)
        self.assertIsNone(cat.get("FS_old"))
        self.assertIsNotNone(cat.get("FS_recent"), "Jogo recente NÃO pode ser removido")

    def test_C13_prune_NEVER_removes_open_position(self):
        """Jogo com posição aberta NUNCA é removido, mesmo antigo."""
        from datetime import datetime, timezone, timedelta
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_open", "http://open/")
        cat._games["FS_open"]["has_open_position"] = True
        # Forçar last_seen_at antigo
        now = datetime.now(timezone.utc)
        cat._games["FS_open"]["last_seen_at"] = (now - timedelta(hours=5)).isoformat()
        cat._games["FS_open"]["first_seen_at"] = (now - timedelta(hours=5)).isoformat()

        stats = cat.prune_stale_entries(not_seen_ttl_minutes=30, now=now)
        self.assertEqual(stats["removed"], 0)
        self.assertIsNotNone(cat.get("FS_open"),
                             "JAMAIS remover jogo com posição aberta")

    def test_C14_prune_removes_finished_long_ago(self):
        """Jogo marcado como finished cujo TTL passou há > finished_ttl_hours é removido."""
        from datetime import datetime, timezone, timedelta
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_done", "http://done/")
        # Marca finished com TTL curto que já expirou
        cat.mark_finished_or_not_live("FS_done", "FINISHED_MATCH", ttl_hours=1)
        # Avança tempo pra TTL ter passado + finished_ttl_hours
        now = datetime.now(timezone.utc) + timedelta(hours=14)
        # Forçar também last_seen_at antigo
        cat._games["FS_done"]["last_seen_at"] = (now - timedelta(hours=15)).isoformat()
        cat._games["FS_done"]["first_seen_at"] = (now - timedelta(hours=15)).isoformat()

        stats = cat.prune_stale_entries(not_seen_ttl_minutes=30,
                                          finished_ttl_hours=12, now=now)
        self.assertEqual(stats["removed"], 1, f"Esperava remoção, got: {stats}")
        self.assertIsNone(cat.get("FS_done"))

    def test_C15_prune_returns_stats(self):
        """prune_stale_entries retorna dict com removed, kept, reason_counts."""
        cat = Catalog(self.path)
        cat.upsert_discovered("FS_keep", "http://keep/")
        stats = cat.prune_stale_entries()
        self.assertIn("removed", stats)
        self.assertIn("kept", stats)
        self.assertIn("reason_counts", stats)
        self.assertEqual(stats["removed"], 0)
        self.assertEqual(stats["kept"], 1)


    # ────────────────────────────────────────────────────────────────────
    # DEDUPLICAÇÃO CANÔNICA — caso Corinthians × Atlético-MG
    # ────────────────────────────────────────────────────────────────────

    def test_C16_canonical_mid_based_wins_over_fingerprint(self):
        """Caso real: dois entries do mesmo jogo Atlético-MG × Corinthians.
        - FS_hGLC5Bah_QBGfQbSe (sem ?mid=, fingerprint-based, antigo)
        - FS_A3c2Hc54         (com ?mid=, mid-based, novo)
        Canônico = FS_A3c2Hc54. Antigo = duplicado."""
        cat = Catalog(self.path)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        url_old = ("https://www.flashscore.com.br/jogo/futebol/"
                   "atletico-mg-hGLC5Bah/corinthians-QBGfQbSe")
        url_new = ("https://www.flashscore.com.br/jogo/futebol/"
                   "atletico-mg-hGLC5Bah/corinthians-QBGfQbSe/?mid=A3c2Hc54")

        cat.upsert_discovered("FS_hGLC5Bah_QBGfQbSe", url_old)
        # ajusta tempos para simular antigo
        cat._games["FS_hGLC5Bah_QBGfQbSe"]["last_scanned_at"] = (now - timedelta(minutes=40)).isoformat()
        cat._games["FS_hGLC5Bah_QBGfQbSe"]["last_minute"] = 16
        cat._games["FS_hGLC5Bah_QBGfQbSe"]["ever_loaded_stats"] = True

        cat.upsert_discovered("FS_A3c2Hc54", url_new)
        cat._games["FS_A3c2Hc54"]["last_scanned_at"] = (now - timedelta(minutes=2)).isoformat()
        cat._games["FS_A3c2Hc54"]["last_minute"] = 45
        cat._games["FS_A3c2Hc54"]["ever_loaded_stats"] = True

        cat.recompute_duplicates()

        # FS_A3c2Hc54 deve ser canônico
        new = cat.get("FS_A3c2Hc54")
        self.assertFalse(new["excluded_duplicate"], "FS_A3c2Hc54 deve ser canônico (mid-based)")
        self.assertEqual(new["duplicate_of"], "")

        # FS_hGLC5Bah_QBGfQbSe deve ser duplicado
        old = cat.get("FS_hGLC5Bah_QBGfQbSe")
        self.assertTrue(old["excluded_duplicate"], "FS_hGLC5Bah_QBGfQbSe deve ser duplicado")
        self.assertEqual(old["duplicate_of"], "FS_A3c2Hc54")

    def test_C17_watchlist_excludes_duplicate_keeps_canonical(self):
        """Watchlist deve excluir o duplicado e incluir o canônico."""
        from src.watchlist import build_watchlist
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        cat = Catalog(self.path)
        url_old = "https://www.flashscore.com.br/jogo/futebol/teamA-aaaaaa/teamB-bbbbbb"
        url_new = url_old + "/?mid=zzzzz12"
        cat.upsert_discovered("FS_aaaaaa_bbbbbb", url_old)
        cat._games["FS_aaaaaa_bbbbbb"]["last_minute"] = 16
        cat._games["FS_aaaaaa_bbbbbb"]["last_bc_sum"] = 2
        cat._games["FS_aaaaaa_bbbbbb"]["ever_loaded_stats"] = True
        cat.upsert_discovered("FS_zzzzz12", url_new)
        cat._games["FS_zzzzz12"]["last_minute"] = 45
        cat._games["FS_zzzzz12"]["last_bc_sum"] = 3
        cat._games["FS_zzzzz12"]["ever_loaded_stats"] = True
        cat.recompute_duplicates()

        wl = build_watchlist(cat, max_size=15, now=now)
        self.assertIn("FS_zzzzz12", wl, "Canônico (mid-based) deve estar na watchlist")
        self.assertNotIn("FS_aaaaaa_bbbbbb", wl, "Duplicado NÃO pode estar na watchlist")

    def test_C18_canonical_picker_priority(self):
        """Quando AMBOS são mid-based, usa last_seen_at desc como tie-break."""
        from src.catalog import _pick_canonical
        e1 = {"match_id": "FS_aaa", "last_seen_at": "2026-05-24T10:00:00+00:00",
              "last_scanned_at": "", "last_minute": 0, "ever_loaded_stats": False,
              "url": "http://x"}
        e2 = {"match_id": "FS_bbb", "last_seen_at": "2026-05-24T12:00:00+00:00",
              "last_scanned_at": "", "last_minute": 0, "ever_loaded_stats": False,
              "url": "http://x"}
        canon = _pick_canonical([e1, e2])
        self.assertEqual(canon["match_id"], "FS_bbb")

    def test_C18b_league_name_cleaned_on_load(self):
        """Migração no load() limpa sufixo de país concatenado no nome da liga."""
        import json
        from datetime import datetime, timezone
        # Cria catálogo com nome sujo (como veio do walker antigo)
        dirty = {
            "FS_test1": {
                "match_id": "FS_test1",
                "url": "http://x/jogo/futebol/teamA-aaaaaa/teamB-bbbbbb/",
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "is_premium": True,
                "premium_reason": "flashscore_highlighted_league",
                "premium_league_name": "Brasileirão BetanoBRASIL:",
                "premium_country": "Brasil",
            },
            "FS_test2": {
                "match_id": "FS_test2",
                "url": "http://x/jogo/futebol/teamC-cccccc/teamD-dddddd/",
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "is_premium": True,
                "premium_reason": "flashscore_highlighted_league",
                "premium_league_name": "Premier LeagueINGLATERRA:",
                "premium_country": "Inglaterra",
            },
        }
        with open(self.path, "w") as f:
            json.dump(dirty, f)
        cat = Catalog(self.path)
        cat.load()
        self.assertEqual(cat.get("FS_test1")["premium_league_name"], "Brasileirão Betano")
        self.assertEqual(cat.get("FS_test2")["premium_league_name"], "Premier League")

    def test_C20_premium_C_phantom_demoted_on_load(self):
        """v2.2 — Catálogo contaminado com Premium C fantasma (URL com slug
        do whitelist, MAS sem league_meta, sem ever_loaded_stats, sem
        last_minute) é demovido para não-premium na carga."""
        from datetime import datetime, timezone
        url_phantom = ("http://x.com/jogo/futebol/"
                        "bahia-UeD7XtzM/coritiba-KGO4pUqO#/match-statistics/0")
        phantom = {
            "FS_UeD7XtzM_KGO4pUqO": {
                "match_id": "FS_UeD7XtzM_KGO4pUqO",
                "url": url_phantom,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "is_premium": True,                      # contaminado
                "premium_reason": "premium_team_slug",
                "premium_level": "C",
                "premium_league_name": "",               # sem nome
                "premium_country": "",                   # sem país
                "last_minute": None,                     # nunca escaneado
                "ever_loaded_stats": False,
                "league_meta_raw": {},
            }
        }
        with open(self.path, "w") as f:
            json.dump(phantom, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_UeD7XtzM_KGO4pUqO")
        self.assertFalse(e["is_premium"],
                          f"Fantasma Premium C deve ser demovido: {e}")
        self.assertEqual(e["premium_level"], "NONE")
        self.assertEqual(e["premium_reason"], "")

    def test_C21_premium_C_keeps_when_has_minute(self):
        """Entry com slug match E last_minute populado → mantém Premium C
        (evidência: o jogo já foi visto ao vivo)."""
        from datetime import datetime, timezone
        url = ("http://x.com/jogo/futebol/"
               "arsenal-AAAAAA1/crystal-palace-BBBBBB1#/match-statistics/0")
        entry = {
            "FS_test_C21": {
                "match_id": "FS_test_C21",
                "url": url,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "is_premium": True,
                "premium_reason": "premium_team_slug",
                "premium_level": "C",
                "premium_league_name": "",
                "premium_country": "",
                "last_minute": 42,                       # JOGO VISTO AO VIVO
                "ever_loaded_stats": True,
                "league_meta_raw": {},
            }
        }
        with open(self.path, "w") as f:
            json.dump(entry, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_test_C21")
        self.assertTrue(e["is_premium"])
        self.assertEqual(e["premium_level"], "C")

    def test_C22_premium_C_keeps_when_ever_loaded_stats(self):
        """Entry com slug match + ever_loaded_stats=True (mesmo sem minute
        atual) → mantém Premium C."""
        from datetime import datetime, timezone
        url = ("http://x.com/jogo/futebol/"
               "psg-AAAAAA1/marseille-BBBBBB1#/match-statistics/0")
        entry = {
            "FS_test_C22": {
                "match_id": "FS_test_C22",
                "url": url,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "is_premium": True,
                "premium_reason": "premium_team_slug",
                "premium_level": "C",
                "premium_league_name": "",
                "premium_country": "",
                "last_minute": None,
                "ever_loaded_stats": True,               # evidência
                "league_meta_raw": {},
            }
        }
        with open(self.path, "w") as f:
            json.dump(entry, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_test_C22")
        self.assertTrue(e["is_premium"])

    def test_C23_premium_C_demoted_on_upsert_when_no_evidence(self):
        """Upsert NOVO de URL com slug whitelist mas SEM league_meta nem
        scan history → não-premium até que evidência apareça."""
        cat = Catalog(self.path)
        url = ("http://x.com/jogo/futebol/"
               "bahia-AAAAAA1/coritiba-BBBBBB1#/match-statistics/0")
        cat.upsert_discovered("FS_new1", url, league_meta=None)
        e = cat.get("FS_new1")
        self.assertFalse(e["is_premium"],
                          f"Upsert novo só com slug NÃO deve virar Premium C: {e}")
        self.assertEqual(e["premium_level"], "NONE")

    def test_C24_premium_C_kept_on_upsert_when_league_meta_present(self):
        """Upsert NOVO de URL com slug whitelist + league_meta com nome →
        deveria virar Premium A (nome bate + país, ou B se só nome).
        O ponto é: NÃO cai no gate fantasma de Premium C."""
        cat = Catalog(self.path)
        url = ("http://x.com/jogo/futebol/"
               "bahia-AAAAAA1/coritiba-BBBBBB1#/match-statistics/0")
        cat.upsert_discovered("FS_new2", url, league_meta={
            "league_name": "Brasileirão Betano",
            "country": "Brasil",
        })
        e = cat.get("FS_new2")
        self.assertTrue(e["is_premium"])
        self.assertEqual(e["premium_level"], "A")  # nome + país = A

    def test_C25_premium_C_promoted_after_scan(self):
        """Entry novo sem evidência (não-premium). Após mark_scanned + upsert
        seguinte, ganha last_minute/ever_loaded_stats → vira Premium C."""
        cat = Catalog(self.path)
        url = ("http://x.com/jogo/futebol/"
               "psg-AAAAAA1/marseille-BBBBBB1#/match-statistics/0")
        cat.upsert_discovered("FS_new3", url)
        self.assertFalse(cat.get("FS_new3")["is_premium"])
        # Daemon escaneia o jogo (mark_scanned popula stats)
        cat.mark_scanned("FS_new3", minute=15, score="0:0", bc_sum=1)
        # Discovery vê o jogo de novo → upsert recomputa com evidência
        cat.upsert_discovered("FS_new3", url)
        e = cat.get("FS_new3")
        self.assertTrue(e["is_premium"],
                          f"Após scan, slug match deve virar Premium C: {e}")
        self.assertEqual(e["premium_level"], "C")

    def test_C26_load_clears_ambiguous_minute_block(self):
        """v2.3 — Catálogo contaminado com finished_or_not_live=True por
        INVALID_MINUTE_STATUS / AMBIGUOUS_MINUTE_STATUS sem nunca ter
        scanado → cleanup automático na load()."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        contaminated = {
            "FS_Gtk53bn1": {  # Nacional × Coquimbo (reprodução do caso real)
                "match_id": "FS_Gtk53bn1",
                "url": ("https://www.flashscore.com.br/jogo/futebol/"
                         "club-nacional-UaVu2MhA/coquimbo-hWejMZ6h/?mid=Gtk53bn1"),
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "last_scanned_at": None,
                "last_minute": None,
                "ever_loaded_stats": False,
                "is_premium": True,
                "premium_reason": "flashscore_highlighted_league",
                "premium_level": "A",
                "premium_league_name": "Copa Libertadores - Fase de Grupos",
                "premium_country": "América do sul",
                "finished_or_not_live": True,
                "finished_or_not_live_at": now.isoformat(),
                "finished_or_not_live_until": future,
                "not_live_reason": "INVALID_MINUTE_STATUS",
                "league_meta_raw": {"league_name": "Copa Libertadores - Fase de Grupos",
                                     "country": "América do sul"},
            }
        }
        with open(self.path, "w") as f:
            json.dump(contaminated, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_Gtk53bn1")
        self.assertFalse(e["finished_or_not_live"],
                          f"Entry ambíguo deve ser destravado: {e}")
        self.assertEqual(e["not_live_reason"], "")
        self.assertIsNone(e["finished_or_not_live_at"])
        self.assertIsNone(e["finished_or_not_live_until"])
        # is_finished_or_not_live_active deve retornar False
        self.assertFalse(cat.is_finished_or_not_live_active("FS_Gtk53bn1"))

    def test_C27_load_clears_AMBIGUOUS_MINUTE_STATUS_block(self):
        """Mesmo cleanup deve rodar pra not_live_reason=AMBIGUOUS_MINUTE_STATUS."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        contaminated = {
            "FS_amb1": {
                "match_id": "FS_amb1",
                "url": "https://x.com/jogo/futebol/a-AAAAAA/b-BBBBBB/?mid=amb1",
                "first_seen_at": now, "last_seen_at": now,
                "last_scanned_at": None, "last_minute": None,
                "ever_loaded_stats": False,
                "finished_or_not_live": True,
                "finished_or_not_live_at": now,
                "finished_or_not_live_until": now,
                "not_live_reason": "AMBIGUOUS_MINUTE_STATUS",
            }
        }
        with open(self.path, "w") as f:
            json.dump(contaminated, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_amb1")
        self.assertFalse(e["finished_or_not_live"])

    def test_C28_load_KEEPS_finished_when_ever_loaded_stats(self):
        """Se o entry JÁ teve stats reais (ever_loaded_stats=True), a
        marcação finished veio com evidência — NÃO limpar."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        valid = {
            "FS_real_finished": {
                "match_id": "FS_real_finished",
                "url": "https://x.com/jogo/futebol/a-AAAAAA/b-BBBBBB/?mid=fin",
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "last_scanned_at": now.isoformat(),
                "last_minute": 90,
                "ever_loaded_stats": True,         # JÁ TINHA STATS
                "finished_or_not_live": True,
                "finished_or_not_live_at": now.isoformat(),
                "finished_or_not_live_until": future,
                "not_live_reason": "INVALID_MINUTE_STATUS",
            }
        }
        with open(self.path, "w") as f:
            json.dump(valid, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_real_finished")
        self.assertTrue(e["finished_or_not_live"],
                         "Entry com stats reais deve preservar finished")

    def test_C29_load_KEEPS_finished_for_FINISHED_MATCH(self):
        """FINISHED_MATCH (status real do Flashscore) NUNCA é limpo."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        valid = {
            "FS_terminado": {
                "match_id": "FS_terminado",
                "url": "https://x.com/jogo/futebol/a-AAAAAA/b-BBBBBB/?mid=ter",
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "last_scanned_at": None,
                "last_minute": None,
                "ever_loaded_stats": False,
                "finished_or_not_live": True,
                "finished_or_not_live_at": now.isoformat(),
                "finished_or_not_live_until": future,
                "not_live_reason": "FINISHED_MATCH",   # status forte
            }
        }
        with open(self.path, "w") as f:
            json.dump(valid, f)
        cat = Catalog(self.path)
        cat.load()
        e = cat.get("FS_terminado")
        self.assertTrue(e["finished_or_not_live"])
        self.assertEqual(e["not_live_reason"], "FINISHED_MATCH")

    def test_C19_get_duplicates_of(self):
        """Catalog.get_duplicates_of retorna entries marcados duplicate_of=<canonical>."""
        cat = Catalog(self.path)
        url_base = "https://www.flashscore.com.br/jogo/futebol/x-aaaaaa/y-bbbbbb"
        cat.upsert_discovered("FS_aaaaaa_bbbbbb", url_base)
        cat.upsert_discovered("FS_zzz9999", url_base + "/?mid=zzz9999")
        cat.recompute_duplicates()
        dups = cat.get_duplicates_of("FS_zzz9999")
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["match_id"], "FS_aaaaaa_bbbbbb")


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestCatalog)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
