"""
Premium leagues classifier — identifica se um jogo do Flashscore é "premium"
(merece slot prioritário de scan em Tier 0.5 da watchlist).

REGRA OFICIAL — três níveis de prioridade (do mais forte ao mais fraco):

  A) flashscore_highlighted_league  — cabeçalho da liga no Flashscore aparece
                                       com CSS class de destaque (fundo amarelo/
                                       dourado). Detectado pelo discovery via
                                       DOM walk. Padrões CSS configuráveis em
                                       config/premium_competitions.json
                                       (chave '_highlighted_css_patterns').
  B) premium_league_name            — nome da liga (texto do header) bate
                                       substring case-insensitive de uma das
                                       entradas em '_premium_a_leagues' **E**
                                       o country bate a lista de países
                                       permitidos daquela competição.
  C) premium_team_slug              — slug do time na URL bate uma das listas
                                       por liga (legado, fallback final).
                                       Requer URL com padrão completo
                                       /jogo/futebol/<slug>-<id6+>/<slug>-<id6+>.

REGRA DE PROTEÇÃO CONTRA IMPERSONATORS (v2.1):
  Se o nome da liga bate uma entrada A famosa ("Premier League", "Bundesliga",
  "Serie A", etc.) MAS o country NÃO bate a lista de países permitidos daquela
  liga → is_premium=False. Isso impede que "Premier League | Kuwait" ou
  "Bundesliga | Singapura" sejam classificados como premium A só porque o
  nome bate substring.

A primeira regra que casar define:
    is_premium = True
    premium_reason = "flashscore_highlighted_league"
                   | "premium_league_name"
                   | "premium_team_slug"

E captura quando disponível:
    premium_league_name  (string, vazia se não detectado)
    premium_country      (string, vazia se não detectado)

Este módulo é PURO (sem efeitos colaterais). Discovery alimenta os dados,
Catalog persiste, Watchlist usa pra Tier 0.5.
"""
import json
import re
from pathlib import Path
from typing import Optional


_CONFIG_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "premium_competitions.json"

# Cache em memória
_CONFIG_CACHE: Optional[dict] = None
_CONFIG_FROM_PATH: Optional[Path] = None


def _load_config(config_path: Optional[Path] = None) -> dict:
    """Carrega config completa (slugs + nomes de liga + padrões CSS + level A/B).

    Returns:
        {
            "slugs": set[str],
            "highlighted_patterns": list[str] (lowercase),
            "premium_a_leagues": list[dict] com {"name": str, "countries": list[str]}
                                  (lowercase, normalizado),
            "premium_b_keywords": list[str] (lowercase),
        }
    """
    global _CONFIG_CACHE, _CONFIG_FROM_PATH
    path = Path(config_path) if config_path else _CONFIG_DEFAULT_PATH

    if _CONFIG_CACHE is not None and _CONFIG_FROM_PATH == path:
        return _CONFIG_CACHE

    out = {
        "slugs": set(),
        "highlighted_patterns": [],
        "premium_a_leagues": [],   # list[{"name": str, "countries": list[str]}]
        "premium_b_keywords": [],
    }
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "_premium_a_leagues" and isinstance(value, list):
                    normalized = []
                    for item in value:
                        if isinstance(item, dict):
                            name = str(item.get("name", "")).strip().lower()
                            countries_raw = item.get("countries") or []
                            countries = [
                                str(c).strip().lower()
                                for c in countries_raw if str(c).strip()
                            ]
                            if name:
                                normalized.append({
                                    "name": name,
                                    "countries": countries,
                                })
                        elif isinstance(item, str) and item.strip():
                            # Formato legado (sem country) — preservado, mas
                            # _check_a_match_status no modo strict trata como
                            # exigindo country não vazio.
                            normalized.append({
                                "name": item.strip().lower(),
                                "countries": [],
                            })
                    out["premium_a_leagues"] = normalized
                    continue
                if key == "_highlighted_css_patterns" and isinstance(value, list):
                    out["highlighted_patterns"] = [
                        str(x).strip().lower() for x in value if str(x).strip()
                    ]
                    continue
                if key == "_premium_b_keywords" and isinstance(value, list):
                    out["premium_b_keywords"] = [
                        str(x).strip().lower() for x in value if str(x).strip()
                    ]
                    continue
                if key.startswith("_"):
                    continue
                if isinstance(value, list):
                    for slug in value:
                        if isinstance(slug, str) and slug.strip():
                            out["slugs"].add(slug.strip().lower())
    except (OSError, json.JSONDecodeError):
        pass

    _CONFIG_CACHE = out
    _CONFIG_FROM_PATH = path
    return out


