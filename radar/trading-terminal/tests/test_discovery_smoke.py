"""
Smoke test do src/discovery.py.

Mock do BrowserContext + Page do Playwright. Não abre browser real.

Cobre:
  S1. discover_live_games retorna lista normalizada (com hash de stats anexado).
  S2. match_id extraído corretamente das URLs do Flashscore.
  S3. URLs duplicadas são deduplicadas.
  S4. ao_vivo_found refletido no retorno.
  S5. Erro de goto retorna estrutura segura com error preenchido.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.discovery import discover_live_games, _extract_match_id, _normalize_stats_url


class FakePage:
    def __init__(self, links, ao_vivo=True, raise_on_goto=False,
                 raise_on_wait_for_selector=False):
        self._links = links
        self._ao_vivo = ao_vivo
        self._raise_on_goto = raise_on_goto
        self._raise_on_wfs = raise_on_wait_for_selector
        self.closed = False

    def goto(self, *_a, **_kw):
        if self._raise_on_goto:
            raise RuntimeError("fake-goto-error")

    def wait_for_selector(self, _selector, **_kw):
        if self._raise_on_wfs:
            raise RuntimeError("selector-timeout")

    def evaluate(self, script):
        # Primeira chamada: JS de "AO VIVO" → bool
        # Segunda chamada: JS de expansão de ligas → não retorna nada
        if "filters__tab" in script:
            return self._ao_vivo
        return None

    def wait_for_timeout(self, _ms):
        pass

    def eval_on_selector_all(self, _selector, _js):
        return list(self._links)

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page


class TestDiscoverySmoke(unittest.TestCase):

    def test_S1_returns_normalized_list_with_stats_hash(self):
        links = [
            "https://www.flashscore.com.br/jogo/futebol/team-a-K8bh3OkJ/team-b-AbcDef12/",
            "https://www.flashscore.com.br/jogo/futebol/team-c-XYZ12abc/team-d-345ZZ/",
        ]
        page = FakePage(links, ao_vivo=True)
        ctx = FakeContext(page)

        result = discover_live_games(ctx, "https://www.flashscore.com.br/")
        games = result["games"]

        self.assertEqual(len(games), 2)
        for mid, url in games:
            self.assertTrue(url.endswith("#/match-summary/match-statistics/0"))
            # URL base não pode ter fragmento residual nem barra extra
            self.assertNotIn("#/", url.split("#")[0],
                             "URL base não pode ter fragmento")

        self.assertTrue(result["ao_vivo_found"])
        self.assertEqual(result["total_found"], 2)
        self.assertIsNone(result["error"])
        self.assertTrue(page.closed)

    def test_S2_match_id_extraction(self):
        # Formato /jogo/futebol/team-ID1/team-ID2
        mid = _extract_match_id("https://www.flashscore.com.br/jogo/futebol/team-a-AAA111/team-b-BBB222/")
        self.assertEqual(mid, "FS_AAA111_BBB222")

        # Formato /match/ID
        mid2 = _extract_match_id("https://example.com/match/K8bh3OkJ/")
        self.assertEqual(mid2, "FS_K8bh3OkJ")

        # Formato ?mid=ID
        mid3 = _extract_match_id("https://example.com/?mid=ZZZ999")
        self.assertEqual(mid3, "FS_ZZZ999")

        # Formato desconhecido
        mid4 = _extract_match_id("https://example.com/random")
        self.assertEqual(mid4, "FS_UNKNOWN")

    def test_S3_duplicate_urls_deduplicated(self):
        # Mesmo link 3x + variação de hash (que será removido pela normalização)
        links = [
            "https://www.flashscore.com.br/jogo/futebol/a-AAA111/b-BBB222/",
            "https://www.flashscore.com.br/jogo/futebol/a-AAA111/b-BBB222/",
            "https://www.flashscore.com.br/jogo/futebol/a-AAA111/b-BBB222/#/match-summary",
        ]
        page = FakePage(links)
        ctx = FakeContext(page)
        result = discover_live_games(ctx, "https://x/")
        # 3 links viraram 1 após normalização e dedup
        self.assertEqual(len(result["games"]), 1)

    def test_S4_ao_vivo_not_found(self):
        page = FakePage([], ao_vivo=False)
        ctx = FakeContext(page)
        result = discover_live_games(ctx, "https://x/")
        self.assertFalse(result["ao_vivo_found"])
        self.assertEqual(result["games"], [])

    def test_S5_goto_error_returns_safe_structure(self):
        page = FakePage([], raise_on_goto=True)
        ctx = FakeContext(page)
        result = discover_live_games(ctx, "https://x/")
        self.assertEqual(result["games"], [])
        self.assertEqual(result["total_found"], 0)
        self.assertFalse(result["ao_vivo_found"])
        self.assertIn("fake-goto-error", result["error"])
        self.assertTrue(page.closed)

    def test_S6_normalize_url(self):
        # Hash existente é trocado por hash de stats
        url = _normalize_stats_url("https://x/jogo/y/#/some-other-hash")
        self.assertTrue(url.endswith("#/match-summary/match-statistics/0"))
        self.assertNotIn("some-other-hash", url)

        # Trailing slash é removido antes de anexar
        url2 = _normalize_stats_url("https://x/jogo/y/")
        self.assertEqual(url2, "https://x/jogo/y#/match-summary/match-statistics/0")

    def test_S7_normalize_url_with_query_string(self):
        """BUG CRÍTICO: URL com ?mid=xxx não pode ter barra antes do hash.
        Bug original gerava '?mid=xxx/#/...' — Flashscore lia mid como 'xxx/'."""
        url = _normalize_stats_url(
            "https://www.flashscore.com.br/jogo/futebol/a-AAA/b-BBB/?mid=tM1Pujif"
        )
        # NÃO pode ter "?mid=tM1Pujif/#" — tem que ser "?mid=tM1Pujif#"
        self.assertNotIn("?mid=tM1Pujif/#", url, f"Bug da barra! URL: {url}")
        self.assertIn("?mid=tM1Pujif#/match-summary", url)

        # Também testar com hash já presente
        url2 = _normalize_stats_url(
            "https://x/jogo/a/b/?mid=ABC#/match-summary/old"
        )
        self.assertNotIn("?mid=ABC/#", url2)
        self.assertIn("?mid=ABC#/match-summary/match-statistics/0", url2)


def _run_all():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestDiscoverySmoke))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
