"""
Testes do parser de minuto do FlashscoreReader (correção do bug 'min 1' tirado do placar).

Cobre:
  P1. status vazio → 0 (motor trata como NO_TRADE pre-game)
  P2. status só com placar não pode poluir o minuto (BUG ORIGINAL)
  P3. "TERMINADO" / "FT" / "FINISHED" / "ENCERRADO" → 90
  P4. "INTERVALO" / "HT" → 45
  P5. status com minuto explícito retorna número
  P6. formato MM:SS reconhecido (incluindo prefixo "2º tempo56:21")
  P7. número fora do range (>130) ignorado → 0
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub Playwright pra evitar dep
import types
if "playwright" not in sys.modules:
    pw = types.ModuleType("playwright")
    pwsa = types.ModuleType("playwright.sync_api")
    pwsa.sync_playwright = lambda: None
    pwsa.Page = type("Page", (), {})
    pwsa.BrowserContext = type("BC", (), {})
    sys.modules["playwright"] = pw
    sys.modules["playwright.sync_api"] = pwsa

from src.flashscore_adapter import FlashscoreReader


class TestParseMinute(unittest.TestCase):

    def setUp(self):
        # Não inicia browser — só usa o método _parse_minute
        self.reader = FlashscoreReader.__new__(FlashscoreReader)

    def test_P1_empty_status_returns_zero(self):
        # Sem status: minute=0 (pre-game/unknown), motor trata como NO_TRADE
        self.assertEqual(self.reader._parse_minute("", "1-0"), 0)
        self.assertEqual(self.reader._parse_minute("", ""), 0)
        self.assertEqual(self.reader._parse_minute(None, "2-1"), 0)
        self.assertEqual(self.reader._parse_minute("   ", "1-0"), 0)

    def test_P2_score_does_not_pollute_minute(self):
        """BUG ORIGINAL: placar '1-0' era extraído como minute=1.
        Agora score_raw é IGNORADO totalmente."""
        self.assertEqual(self.reader._parse_minute("", "1-0"), 0)
        self.assertEqual(self.reader._parse_minute("", "3-2"), 0)
        self.assertEqual(self.reader._parse_minute("", "0-0"), 0)

    def test_P3_finished_returns_90(self):
        self.assertEqual(self.reader._parse_minute("TERMINADO", ""), 90)
        self.assertEqual(self.reader._parse_minute("FT", ""), 90)
        self.assertEqual(self.reader._parse_minute("FINISHED", ""), 90)
        self.assertEqual(self.reader._parse_minute("ENCERRADO", ""), 90)
        self.assertEqual(self.reader._parse_minute("terminado", "1-0"), 90)

    def test_P4_halftime_returns_45(self):
        self.assertEqual(self.reader._parse_minute("INTERVALO", ""), 45)
        self.assertEqual(self.reader._parse_minute("HT", ""), 45)
        self.assertEqual(self.reader._parse_minute("Half Time", ""), 45)

    def test_P5_explicit_minute_returned(self):
        self.assertEqual(self.reader._parse_minute("45", "1-0"), 45)
        self.assertEqual(self.reader._parse_minute("67'", "1-1"), 67)
        self.assertEqual(self.reader._parse_minute("12", ""), 12)
        self.assertEqual(self.reader._parse_minute("90+3", "2-0"), 90)

    def test_P6_mmss_format(self):
        self.assertEqual(self.reader._parse_minute("45:30", "0-0"), 45)
        self.assertEqual(self.reader._parse_minute("12:05", ""), 12)

    def test_P7_out_of_range_minute_falls_through(self):
        # Minuto > 130 (impossível) → cai pra 0
        self.assertEqual(self.reader._parse_minute("999", "1-0"), 0)
        # Lembrando que o regex captura só 1-3 dígitos; valores grandes que
        # cabem em 130 são aceitos (90 é valido)
        self.assertEqual(self.reader._parse_minute("90", ""), 90)
        self.assertEqual(self.reader._parse_minute("130", ""), 130)

    def test_P8_real_flashscore_format(self):
        """Caso real observado em produção: '2º tempo56:21'"""
        self.assertEqual(self.reader._parse_minute("2º tempo56:21", "0-2"), 56)
        self.assertEqual(self.reader._parse_minute("1º tempo23:45", "1-0"), 23)
        self.assertEqual(self.reader._parse_minute("1st Half 12:30", ""), 12)

    def test_P9_mmss_in_score_fallback(self):
        """Flashscore às vezes deixa só '2º tempo' no header e o MM:SS no score.
        Probe real: status='2º tempo', score='0-22º tempo69:45'.
        Deve extrair minute=69 do MM:SS no score (não 0)."""
        self.assertEqual(
            self.reader._parse_minute("2º tempo", "0-22º tempo69:45"),
            69
        )
        # Mas score puro "1-0" continua sem poluir (não tem ":")
        self.assertEqual(self.reader._parse_minute("", "1-0"), 0)
        self.assertEqual(self.reader._parse_minute("", "3-2"), 0)


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestParseMinute)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