# ──────────────────────────────────────────────────────────────────────
# Limpeza de nome de liga — remove sufixo de país concatenado
# ──────────────────────────────────────────────────────────────────────

# Lista canônica de sufixos de país que aparecem grudados em league_name
# pelo Flashscore quando o walker pega textContent do titleWrapper inteiro.
# Mantida explícita pra NÃO comer siglas legítimas como "MLS", "NWSL".
COUNTRY_SUFFIXES = [
    "BRASIL", "ARGENTINA", "EUA", "ESTADOS UNIDOS",
    "CHILE", "URUGUAI", "URUGUAY", "PARAGUAI", "PARAGUAY",
    "COLÔMBIA", "COLOMBIA", "EQUADOR", "ECUADOR", "PERU",
    "VENEZUELA", "BOLÍVIA", "BOLIVIA", "MÉXICO", "MEXICO",
    "INGLATERRA", "ESPANHA", "ALEMANHA", "ITÁLIA", "ITALIA",
    "FRANÇA", "FRANCA", "HOLANDA", "PORTUGAL",
    "BÉLGICA", "BELGICA", "DINAMARCA", "SUÉCIA", "SUECIA",
    "NORUEGA", "FINLÂNDIA", "FINLANDIA", "POLÔNIA", "POLONIA",
    "RÚSSIA", "RUSSIA", "TURQUIA", "GRÉCIA", "GRECIA",
    "ESCÓCIA", "ESCOCIA", "IRLANDA", "PAÍS DE GALES", "PAIS DE GALES",
    "AUSTRÁLIA", "AUSTRALIA", "JAPÃO", "JAPAO", "CHINA",
    "CORÉIA DO SUL", "COREIA DO SUL", "CORÉIA", "COREIA",
    "PANAMÁ", "PANAMA", "GUATEMALA", "EL SALVADOR", "COSTA RICA",
    "NICARÁGUA", "NICARAGUA", "CUBA", "PORTO RICO",
    "TRINIDAD E TOBAGO", "TRINIDAD",
    "HONDURAS", "JAMAICA", "REPÚBLICA DOMINICANA", "REPUBLICA DOMINICANA",
    "EGITO", "MARROCOS", "TUNÍSIA", "TUNISIA", "ARGÉLIA", "ARGELIA",
    "NIGÉRIA", "NIGERIA", "GANA", "GHANA", "CAMARÕES", "CAMAROES",
    "SENEGAL", "ÁFRICA DO SUL", "AFRICA DO SUL",
    "ARÁBIA SAUDITA", "ARABIA SAUDITA",
    "EMIRADOS ÁRABES UNIDOS", "EMIRADOS ARABES UNIDOS",
    "QATAR", "CATAR", "ISRAEL", "IRÃ", "IRAN",
    "ÍNDIA", "INDIA", "INDONÉSIA", "INDONESIA",
    "TAILÂNDIA", "TAILANDIA", "VIETNÃ", "VIETNA",
    "MALÁSIA", "MALASIA", "FILIPINAS", "CINGAPURA",
    "CANADÁ", "CANADA",
    "ROMÊNIA", "ROMENIA", "HUNGRIA", "REPÚBLICA TCHECA", "REPUBLICA TCHECA",
    "ESLOVÁQUIA", "ESLOVAQUIA", "ESLOVÊNIA", "ESLOVENIA",
    "CROÁCIA", "CROACIA", "SÉRVIA", "SERVIA",
    "BÓSNIA", "BOSNIA", "ALBÂNIA", "ALBANIA",
    "BULGÁRIA", "BULGARIA", "AUSTRIA", "ÁUSTRIA",
    "SUÍÇA", "SUICA", "ISLÂNDIA", "ISLANDIA",
    "UCRÂNIA", "UCRANIA", "LITUÂNIA", "LITUANIA",
    "LETÔNIA", "LETONIA", "ESTÔNIA", "ESTONIA",
    "AZERBAIJÃO", "AZERBAIJAO", "CAZAQUISTÃO", "CAZAQUISTAO",
    "GEÓRGIA", "GEORGIA",
    "KUWAIT", "BAHRAIN", "BAHREIN", "SERRA LEOA", "SIERRA LEONE",
    "ILHAS FAROÉ", "ILHAS FAROE", "FAROE ISLANDS",
    "OMÃ", "OMAN", "IÊMEN", "IEMEN", "JORDÂNIA", "JORDANIA",
    "LÍBANO", "LIBANO", "SÍRIA", "SIRIA", "IRAQUE", "IRAQ",
]

