"""
Discovery — extrai lista de jogos ao vivo do Flashscore.

Lógica isolada do live_daemon.py. Mesma sequência JS (clica AO VIVO,
expande ligas colapsadas, coleta hrefs '/jogo/'), mesmo fallback,
mesma normalização de URL com hash de stats.

Usado pelo modo --use-watchlist do live_daemon.py.

NÃO substitui FlashscoreReader.read_match — apenas descobre URLs de jogos.
A extração de stats continua sendo feita por src.flashscore_adapter.FlashscoreReader.
"""
import re
from typing import Optional


def _extract_match_id(url: str) -> str:
    """Espelha src.flashscore_adapter.FlashscoreReader._extract_match_id."""
    m = re.search(r"/match/([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}"
    m = re.search(r"mid=([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}"
    m = re.search(r"/jogo/[^/]+/[^/]+-([A-Za-z0-9]+)/[^/]+-([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}_{m.group(2)}"
    return "FS_UNKNOWN"


def _normalize_stats_url(url: str) -> str:
    """Remove hash existente e anexa hash de match-statistics.

    CORREÇÃO V2: NÃO colocar barra entre query string e hash.
    URL com ?mid=xxx termina sem barra (rstrip remove), e a barra extra
    antes do # quebrava o parsing do Flashscore (mid virava "xxx/").
    """
    base = url.split("#")[0].rstrip("/")
    return base + "#/match-summary/match-statistics/0"


_JS_CLICK_AO_VIVO = """
() => {
  const tab = document.querySelector(
    '.filters__tab[data-analytics-alias="live"], [data-analytics-alias="live"], [class*="filters__tab"][data-value="live"]'
  );
  if (tab) { tab.click(); return true; }
  const tabs = document.querySelectorAll('.filters__tab, [class*="filters__tab"], [class*="filters__text"], [role="tab"], button, a');
  for (const t of tabs) {
    const txt = (t.textContent || '').trim().toLowerCase();
    if (txt === 'ao vivo' || txt === 'live' || txt.startsWith('ao vivo (') || txt.startsWith('live (')) {
      t.click(); return true;
    }
  }
  return false;
}
"""

_JS_EXTRACT_ALL_MATCH_URLS = """
() => {
  const urls = new Set();
  document.querySelectorAll('a[href*="/jogo/"], a[href*="/match/"]').forEach(a => {
    if (a.href) urls.add(a.href);
  });
  document.querySelectorAll('[id^="g_1_"]').forEach(el => {
    const rawId = (el.id || '').replace(/^g_1_/, '').trim();
    if (rawId && rawId.length >= 5) {
      urls.add(`https://www.flashscore.com.br/jogo/${rawId}/#/resumo/estatisticas/total/`);
    }
  });
  document.querySelectorAll('.event__match').forEach(el => {
    const a = el.querySelector('a');
    if (a && a.href) urls.add(a.href);
    if (el.id && el.id.startsWith('g_1_')) {
      const mid = el.id.substring(4);
      urls.add(`https://www.flashscore.com.br/jogo/${mid}/#/resumo/estatisticas/total/`);
    }
  });
  return Array.from(urls);
}
"""

_JS_EXPAND_LEAGUES = """
() => {
  document.querySelectorAll('[class*="event__expander"], [class*="wcl-scores"]').forEach(el => {
    const p = el.closest('[class*="leagues--live"], [class*="sportName"]');
    if (p) p.click();
  });
  document.querySelectorAll('span').forEach(s => {
    if (/exibir jogos?/i.test(s.textContent)) {
      const clickable = s.closest('[role="button"], a, [class*="event__expander"]') || s.parentElement;
      if (clickable) clickable.click();
    }
  });
}
"""


# Walker que extrai metadados da liga pra cada link de jogo.
#
# REGRA DIRETA (Flashscore 2026 — confirmado via --debug-dom-game):
#   <div class="headerLeague__wrapper">     ← header (previousSibling do sportName)
#     <div class="wcl-header_HrElx wcl-pinned_dRFvU headerLeague headerLeague--has-star">
#       <div class="headerLeague__title-text">Brasileirão Betano</div>
#       <div class="headerLeague__category">BRASIL:</div>
#     </div>
#   </div>
#   <div class="sportName soccer">          ← container de jogos da liga
#     <div class="event__match">
#       <a href="/jogo/...">                 ← link do jogo
#     </div>
#     ...
#
# Algoritmo CORRETO (após investigação --debug-league-walker):
#   O headerLeague__wrapper NÃO é previousSibling do sportName — é FILHO dele,
#   intercalado com os event__match. Cada sportName contém VÁRIAS ligas.
#
#   <div class="sportName soccer">
#     <div class="headerLeague__wrapper">    ← header da liga A
#     <div class="event__match"><a href="...A1">
#     <div class="event__match"><a href="...A2">
#     <div class="headerLeague__wrapper">    ← header da liga B (próxima)
#     <div class="event__match"><a href="...B1">
#
#   Algoritmo:
#   1. Pra cada DIV.sportName: percorre children diretos em ordem documental.
#   2. currentLeague = null
#   3. Se child é headerLeague__wrapper → parseia e atualiza currentLeague.
#   4. Se child é event__match → atribui currentLeague a todos os links dentro.
#   5. Se event__match aparece sem currentLeague → falha registrada.
#
# Retorna {result, stats, failures, failure_sample}.
_JS_EXTRACT_LEAGUE_META = r"""
() => {
  // Padrões que identificam cada tipo de elemento
  const hasClass = (el, subs) => {
    if (!el) return false;
    const c = (typeof el.className === 'string') ? el.className.toLowerCase() : '';
    return subs.some(s => c.indexOf(s.toLowerCase()) !== -1);
  };
  const STAR_SUBSTR = [
    'headerleague--has-star', 'headerleague--star',
    'wcl-pinned', 'is-pinned',
    'is-favourite-league', 'favourite-league',
    'is-favorite-league', 'favorite-league',
    'is-highlighted', 'wcl-ishighlighted'
  ];

  const titleCase = (s) => {
    if (!s) return '';
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  };

  // Parseia um headerLeague__wrapper e retorna {league, country, css, star, text}
  const parseLeagueHeader = (wrapper) => {
    // PRIORIDADE 1: headerLeague__title-text (mais específico, só nome puro).
    //   Bug evitado: [class*="headerLeague__title"] também casa __titleWrapper
    //   que contém país concatenado. Buscamos -text PRIMEIRO.
    let titleEl = wrapper.querySelector('[class*="headerLeague__title-text"]');
    if (!titleEl) {
      // Fallback: __title PURO, excluindo qualquer "Wrapper"
      const candidates = wrapper.querySelectorAll('[class*="headerLeague__title"]');
      for (const el of candidates) {
        const cls = (typeof el.className === 'string') ? el.className : '';
        if (cls.toLowerCase().indexOf('wrapper') === -1) { titleEl = el; break; }
      }
    }
    const catEl = wrapper.querySelector(
      '[class*="headerLeague__category"], [class*="headerLeague__meta"]'
    );
    let league = titleEl ? (titleEl.textContent || '').trim() : '';
    let country = catEl ? (catEl.textContent || '').replace(/[:\s]+$/, '').trim() : '';

    // Fallback regex se sub-elementos não acharam
    if (!league) {
      const fullTxt = (wrapper.textContent || '').trim().replace(/\s+/g, ' ');
      const m = fullTxt.match(/^(.+?)\s*([A-ZÁÀÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝ]{3,})\s*:/);
      if (m) {
        league = m[1].trim();
        if (!country) country = m[2].trim();
      } else {
        league = fullTxt.slice(0, 80);
      }
    }
    if (country) country = titleCase(country);

    // LIMPEZA FINAL: remove sufixos de país concatenados ao league_name.
    // Cobre casos onde o título veio do titleWrapper:
    //   "Brasileirão BetanoBRASIL:" → "Brasileirão Betano"
    //   "Brasileirão Série BBRASIL:" → "Brasileirão Série B"
    //   "Premier LeagueINGLATERRA:" → "Premier League"
    if (league) {
      league = league.replace(
        /\s*[A-ZÁÀÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝ]{3,}\s*:?\s*$/, ''
      ).trim();
    }

    // Coleta TODAS as classes (wrapper + descendentes) pra detectar star
    const css = [];
    const pushCls = (el) => {
      if (el && typeof el.className === 'string') {
        el.className.split(/\s+/).forEach(c => { if (c) css.push(c); });
      }
    };
    pushCls(wrapper);
    wrapper.querySelectorAll('*').forEach(pushCls);

    const star = css.some(c =>
      STAR_SUBSTR.some(s => c.toLowerCase().indexOf(s) !== -1)
    );

    // Background amarelo como sinal adicional
    let yellow = star;
    if (!yellow && window.getComputedStyle) {
      try {
        const cs = window.getComputedStyle(wrapper);
        const m = (cs.backgroundColor || '').match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
        if (m) {
          const r = +m[1], g = +m[2], b = +m[3];
          if (r >= 220 && g >= 180 && b <= 120) yellow = true;
        }
      } catch (e) {}
    }

    return {
      league_name: league,
      country: country,
      css_classes: css,
      star_detected: star,
      yellow_bg_detected: yellow,
      header_text: (wrapper.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200),
    };
  };

  // ─── ALGORITMO PRINCIPAL ──────────────────────────────────────────
  // Pra cada container DIV.sportName, percorre children DIRETOS em ordem
  // documental tracking currentLeague. headerLeague__wrapper atualiza ctx;
  // event__match recebe o ctx atual.
  const result = {};
  const stats = {
    total_links: 0,
    sportName_containers_found: 0,
    headerLeague_wrappers_found: 0,
    event_match_children_found: 0,
    links_com_current_league_context: 0,
    links_com_league_name_extraida: 0,
    links_com_country_extraida: 0,
    links_com_highlighted_true: 0,
    links_fora_de_sportName_container: 0,
  };
  const failures = {};
  const failure_sample = {};
  const recordFail = (type, href) => {
    failures[type] = (failures[type] || 0) + 1;
    if (!failure_sample[type]) failure_sample[type] = href;
  };

  const containers = document.querySelectorAll('[class*="sportName"]');
  stats.sportName_containers_found = containers.length;

  for (const container of containers) {
    let currentLeague = null;
    for (const child of container.children) {
      // Header da liga
      if (hasClass(child, ['headerLeague__wrapper', 'headerLeague'])) {
        stats.headerLeague_wrappers_found++;
        currentLeague = parseLeagueHeader(child);
        continue;
      }
      // Jogo (event__match)
      if (hasClass(child, ['event__match'])) {
        stats.event_match_children_found++;
        const links = child.querySelectorAll('a[href*="/jogo/"]');
        for (const a of links) {
          if (currentLeague) {
            result[a.href] = Object.assign({header_found: true}, currentLeague);
            stats.links_com_current_league_context++;
            if (currentLeague.league_name) stats.links_com_league_name_extraida++;
            if (currentLeague.country) stats.links_com_country_extraida++;
            if (currentLeague.star_detected) stats.links_com_highlighted_true++;
          } else {
            recordFail('event_match_sem_currentLeague', a.href);
          }
        }
      }
    }
  }

  // Conta TODOS os links da página e detecta os que ficaram fora
  const allLinks = document.querySelectorAll('a[href*="/jogo/"]');
  stats.total_links = allLinks.length;
  for (const a of allLinks) {
    if (!result[a.href]) {
      stats.links_fora_de_sportName_container++;
      recordFail('link_fora_de_sportName_container', a.href);
    }
  }

  return {result: result, stats: stats,
          failures: failures, failure_sample: failure_sample};
}
"""



def http_fallback_discover_live() -> dict:
    """Fallback ultra-rápido via HTTP direto para o feed live do Flashscore caso o DOM do navegador não entregue jogos."""
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo",
        "Referer": "https://www.flashscore.com.br/"
    }
    games = []
    league_meta = {}
    
    # 1. Tenta feed leve
    feed_urls = [
        "https://www.flashscore.com.br/x/feed/f_1_0_3_pt-br_1",
        "https://www.flashscore.com.br/futebol/ao-vivo/",
        "https://www.flashscore.mobi/"
    ]
    
    for u in feed_urls:
        try:
            r = requests.get(u, headers=headers, timeout=6)
            if r.status_code == 200 and len(r.text) > 50:
                txt = r.text
                # Match IDs do feed Flashscore (~AA÷ID ou id="g_1_ID")
                mids = re.findall(r'~AA÷([A-Za-z0-9]+)', txt)
                if not mids:
                    mids = re.findall(r'id="g_1_([A-Za-z0-9]+)"', txt)
                if not mids:
                    mids = re.findall(r'/jogo/[^/]+/([A-Za-z0-9]+)', txt)
                
                # Deduplica mantendo ordem
                seen = set()
                current_league = "Geral"
                current_country = "Internacional"
                
                # Tenta parsear blocos de liga se for formato ~ZA÷
                if "~ZA÷" in txt:
                    sections = txt.split("~ZA÷")
                    for sec in sections[1:]:
                        l_m = re.match(r'([^¬]+)', sec)
                        l_name = l_m.group(1) if l_m else "Geral"
                        c_m = re.search(r'~ZE÷([^¬]+)', sec)
                        c_name = c_m.group(1) if c_m else "Internacional"
                        sec_mids = re.findall(r'~AA÷([A-Za-z0-9]+)', sec)
                        for mid in sec_mids:
                            if mid not in seen:
                                seen.add(mid)
                                url = f"https://www.flashscore.com.br/jogo/{mid}/#/resumo/estatisticas/total/"
                                games.append((mid, url))
                                league_meta[mid] = {
                                    "league_name": l_name.strip(),
                                    "country": c_name.strip(),
                                    "css_classes": [],
                                    "header_text": f"{c_name}: {l_name}",
                                    "header_found": True,
                                    "yellow_bg_detected": False,
                                    "star_detected": False,
                                }
                elif mids:
                    for mid in mids:
                        if mid not in seen:
                            seen.add(mid)
                            url = f"https://www.flashscore.com.br/jogo/{mid}/#/resumo/estatisticas/total/"
                            games.append((mid, url))
                            league_meta[mid] = {
                                "league_name": "FlashScore Live",
                                "country": "Ao Vivo",
                                "css_classes": [],
                                "header_text": "Live",
                                "header_found": True,
                                }
                if len(games) > 0:
                    break
        except Exception:
            continue

    return {
        "games": games,
        "league_meta": league_meta,
        "league_stats": {},
        "league_failures": {},
        "league_failure_sample": {},
        "dom_detection_failed": False,
        "total_found": len(games),
        "ao_vivo_found": True,
        "live_only": True,
        "error": None,
    }


def discover_live_games(context, base_url: str,
                        cookie_accept_fn=None,
                        timeout_ms: int = 15000) -> dict:
    """
    Abre o Flashscore, ativa filtro AO VIVO, expande ligas e coleta links dos jogos.
    Com fallback robusto automático se a renderização inicial não entregar elementos.
    """
    page = None
    try:
        page = context.new_page()
        # Navega para a aba de futebol ao vivo diretamente
        target_url = base_url.rstrip("/")
        if not target_url.endswith("/ao-vivo") and not target_url.endswith("/live"):
            target_url = f"{target_url}/futebol/ao-vivo/"
        
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)

        if cookie_accept_fn:
            try:
                cookie_accept_fn(page)
            except Exception:
                pass

        ao_vivo_found = False
        try:
            page.wait_for_selector('.filters__tab, [class*="event__match"], [id^="g_1_"]', timeout=4000, state="attached")
            ao_vivo_found = bool(page.evaluate(_JS_CLICK_AO_VIVO))
            page.wait_for_timeout(800)
        except Exception:
            ao_vivo_found = True

        try:
            page.evaluate(_JS_EXPAND_LEAGUES)
            page.wait_for_timeout(800)
        except Exception:
            pass

        try:
            all_links = page.evaluate(_JS_EXTRACT_ALL_MATCH_URLS) or []
        except Exception:
            all_links = page.eval_on_selector_all(
                'a[href*="/jogo/"], a[href*="/match/"]',
                "els => Array.from(new Set(els.map(e => e.href)))"
            )

        league_meta_by_href = {}
        dom_detection_failed = False
        league_stats = {}
        league_failures = {}
        league_failure_sample = {}
        try:
            walker_result = page.evaluate(_JS_EXTRACT_LEAGUE_META) or {}
            league_meta_by_href = walker_result.get("result", {}) or {}
            league_stats = walker_result.get("stats", {}) or {}
            league_failures = walker_result.get("failures", {}) or {}
            league_failure_sample = walker_result.get("failure_sample", {}) or {}
        except Exception:
            dom_detection_failed = True

        seen = set()
        games = []
        league_meta = {}
        for link in all_links:
            url = _normalize_stats_url(link)
            if url in seen:
                continue
            seen.add(url)
            mid = _extract_match_id(url)
            games.append((mid, url))
            meta = league_meta_by_href.get(link) or league_meta_by_href.get(url)
            if meta:
                css = list(meta.get("css_classes") or [])
                if meta.get("yellow_bg_detected") or meta.get("star_detected"):
                    if "is-highlighted" not in css:
                        css.append("is-highlighted")
                league_meta[mid] = {
                    "league_name": meta.get("league_name", ""),
                    "country": meta.get("country", ""),
                    "css_classes": css,
                    "header_text": meta.get("header_text", ""),
                    "header_found": bool(meta.get("header_found")),
                    "yellow_bg_detected": bool(meta.get("yellow_bg_detected")),
                    "star_detected": bool(meta.get("star_detected")),
                    "failure_type": meta.get("failure_type", ""),
                }

        # Se Playwright não achou partidas na página, recorre ao HTTP feed de contingência
        if len(games) == 0:
            print("ℹ️ [Discovery] 0 jogos no DOM. Acionando contingência HTTP feed...")
            fb = http_fallback_discover_live()
            if len(fb.get("games", [])) > 0:
                return fb

        return {
            "games": games,
            "league_meta": league_meta,
            "league_stats": league_stats,
            "league_failures": league_failures,
            "league_failure_sample": league_failure_sample,
            "dom_detection_failed": dom_detection_failed,
            "total_found": len(all_links),
            "ao_vivo_found": ao_vivo_found,
            "live_only": ao_vivo_found,
            "error": None,
        }

    except Exception as e:
        print(f"⚠️ [Discovery DOM Exception]: {e}. Usando contingência HTTP...")
        return http_fallback_discover_live()
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
