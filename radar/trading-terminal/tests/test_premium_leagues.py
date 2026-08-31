"""Testes da classificação premium em 3 níveis (A>B>C).

A) flashscore_highlighted_league — CSS class do header
B) premium_league_name           — nome da liga (text match)
C) premium_team_slug             — slug do time na URL (legado)
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.premium_leagues import (
    classify_premium, is_premium_url, reset_cache,
    clean_league_name, classify_premium_level,
    REASON_HIGHLIGHTED, REASON_LEAGUE_NAME, REASON_TEAM_SLUG, REASON_NONE,
    LEVEL_A, LEVEL_B, LEVEL_C, LEVEL_NONE,
)


URL_PREM_BR = ("https://www.flashscore.com.br/jogo/futebol/"
                "atletico-mg-hGLC5Bah/corinthians-QBGfQbSe/?mid=A3c2Hc54")
URL_PL_ARS = ("https://www.flashscore.com.br/jogo/futebol/"
               "arsenal-hA1Zm19f/crystal-palace-AovF1Mia/?mid=UNC9hLMj")
URL_OBSCURE = ("https://www.flashscore.com.br/jogo/futebol/"
                "parnu-jk-vaprus-AAAAAA1/levadia-BBBBBB1/?mid=xxxxxx")


class TestClassifyPremium(unittest.TestCase):

    def setUp(self):
        reset_cache()

    # ─── Nível A — CSS destacado ──────────────────────────────────────

    def test_A1_highlighted_css_marks_premium_even_obscure_url(self):
        """Liga destacada com CSS — todos os jogos filhos viram premium,
        mesmo com URL de times obscuros."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Liga Obscura X",
            league_country="País Y",
            league_css_classes=["event__header", "event__header--type-top"],
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)
        self.assertEqual(result["league_name"], "Liga Obscura X")
        self.assertEqual(result["country"], "País Y")

    def test_A2_highlighted_css_accepted_as_string(self):
        """Aceita string OU lista de classes."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="X",
            league_css_classes="event__header wcl-header_top",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)

    def test_A3_highlighted_takes_priority_over_slug(self):
        """Mesmo um URL premium (Arsenal) usa REASON_HIGHLIGHTED quando
        a liga está destacada."""
        result = classify_premium(
            URL_PL_ARS,
            league_name="Premier League",
            league_country="Inglaterra",
            league_css_classes=["event__header--type-top"],
        )
        # Reason é highlighted, NÃO league_name nem slug
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)

    # ─── Nível B — nome de liga ───────────────────────────────────────

    def test_B1_league_name_match_marks_premium(self):
        """'Brasileirão Betano' bate substring 'brasileirão' do whitelist."""
        result = classify_premium(
            URL_PREM_BR,
            league_name="Brasileirão Betano",
            league_country="Brasil",
            league_css_classes=[],  # sem destaque CSS
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_LEAGUE_NAME)

    def test_B2_league_name_match_premier_league(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Inglaterra - Premier League")
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_LEAGUE_NAME)

    def test_B3_league_name_no_match_does_not_promote(self):
        """Liga não-premium NÃO é promovida por nome."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Primera B Nacional Argentina",
        )
        # Nem CSS, nem nome (Primera B não está no whitelist),
        # nem slug (URL obscura) — deve ser não-premium.
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["reason"], REASON_NONE)

    # ─── Nível C — slug do time ──────────────────────────────────────

    def test_C1_slug_match_marks_premium_when_no_league_name(self):
        """Sem CSS, sem nome de liga, mas Arsenal no slug → REASON_TEAM_SLUG."""
        result = classify_premium(URL_PL_ARS)
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_TEAM_SLUG)

    def test_C2_brasileirao_slug_also_works(self):
        """Sem CSS, sem liga, mas Corinthians/Atlético-MG no slug."""
        result = classify_premium(URL_PREM_BR)
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_TEAM_SLUG)

    # ─── Prioridade A > B > C ─────────────────────────────────────────

    def test_priority_A_beats_B(self):
        """CSS destacado vence nome de liga."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",  # bateria por B
            league_country="Inglaterra",
            league_css_classes=["wcl-header_top"],  # bate por A primeiro
        )
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)

    def test_priority_B_beats_C(self):
        """Nome de liga vence slug."""
        result = classify_premium(
            URL_PL_ARS,  # Arsenal no whitelist (C)
            league_name="Premier League",  # bate B
            league_country="Inglaterra",
        )
        self.assertEqual(result["reason"], REASON_LEAGUE_NAME)

    # ─── Casos negativos ──────────────────────────────────────────────

    def test_obscure_no_match(self):
        result = classify_premium(URL_OBSCURE)
        self.assertFalse(result["is_premium"])

    def test_no_url_no_match(self):
        result = classify_premium("")
        self.assertFalse(result["is_premium"])

    # ─── Padrões REAIS do Flashscore (DOM dumpado) ────────────────────

    def test_REAL_headerLeague_has_star_marks_highlighted(self):
        """DOM real: cabeçalho 'Brasileirão Betano' tem class headerLeague--has-star."""
        result = classify_premium(
            URL_PREM_BR,
            league_name="Brasileirão Betano",
            league_country="Brasil",
            league_css_classes=["headerLeague", "headerLeague--has-star",
                                 "wcl-header_HrElx", "wcl-pinned_dRFvU"],
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)
        self.assertEqual(result["league_name"], "Brasileirão Betano")
        self.assertEqual(result["country"], "Brasil")

    def test_REAL_wcl_pinned_alone_marks_highlighted(self):
        """wcl-pinned_dRFvU sozinho (sem has-star) também conta como destaque."""
        result = classify_premium(
            URL_PREM_BR,
            league_name="Brasileirão Série B",
            league_country="Brasil",
            league_css_classes=["headerLeague__wrapper", "wcl-pinned_dRFvU"],
        )
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)

    def test_REAL_headerLeague_wrapper_only_does_not_promote(self):
        """headerLeague__wrapper SEM star/pinned NÃO promove via regra A."""
        result = classify_premium(
            "https://www.flashscore.com.br/jogo/futebol/teamA-AAA111/teamB-BBB222",
            league_name="Primera B Nacional",
            league_country="Argentina",
            league_css_classes=["headerLeague__wrapper"],  # tem wrapper mas sem star
        )
        # Não promove: regra A (highlighted) NÃO bate, B (nome) também não
        # (Primera B Nacional fora do whitelist), C (slug) também não → não premium
        self.assertFalse(result["is_premium"])

    def test_jogo_premium_destacado_aparece_para_cobertura(self):
        """Regra final pedida pelo usuário: jogo dentro de liga destacada
        SEMPRE recebe is_premium=True (pra entrar em Tier 0.5 e na cobertura)."""
        # Mesmo com URL irreconhecível + sem nome no whitelist B,
        # se o CSS marca destaque, é premium.
        result = classify_premium(
            "http://exemplo.com/jogo/futebol/nada/nada/?mid=zzz",
            league_name="Liga Pro Equador",
            league_css_classes=["event__header--type-top"],
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_HIGHLIGHTED)

    # ─── Retrocompat ──────────────────────────────────────────────────

    def test_is_premium_url_legacy_still_works(self):
        """API antiga (slug-only) continua funcionando para Catalog migrar."""
        self.assertTrue(is_premium_url(URL_PL_ARS))
        self.assertFalse(is_premium_url(URL_OBSCURE))


class TestCleanLeagueName(unittest.TestCase):
    """15+ casos reais de nomes sujos vindos do walker DOM."""

    def setUp(self):
        reset_cache()

    def test_clean_01_brasileirao_betano(self):
        self.assertEqual(clean_league_name("Brasileirão BetanoBRASIL:"),
                          "Brasileirão Betano")

    def test_clean_02_brasileirao_serie_b(self):
        self.assertEqual(clean_league_name("Brasileirão Série BBRASIL:"),
                          "Brasileirão Série B")

    def test_clean_03_mls_next_pro(self):
        self.assertEqual(clean_league_name("MLS Next ProEUA:"), "MLS Next Pro")

    def test_clean_04_primera_b_argentina(self):
        self.assertEqual(
            clean_league_name("Primera B Nacional (2ª Divisão)ARGENTINA:"),
            "Primera B Nacional (2ª Divisão)")

    def test_clean_05_premier_league(self):
        self.assertEqual(clean_league_name("Premier LeagueINGLATERRA:"),
                          "Premier League")

    def test_clean_06_la_liga(self):
        self.assertEqual(clean_league_name("La LigaESPANHA:"), "La Liga")

    def test_clean_07_bundesliga(self):
        self.assertEqual(clean_league_name("BundesligaALEMANHA:"), "Bundesliga")

    def test_clean_08_serie_a_italia(self):
        self.assertEqual(clean_league_name("Serie AITÁLIA:"), "Serie A")

    def test_clean_09_liga_pro_equador(self):
        self.assertEqual(clean_league_name("Liga ProEQUADOR:"), "Liga Pro")

    def test_clean_10_liga_dominicana(self):
        self.assertEqual(
            clean_league_name("Liga DominicanaREPÚBLICA DOMINICANA:"),
            "Liga Dominicana")

    def test_clean_11_NWSL_should_NOT_be_eaten(self):
        """NWSL é sigla legítima — não pode virar string vazia."""
        self.assertEqual(clean_league_name("NWSL"), "NWSL")

    def test_clean_12_MLS_should_NOT_be_eaten(self):
        self.assertEqual(clean_league_name("MLS"), "MLS")

    def test_clean_13_no_suffix_unchanged(self):
        self.assertEqual(clean_league_name("Brasileirão Betano"),
                          "Brasileirão Betano")

    def test_clean_14_empty_safe(self):
        self.assertEqual(clean_league_name(""), "")
        self.assertEqual(clean_league_name(None), "")

    def test_clean_15_with_country_param(self):
        """Country param dado: pode limpar até casos não na lista canônica."""
        self.assertEqual(
            clean_league_name("Some LeaguePAISDESCONHECIDO:",
                              country="PAISDESCONHECIDO"),
            "Some League")

    def test_clean_16_ligue_1_franca(self):
        self.assertEqual(clean_league_name("Ligue 1FRANÇA:"), "Ligue 1")


class TestClassifyPremiumLevel(unittest.TestCase):
    """Hierarquia A/B/C/NONE."""

    def setUp(self):
        reset_cache()

    def test_level_A_brasileirao_betano(self):
        lvl = classify_premium_level("Brasileirão Betano", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_A)

    def test_level_A_brasileirao_serie_b(self):
        lvl = classify_premium_level("Brasileirão Série B", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_A)

    def test_level_A_mls_principal(self):
        lvl = classify_premium_level("MLS", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_A)

    def test_level_B_mls_next_pro(self):
        """MLS Next Pro contém 'mls' (que está em A), mas keyword 'next pro'
        força LEVEL_B (verificado ANTES de A)."""
        lvl = classify_premium_level("MLS Next Pro", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_level_B_nwsl(self):
        lvl = classify_premium_level("NWSL", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_level_B_brasileirao_feminino(self):
        lvl = classify_premium_level("Brasileirão Feminino", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_level_B_serie_d(self):
        lvl = classify_premium_level("Brasileirão Série D", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_level_B_primera_b_nacional(self):
        lvl = classify_premium_level("Primera B Nacional", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_level_C_slug_only(self):
        """Sem nome de liga + reason=slug → LEVEL_C."""
        lvl = classify_premium_level("", REASON_TEAM_SLUG)
        self.assertEqual(lvl, LEVEL_C)

    def test_level_NONE_not_premium(self):
        lvl = classify_premium_level("", REASON_NONE)
        self.assertEqual(lvl, LEVEL_NONE)

    def test_level_B_default_unknown_league(self):
        """Liga destacada mas não bate A nem keyword B → default B."""
        lvl = classify_premium_level("Liga Aleatória XYZ", REASON_HIGHLIGHTED)
        self.assertEqual(lvl, LEVEL_B)

    def test_classify_premium_returns_level_field(self):
        """classify_premium() retorna level como campo do dict."""
        result = classify_premium(
            URL_PREM_BR,
            league_name="Brasileirão Betano",
            league_country="Brasil",
            league_css_classes=["headerLeague--has-star"],
        )
        self.assertEqual(result["level"], LEVEL_A)
        self.assertEqual(result["league_name"], "Brasileirão Betano")

    def test_classify_premium_cleans_dirty_name(self):
        """classify_premium() limpa nome sujo automaticamente."""
        result = classify_premium(
            "http://x/jogo/futebol/teamA-AAA111/teamB-BBB222",
            league_name="Brasileirão BetanoBRASIL:",
            league_country="Brasil",
            league_css_classes=["headerLeague--has-star"],
        )
        self.assertEqual(result["league_name"], "Brasileirão Betano")
        self.assertEqual(result["level"], LEVEL_A)


class TestCountryValidation(unittest.TestCase):
    """v2.1 — Filtro anti-impersonator: nome de A-league famoso (Premier
    League, Bundesliga, Serie A, etc.) só promove a premium se o country
    bater a lista de países permitidos daquela competição."""

    def setUp(self):
        reset_cache()

    # ─── Premier League — só Inglaterra é A ──────────────────────────

    def test_premier_league_inglaterra_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Inglaterra",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_LEAGUE_NAME)
        self.assertEqual(result["level"], LEVEL_A)

    def test_premier_league_england_em_ingles_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="England",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_premier_league_KUWAIT_nao_eh_premium(self):
        """BUG RELATÓRIO: 'Premier League | Kuwait' aparecia como Premium A."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Kuwait",
        )
        self.assertFalse(result["is_premium"],
                          f"Premier League Kuwait NÃO pode ser premium: {result}")
        self.assertEqual(result["reason"], REASON_NONE)
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_premier_league_BAHREIN_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League - Playoff de Rebaixamento",
            league_country="Bahrein",
        )
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_premier_league_BAHRAIN_em_ingles_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Bahrain",
        )
        self.assertFalse(result["is_premium"])

    def test_premier_league_SERRA_LEOA_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Serra Leoa",
        )
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_premier_league_ILHAS_FAROE_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Ilhas Faroé",
        )
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_NONE)

    # ─── Bundesliga — só Alemanha é A ────────────────────────────────

    def test_bundesliga_alemanha_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Bundesliga",
            league_country="Alemanha",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_bundesliga_germany_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Bundesliga",
            league_country="Germany",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_bundesliga_austria_nao_eh_premium(self):
        """Bundesliga Áustria NÃO é A (é uma 2ª divisão de outro país)."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Bundesliga",
            league_country="Áustria",
        )
        self.assertFalse(result["is_premium"])

    # ─── Serie A — Itália é A, Brasil também é A (Brasileirão) ─────

    def test_serie_a_italia_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Serie A",
            league_country="Itália",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_serie_a_brasil_eh_premium_A(self):
        """Brasileirão Série A — country=Brasil também valida (Serie A é
        alias para o brasileirão também)."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Brasileirão Serie A",
            league_country="Brasil",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_serie_a_KUWAIT_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Serie A",
            league_country="Kuwait",
        )
        self.assertFalse(result["is_premium"])

    # ─── LaLiga / La Liga ────────────────────────────────────────────

    def test_la_liga_espanha_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="LaLiga",
            league_country="Espanha",
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_A)

    def test_la_liga_arabia_saudita_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="La Liga",
            league_country="Arábia Saudita",
        )
        self.assertFalse(result["is_premium"])

    # ─── Ligue 1, Eredivisie, Primeira Liga, MLS ─────────────────────

    def test_ligue_1_franca_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Ligue 1", league_country="França")
        self.assertEqual(result["level"], LEVEL_A)

    def test_ligue_1_costa_do_marfim_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Ligue 1", league_country="Costa do Marfim")
        self.assertFalse(result["is_premium"])

    def test_eredivisie_holanda_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Eredivisie", league_country="Holanda")
        self.assertEqual(result["level"], LEVEL_A)

    def test_primeira_liga_portugal_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Primeira Liga", league_country="Portugal")
        self.assertEqual(result["level"], LEVEL_A)

    def test_primeira_liga_angola_nao_eh_premium(self):
        result = classify_premium(
            URL_OBSCURE, league_name="Primeira Liga", league_country="Angola")
        self.assertFalse(result["is_premium"])

    def test_mls_eua_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE, league_name="MLS", league_country="EUA")
        self.assertEqual(result["level"], LEVEL_A)

    # ─── Champions / Europa / Conference (internacional) ─────────────

    def test_champions_league_europa_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Champions League",
            league_country="Europa",
        )
        self.assertEqual(result["level"], LEVEL_A)

    def test_europa_league_europa_eh_premium_A(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Europa League",
            league_country="Europa",
        )
        self.assertEqual(result["level"], LEVEL_A)

    # ─── Entradas vazias / inválidas ─────────────────────────────────

    def test_sem_country_sem_competition_sem_team_nao_eh_premium(self):
        """Item sem nada → não premium."""
        result = classify_premium("", league_name="", league_country="")
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_fs_id_sem_url_completa_nao_eh_premium_C(self):
        """URL sem padrão /jogo/futebol/<slug>-<id>/<slug>-<id> → não C.
        Mesmo se o slug textual aparece no whitelist, sem padrão completo
        a URL não é parseável e o jogo não vira premium C."""
        # URL malformada — não tem o padrão completo
        result = classify_premium(
            "https://flashscore.com.br/jogo/futebol/x/y",
            league_name="", league_country="",
        )
        self.assertFalse(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_fs_id_sem_slug_no_whitelist_nao_eh_premium(self):
        """URL bem-formada mas slug não está no whitelist de times C."""
        result = classify_premium(
            "https://flashscore.com.br/jogo/futebol/random-team-AAAAAA/another-BBBBBB",
            league_name="", league_country="",
        )
        self.assertFalse(result["is_premium"])

    # ─── Arsenal / PSG — Premium C válido com URL completa ───────────

    def test_arsenal_premium_C_com_url_valida(self):
        result = classify_premium(URL_PL_ARS, league_name="", league_country="")
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_TEAM_SLUG)
        self.assertEqual(result["level"], LEVEL_C)

    def test_psg_premium_C_com_url_valida(self):
        url = ("https://www.flashscore.com.br/jogo/futebol/"
               "psg-AAAAAA1/marseille-BBBBBB1/?mid=zzz")
        result = classify_premium(url, league_name="", league_country="")
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["reason"], REASON_TEAM_SLUG)
        self.assertEqual(result["level"], LEVEL_C)

    # ─── CSS destacado de impersonator também é rejeitado ────────────

    def test_css_destacado_premier_league_kuwait_NAO_promove(self):
        """Mesmo com CSS destacado, Premier League | Kuwait NÃO é premium.
        O filtro anti-impersonator precede o CSS destacado."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Kuwait",
            league_css_classes=["headerLeague--has-star", "wcl-pinned"],
        )
        self.assertFalse(result["is_premium"],
                          f"Mesmo com CSS destacado, Kuwait não é premium: {result}")
        self.assertEqual(result["reason"], REASON_NONE)
        self.assertEqual(result["level"], LEVEL_NONE)

    def test_css_destacado_premier_league_ilhas_faroe_NAO_promove(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="Premier League",
            league_country="Ilhas Faroé",
            league_css_classes=["wcl-pinned_dRFvU"],
        )
        self.assertFalse(result["is_premium"])

    # ─── Categoria B (NWSL, Sub-20) com qualquer país — só promove se
    #     houver CSS destacado ───────────────────────────────────────

    def test_nwsl_com_css_destacado_eh_premium_B(self):
        result = classify_premium(
            URL_OBSCURE,
            league_name="NWSL",
            league_country="EUA",
            league_css_classes=["headerLeague--has-star"],
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_B)

    def test_brasileirao_sub_20_com_css_destacado_eh_premium_B(self):
        """Sub-20 mesmo do Brasil é B (não A) por causa do B-keyword."""
        result = classify_premium(
            URL_OBSCURE,
            league_name="Brasileirão Sub-20",
            league_country="Brasil",
            league_css_classes=["headerLeague--has-star"],
        )
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["level"], LEVEL_B)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestClassifyPremium, TestCleanLeagueName,
                TestClassifyPremiumLevel, TestCountryValidation):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