# Pré-compila padrões pra performance: ordenado por TAMANHO desc
# pra "ESTADOS UNIDOS" casar antes de "ESTADOS" sozinho.
_COUNTRY_PATTERNS = sorted(
    [(s, re.compile(r"\s*" + re.escape(s) + r"\s*:?\s*$", re.IGNORECASE))
     for s in COUNTRY_SUFFIXES],
    key=lambda x: -len(x[0])
)


def clean_league_name(name: str, country: Optional[str] = None) -> str:
    """Remove sufixo de país concatenado ao nome da liga.

    Estratégia: tenta primeiro o country específico (se fornecido), depois
    a lista canônica COUNTRY_SUFFIXES (ordenada por tamanho desc).
    NUNCA come siglas curtas tipo "MLS", "NWSL" (não estão na lista).

    Exemplos:
        "Brasileirão BetanoBRASIL:" → "Brasileirão Betano"
        "MLS Next ProEUA:"          → "MLS Next Pro"
        "Primera B Nacional (2ª Divisão)ARGENTINA:" → "Primera B Nacional (2ª Divisão)"
        "MLS"                       → "MLS"   (sem mudança)
        "NWSL"                      → "NWSL"  (sem mudança)
    """
    if not name:
        return name or ""
    cleaned = str(name).strip()

    # 1) Country específico tem prioridade (cobre ortografias customizadas)
    if country:
        pat = re.compile(r"\s*" + re.escape(country.upper()) + r"\s*:?\s*$",
                          re.IGNORECASE)
        new = pat.sub("", cleaned).strip()
        if new and new != cleaned:
            cleaned = new

    # 2) Lista canônica
    for _suf, pat in _COUNTRY_PATTERNS:
        new = pat.sub("", cleaned).strip()
        if new and new != cleaned:
            cleaned = new
            break

    return cleaned


def reset_cache() -> None:
    """Limpa cache — útil para testes que mockam o config."""
    global _CONFIG_CACHE, _CONFIG_FROM_PATH
    _CONFIG_CACHE = None
    _CONFIG_FROM_PATH = None


def load_premium_slugs(config_path: Optional[Path] = None) -> set:
    """Retrocompatibilidade — usado por testes antigos."""
    return _load_config(config_path)["slugs"]


# Regex para extrair slugs (home/away) da URL do Flashscore.
# Requer slug com ao menos 3 caracteres (a-z0-9-) e id alfanumérico ≥6 chars
# pra evitar falsos positivos em URLs malformadas.
_URL_TEAMS_RE = re.compile(
    r"/jogo/futebol/([a-z0-9][a-z0-9-]{2,}?)-([A-Za-z0-9]{6,})/([a-z0-9][a-z0-9-]{2,}?)-([A-Za-z0-9]{6,})",
    re.IGNORECASE,
)


def extract_team_slugs_from_url(url: str) -> tuple:
    """Extrai (home_slug, away_slug) da URL do Flashscore.
    Retorna ("", "") se a URL não seguir o padrão esperado
    (`/jogo/futebol/<slug3+>-<id6+>/<slug3+>-<id6+>`)."""
    if not url:
        return ("", "")
    m = _URL_TEAMS_RE.search(url)
    if not m:
        return ("", "")
    return (m.group(1).lower(), m.group(3).lower())


# ──────────────────────────────────────────────────────────────────────
# Classificação premium em 3 níveis (A > B > C)
# ──────────────────────────────────────────────────────────────────────

REASON_HIGHLIGHTED   = "flashscore_highlighted_league"
REASON_LEAGUE_NAME   = "premium_league_name"
REASON_TEAM_SLUG     = "premium_team_slug"
REASON_NONE          = ""

# Níveis hierárquicos do premium
LEVEL_A    = "A"      # Premium principal — prioridade máxima
LEVEL_B    = "B"      # Premium secundário — cobertura premium
LEVEL_C    = "C"      # Fallback por slug/time grande (sem liga detectada)
LEVEL_NONE = "NONE"   # Não-premium


# Status retornado por _check_a_match_status:
_A_OK         = "A_OK"          # Nome bate A E country valida (ou tolerância)
_A_REJECTED   = "A_REJECTED"    # Nome bate A MAS country não valida (impersonator)
_A_NO_MATCH   = "A_NO_MATCH"    # Nome NÃO bate nenhuma entry A


def _check_a_match_status(league_name: str, country: str, config: dict,
                           *, strict: bool = True) -> str:
    """Verifica se o nome da liga bate uma A-league no whitelist + valida country.

    Args:
        league_name: nome da liga (texto vindo do header DOM).
        country: país (texto vindo do bloco de país do Flashscore).
        config: dict do _load_config (com `premium_a_leagues`).
        strict: se True, country vazio + nome bate A → A_REJECTED.
                Se False, country vazio é tolerado (uso interno em testes
                de unidade que chamam classify_premium_level direto).

    Returns:
        _A_OK         — nome bate A E país valida
        _A_REJECTED   — nome bate A MAS país NÃO valida (impersonator filter)
        _A_NO_MATCH   — nome NÃO bate nenhuma entry A
    """
    if not league_name:
        return _A_NO_MATCH

    ln = league_name.lower()
    ctry = (country or "").lower().strip()

    found_name_but_country_failed = False

    for entry in config.get("premium_a_leagues", []):
        name = entry.get("name", "")
        if not name or name not in ln:
            continue

        countries = entry.get("countries", [])

        # Entrada sem countries definidos = sem restrição de país (rara).
        if not countries:
            return _A_OK

        # Verifica se o país (campo) bate qualquer país permitido,
        # OU se o nome da liga já contém o país internamente
        # (ex.: "Inglaterra - Premier League").
        def _country_validates() -> bool:
            for allowed in countries:
                if not allowed:
                    continue
                if ctry and (allowed in ctry or ctry in allowed):
                    return True
                # Tolerância: o país aparece dentro do próprio league_name
                if allowed in ln:
                    return True
            return False

        if _country_validates():
            return _A_OK

        # Modo lenient (strict=False): country vazio + nome bate → A_OK
        # (preserva compat com testes unitários que chamam sem country).
        if not strict and not ctry:
            return _A_OK

        # Nome bateu mas country falhou → marca rejeição e continua olhando
        # outras entries (uma A diferente pode bater com este country).
        found_name_but_country_failed = True

    return _A_REJECTED if found_name_but_country_failed else _A_NO_MATCH


def _matches_b_keyword(league_name: str, config: dict) -> bool:
    """True se o nome contém alguma keyword de liga secundária (Sub-20, NWSL, etc.)."""
    if not league_name:
        return False
    ln = league_name.lower()
    return any(kw in ln for kw in config.get("premium_b_keywords", []))


def classify_premium_level(league_name: str, reason: str,
                            country: str = "",
                            config_path: Optional[Path] = None) -> str:
    """Classifica o premium em níveis A/B/C/NONE.

    Args:
        league_name: nome da liga (já limpo de sufixo de país).
        reason: REASON_HIGHLIGHTED | REASON_LEAGUE_NAME | REASON_TEAM_SLUG | REASON_NONE.
        country: país (opcional — necessário em modo strict para promoção A).

    Regra (na ordem):
      1. reason == REASON_NONE        → LEVEL_NONE
      2. reason == REASON_TEAM_SLUG   → LEVEL_C  (fallback por time)
      3. league_name vazio            → LEVEL_B  (cobertura genérica destacada)
      4. nome bate _premium_b_keywords → LEVEL_B (checado ANTES de A)
      5. nome bate _premium_a_leagues
         + country valida              → LEVEL_A
      6. nome bate _premium_a_leagues
         MAS country NÃO valida        → LEVEL_B (fallback defensivo,
                                                  classify_premium já rejeitou)
      7. default                       → LEVEL_B
    """
    if not reason or reason == REASON_NONE:
        return LEVEL_NONE
    if reason == REASON_TEAM_SLUG:
        return LEVEL_C

    cfg = _load_config(config_path)

    # ✨ v3.9 — CSS destacado pelo Flashscore = LEVEL_A direto.
    # Flashscore só destaca em amarelo (event__header--type-top, is-highlighted,
    # wcl-isHighlighted, etc.) ligas/jogos que são importância máxima — confiar
    # no app é mais seguro que tentar adivinhar pela whitelist de nomes.
    # EXCEÇÃO: se nome bate keyword B explícita (Sub-20, Reservas, Feminino,
    # etc.) — aí continua B mesmo destacado.
    if reason == REASON_HIGHLIGHTED:
        if league_name and _matches_b_keyword(league_name, cfg):
            return LEVEL_B
        return LEVEL_A

    if not league_name:
        return LEVEL_B  # sem CSS destacado e sem nome — cobertura secundária

    # 4) Keywords B (antes de A — "MLS Next Pro" precisa virar B mesmo
    #    contendo "mls" que está em premium_a_leagues)
    if _matches_b_keyword(league_name, cfg):
        return LEVEL_B

    # 5/6) A-list com validação de country (lenient — call direto, sem context).
    status = _check_a_match_status(league_name, country, cfg, strict=False)
    if status == _A_OK:
        return LEVEL_A
    # Se rejeitado por country, defensivo retorna B
    # (classify_premium já bloqueou is_premium nesse caso).
    return LEVEL_B


def _is_highlighted_css(css_classes, config: dict) -> bool:
    """True se alguma class do cabeçalho casa um padrão de destaque."""
    if not css_classes:
        return False
    if isinstance(css_classes, str):
        blob = css_classes.lower()
    else:
        blob = " ".join(str(c).lower() for c in css_classes)
    return any(pat in blob for pat in config["highlighted_patterns"])


def _matches_premium_slug(url, config: dict) -> bool:
    """True se home_slug ou away_slug está no whitelist de times E a URL
    tem padrão completo /jogo/futebol/<slug>-<id6+>/<slug>-<id6+>."""
    slugs = config["slugs"]
    if not slugs or not url:
        return False
    home, away = extract_team_slugs_from_url(url)
    if not home and not away:
        # URL não tem padrão completo (sem times) → não C
        return False
    return home in slugs or away in slugs


def classify_premium(url: str,
                     league_name: Optional[str] = None,
                     league_country: Optional[str] = None,
                     league_css_classes=None,
                     config_path: Optional[Path] = None) -> dict:
    """Classifica um jogo como premium aplicando as 3 regras em ordem +
    determina o NÍVEL (A/B/C/NONE) com validação country+competition.

    REGRA DE PROTEÇÃO: se o nome da liga bate uma A-league famosa (Premier
    League, Bundesliga, etc.) MAS o country NÃO bate a lista de países
    permitidos → is_premium=False (filtra impersonators).

    Args:
        url: URL do Flashscore (obrigatório).
        league_name: nome da liga conforme texto do header DOM (opcional).
        league_country: país conforme bloco do Flashscore (opcional).
        league_css_classes: lista ou string com as CSS classes do header.
        config_path: opcional, para testes.

    Returns:
        {
            "is_premium": bool,
            "reason": str (REASON_*),
            "level":  str (LEVEL_A | LEVEL_B | LEVEL_C | LEVEL_NONE),
            "league_name": str (limpo de sufixo de país),
            "country": str,
        }
    """
    cfg = _load_config(config_path)
    league_name_raw = (league_name or "").strip()
    league_country = (league_country or "").strip()
    # SEMPRE limpa antes de qualquer match (evita "Brasileirão BetanoBRASIL:")
    cleaned_name = clean_league_name(league_name_raw, country=league_country)

    def _ret_not_premium() -> dict:
        return {
            "is_premium": False,
            "reason": REASON_NONE,
            "level": LEVEL_NONE,
            "league_name": cleaned_name,
            "country": league_country,
        }

    def _ret_premium(reason: str, level: Optional[str] = None) -> dict:
        if level is None:
            level = classify_premium_level(
                cleaned_name, reason,
                country=league_country, config_path=config_path,
            )
        return {
            "is_premium": True,
            "reason": reason,
            "level": level,
            "league_name": cleaned_name,
            "country": league_country,
        }

    # ──────────────────────────────────────────────────────────────
    # FILTRO ANTI-IMPERSONATOR (precede todas as regras de promoção):
    # se o nome bate uma A-league famosa MAS o country NÃO valida,
    # o jogo NÃO é premium, INDEPENDENTE de CSS destacado ou slug.
    # Isso bloqueia "Premier League | Kuwait", "Bundesliga | Singapura",
    # "Premier League | Serra Leoa", "Premier League | Ilhas Faroé", etc.
    # ──────────────────────────────────────────────────────────────
    a_status_strict = _check_a_match_status(
        cleaned_name, league_country, cfg, strict=True,
    )
    if a_status_strict == _A_REJECTED:
        return _ret_not_premium()

    # A) CSS destacado (prioridade máxima — Flashscore explicitamente destacou)
    if _is_highlighted_css(league_css_classes, cfg):
        return _ret_premium(REASON_HIGHLIGHTED)

    # B) Nome da liga bate A-league com country válido → premium nível A.
    #    a_status_strict == _A_OK significa: nome + country validaram.
    if a_status_strict == _A_OK:
        return _ret_premium(REASON_LEAGUE_NAME, level=LEVEL_A)

    # C) Slug do time (legado) — só conta se a URL tiver padrão completo
    #    /jogo/futebol/<slug3+>-<id6+>/<slug3+>-<id6+> E slug bater whitelist.
    if _matches_premium_slug(url, cfg):
        return _ret_premium(REASON_TEAM_SLUG, level=LEVEL_C)

    return _ret_not_premium()


# ──────────────────────────────────────────────────────────────────────
# Retrocompat: API antiga (apenas slug)
# ──────────────────────────────────────────────────────────────────────


def is_premium_url(url: str, config_path: Optional[Path] = None) -> bool:
    """Retrocompat: True se URL bate slug premium (regra C apenas).

    Mantido para chamadas antigas no Catalog. Para classificação completa
    com regras A e B, use classify_premium().
    """
    cfg = _load_config(config_path)
    return _matches_premium_slug(url, cfg)


def detected_premium_team(url: str, config_path: Optional[Path] = None) -> str:
    """Retrocompat: retorna slug do time premium (home primeiro, depois away)."""
    cfg = _load_config(config_path)
    slugs = cfg["slugs"]
    if not slugs:
        return ""
    home, away = extract_team_slugs_from_url(url)
    if home in slugs:
        return home
    if away in slugs:
        return away
    return ""
