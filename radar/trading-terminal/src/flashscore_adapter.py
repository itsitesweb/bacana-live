"""
Flashscore Adapter — converte ExtratorFlashscore (PAINEL_V8) → MatchState (V1.2).

Reaproveita o extrator existente sem modificá-lo.
Adiciona extração de red cards via DOM.

SEM LIVE loop. SEM execução de aposta. SEM odd/preço/EV.
"""
import sys
import json
import re
from pathlib import Path
from typing import Optional

# Adiciona PAINEL_V8 ao path para importar extrator
PAINEL_DIR = str(Path(__file__).parent.parent.parent / "PAINEL_V8")
if PAINEL_DIR not in sys.path:
    sys.path.insert(0, PAINEL_DIR)

from playwright.sync_api import sync_playwright, Page, BrowserContext
from .models import MatchState


# ─── DOM Script para red cards ──────────────────────────────────────────

SCRIPT_RED_CARDS = r"""
() => {
  const cards = document.querySelectorAll('[class*="smh__incident"]');
  let homeRed = 0, awayRed = 0;
  cards.forEach(c => {
    const text = c.textContent || '';
    const isRed = c.querySelector('[class*="card-ico--red"]') ||
                  c.querySelector('[class*="redCard"]') ||
                  text.includes('Red card');
    if (!isRed) return;
    const isHome = c.closest('[class*="smh__home"]') !== null;
    if (isHome) homeRed++;
    else awayRed++;
  });
  return JSON.stringify({home_red: homeRed, away_red: awayRed});
}
"""


# ─── Classe principal ──────────────────────────────────────────────────

class FlashscoreReader:
    """Lê UM jogo do Flashscore e retorna MatchState pronto para run_scan()."""

    def __init__(self, headless: bool = True, locale: str = "pt-BR",
                 browser_data_dir: str = None):
        self.headless = headless
        self.locale = locale
        # Diretório próprio — NÃO compartilhar com PAINEL_V8 (conflito de lock)
        if browser_data_dir:
            self._browser_dir = browser_data_dir
        else:
            own_dir = str(Path(__file__).parent.parent / ".browser_data")
            self._browser_dir = own_dir
        self._pw = None
        self._context: Optional[BrowserContext] = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self._browser_dir,
            headless=self.headless,
            locale=self.locale,
            viewport={"width": 1366, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )
        try:
            self._context.route(
                "**/*.{png,jpg,jpeg,webp,gif,svg,woff,woff2,ttf,otf,mp4,mp3}",
                lambda route: route.abort() if route.request.resource_type in ("image", "font", "media") else route.continue_()
            )
        except Exception:
            pass
        return self

    def __exit__(self, *args):
        # Shutdown defensivo: se o browser já fechou (TargetClosedError no
        # Ctrl+C), engole o erro pra não derrubar o supervisor. Mesmo se
        # _context.close() falhar, ainda tentamos _pw.stop().
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    # R1 (v2.10): teto duro total de 30s por jogo. Soma de:
    #   goto(10s) + reload(10s) + wait_for_selector(6s) + sample(2.5s) ≈ 28s
    # Wrapper externo com Timer aborta a leitura se o total estourar.
    READ_MATCH_HARD_LIMIT_S = 30

    def read_match(self, url: str, match_id: str = None,
                   timeout_ms: int = 20000) -> Optional[MatchState]:
        """Abre URL do Flashscore, extrai stats, retorna MatchState ou None.

        Executa de forma 100% thread-safe dentro do event loop do Playwright
        usando timeouts nativos por etapa para evitar corrupção de greenlet.
        """
        if match_id is None:
            match_id = self._extract_match_id(url)

        per_step_ms = max(3000, min(int(timeout_ms), 10000))
        wait_selector_ms = max(2000, min(int(timeout_ms), 6000))

        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(per_step_ms)

            # 1) navegar
            stats_url = self._ensure_stats_url(url)
            page.goto(stats_url, wait_until="domcontentloaded",
                       timeout=per_step_ms)
            self._accept_cookies(page)
            # 2) reload
            page.reload(wait_until="domcontentloaded", timeout=per_step_ms)
            self._accept_cookies(page)
            # 3) esperar stats carregarem
            try:
                page.wait_for_selector('[class*="wcl-category"]',
                                          timeout=wait_selector_ms)
            except Exception:
                return None
            # 4) sampling defensivo
            page.wait_for_timeout(2000)
            # 5) extrair
            raw = page.evaluate(self._get_extraction_script())
            dados = json.loads(raw)
            try:
                red_raw = page.evaluate(SCRIPT_RED_CARDS)
                red_data = json.loads(red_raw)
            except Exception:
                red_data = {"home_red": 0, "away_red": 0}
            return self._to_match_state(dados, red_data, match_id)
        except Exception as e:
            print(f"  ⚠️  Erro ao extrair {url[-40:]}: {str(e)[:80]}")
            return None
        finally:
            if page:
                try: page.close()
                except Exception: pass

    def _ensure_stats_url(self, url: str) -> str:
        """Garante que a URL aponta para a aba ESTATÍSTICAS completa.

        CORREÇÃO V3 (30/mai/2026):
          Flashscore renomeou a página. O hash antigo
          '#/match-summary/match-statistics/0' carrega apenas o preview do
          SUMÁRIO (5 stats, SEM xGOT). A aba ESTATÍSTICAS completa (80
          rows, com xGOT) fica em '.../resumo/estatisticas/total/?mid=...'.

          Constrói a URL nova preservando ?mid= e demais query params.
          Insere '/resumo/estatisticas/total/' ANTES do '?'.

          Idempotente: se a URL já estiver no formato correto, devolve igual.
          Remove qualquer hash antigo.
        """
        # Remove hash legado
        clean = url.split("#")[0]
        # Idempotência: já tem /resumo/estatisticas/total/ no path
        if "/resumo/estatisticas/total/" in clean:
            return clean
        # Separa path da query string
        if "?" in clean:
            path, _, query = clean.partition("?")
            query = "?" + query
        else:
            path, query = clean, ""
        # Garante 1 barra antes de "resumo"
        path = path.rstrip("/") + "/resumo/estatisticas/total/"
        return path + query

    def _extract_match_id(self, url: str) -> str:
        """Extrai match_id da URL."""
        # /match/K8bh3OkJ/ ou ?mid=K8bh3OkJ
        m = re.search(r"/match/([A-Za-z0-9]+)", url)
        if m:
            return f"FS_{m.group(1)}"
        m = re.search(r"mid=([A-Za-z0-9]+)", url)
        if m:
            return f"FS_{m.group(1)}"
        # /jogo/futebol/team1-ID/team2-ID/ → usar últimos 2 IDs como match_id
        m = re.search(r"/jogo/[^/]+/[^/]+-([A-Za-z0-9]+)/[^/]+-([A-Za-z0-9]+)", url)
        if m:
            return f"FS_{m.group(1)}_{m.group(2)}"
        return "FS_UNKNOWN"

    def _accept_cookies(self, page: Page):
        """Aceita cookies/consent banners."""
        for s in ['button:has-text("ACEITAR")', 'button:has-text("Accept")',
                  'button:has-text("AGREE")', '#onetrust-accept-btn-handler',
                  'button:has-text("Aceitar tudo")']:
            try:
                btn = page.locator(s).first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    def _get_extraction_script(self) -> str:
        """Script JS para extrair stats e metadados de liga/país do DOM do Flashscore."""
        return r"""
        () => {
          const rows = document.querySelectorAll('[class*="wcl-category"], [class*="statRow"], [class*="category__"]');
          const stats = {};
          rows.forEach(r => {
            const labelEl = r.querySelector('[class*="categoryName"], [class*="category_"], [class*="statName"]');
            if (!labelEl) return;
            const name = labelEl.textContent.trim();
            if (!name) return;
            let homeVal = '', awayVal = '';
            
            const homeEl = r.querySelector('[class*="homeValue"], [class*="home_"], [class*="value--home"], [class*="categoryHomeValue"]');
            const awayEl = r.querySelector('[class*="awayValue"], [class*="away_"], [class*="value--away"], [class*="categoryAwayValue"]');
            if (homeEl && awayEl) {
              homeVal = homeEl.textContent.trim();
              awayVal = awayEl.textContent.trim();
            } else {
              const fullText = r.textContent.trim();
              const labelIdx = fullText.indexOf(name);
              if (labelIdx > 0) {
                homeVal = fullText.substring(0, labelIdx).trim();
                awayVal = fullText.substring(labelIdx + name.length).trim();
              }
            }
            stats[name] = { h: homeVal, a: awayVal };
          });

          // Placar e Status
          const scoreEl = document.querySelector('[class*="detailScore__wrapper"], [class*="detailScore"]');
          const scoreRaw = scoreEl ? scoreEl.textContent.trim() : '';
          const statusEl = document.querySelector('[class*="detailStatus"], [class*="liveTime"]');
          const statusRaw = statusEl ? statusEl.textContent.trim() : '';

          // Times
          const teamEls = document.querySelectorAll('[class*="participant__participantName"]');
          const teamsSet = [...new Set(Array.from(teamEls).map(e => e.textContent.trim()).filter(Boolean))];

          // País e Liga dos Breadcrumbs / Headers
          let countryName = '';
          let leagueName = '';
          const countryEl = document.querySelector('[class*="tournamentHeader__country"], [class*="tournamentHeader__category"], [class*="breadcrumb"] span:first-child, [class*="breadcrumb"] a:first-child');
          const leagueEl = document.querySelector('[class*="tournamentHeader__league"], [class*="tournamentHeader__title"], [class*="tournamentHeader"] a:last-child');
          if (countryEl) countryName = countryEl.textContent.replace(/[:\s]+$/, '').trim();
          if (leagueEl) leagueName = leagueEl.textContent.trim();

          // Fallback para title caso não ache no header
          const docTitle = document.title || '';

          return JSON.stringify({
            title: docTitle,
            score_raw: scoreRaw,
            status_raw: statusRaw,
            home_team: teamsSet[0] || '?',
            away_team: teamsSet[1] || '?',
            country: countryName,
            league: leagueName,
            stats: stats,
          });
        }
        """

    def _to_match_state(self, dados: dict, red_data: dict, match_id: str) -> MatchState:
        """Converte dados brutos do DOM → MatchState V1.2."""
        # Parse placar
        home_score, away_score = self._parse_score(
            dados.get("score_raw", ""), dados.get("title", "")
        )

        # Parse minuto
        minute = self._parse_minute(
            dados.get("status_raw", ""), dados.get("score_raw", "")
        )

        # Parse stats
        stats = dados.get("stats", {})

        # Delega construção pro helper que popula tanto legacy quanto _raw.
        return self._build_match_state(
            dados=dados, stats=stats, red_data=red_data,
            minute=minute, home_score=home_score, away_score=away_score,
            match_id=match_id,
        )

    def _build_match_state(self, dados, stats, red_data, minute,
                              home_score, away_score, match_id=""):
        """Monta MatchState populando legacy + _raw (None = ausente)."""
        BC_LABELS    = ["Big chances", "Grandes oportunidades",
                         "Chances claras", "Grandes chances"]
        XGOT_LABELS  = ["xG on target (xGOT)", "xG na baliza (xGOT)",
                         "xG no alvo (xGOT)",
                         "xG das finalizações no alvo (xGOT)",
                         "xGOT"]
        XG_LABELS    = ["Expected goals (xG)", "Golos esperados (xG)",
                         "Gols esperados (xG)", "xG (esperado)"]
        SOT_LABELS   = ["Shots on target", "Remates à baliza",
                         "Finalizações ao gol", "Chutes ao gol",
                         "Finalizações no alvo"]
        # v3.1 — Rota B precisa do total de finalizações
        SHOTS_LABELS = ["Total de finalizações", "Total shots",
                         "Remates totais", "Finalizações totais", "Chutes"]
        # v3.2 — xA (Assistências esperadas) — 4ª métrica da Quádrupla
        XA_LABELS    = ["Assistências esperadas (xA)", "Expected assists (xA)",
                         "xA (esperado)", "Assistências esperadas"]
        # Posse e Escanteios
        CORNERS_LABELS = ["Escanteios", "Pontapés de canto", "Cantos",
                          "Corner kicks", "Corners", "Córners", "Tiros de esquina"]
        POSSESSION_LABELS = ["Posse de bola", "Posse de bola (%)", "Posse",
                             "Ball possession", "Ball Possession", "Possession",
                             "Posesión de balón", "Posesión"]
        ATTACKS_LABELS = ["Ataques", "Total attacks", "Attacks", "Ataques totais"]
        DANGEROUS_ATTACKS_LABELS = ["Ataques Perigosos", "Ataques perigosos",
                                    "Dangerous attacks", "Dangerous Attacks", "Ataques peligrosos"]
        SHOTS_OFF_TARGET_LABELS = ["Finalizações para fora", "Remates para fora", "Shots off target",
                                   "Chutes fora", "Remates fora"]
        BLOCKED_SHOTS_LABELS = ["Chutes travados", "Remates bloqueados", "Blocked shots", "Chutes bloqueados"]
        FOULS_LABELS = ["Faltas", "Fouls", "Faltas cometidas"]
        YELLOW_CARDS_LABELS = ["Cartões amarelos", "Cartões Amarelos", "Yellow cards", "Tarjetas amarillas"]
        SAVES_LABELS = ["Defesas do goleiro", "Defesas", "Goalkeeper saves", "Saves", "Paradas"]

        h_bc_raw   = self._get_stat_int_or_none(stats,   BC_LABELS,   "h")
        a_bc_raw   = self._get_stat_int_or_none(stats,   BC_LABELS,   "a")
        h_xgot_raw = self._get_stat_float_or_none(stats, XGOT_LABELS, "h")
        a_xgot_raw = self._get_stat_float_or_none(stats, XGOT_LABELS, "a")
        h_xg_raw   = self._get_stat_float_or_none(stats, XG_LABELS,   "h")
        a_xg_raw   = self._get_stat_float_or_none(stats, XG_LABELS,   "a")
        h_sot_raw  = self._get_stat_int_or_none(stats,   SOT_LABELS,  "h")
        a_sot_raw  = self._get_stat_int_or_none(stats,   SOT_LABELS,  "a")
        h_shots_raw = self._get_stat_int_or_none(stats, SHOTS_LABELS, "h")
        a_shots_raw = self._get_stat_int_or_none(stats, SHOTS_LABELS, "a")
        h_xa_raw    = self._get_stat_float_or_none(stats, XA_LABELS, "h")
        a_xa_raw    = self._get_stat_float_or_none(stats, XA_LABELS, "a")

        # Stats adicionais
        h_corners = self._get_stat_int(stats, CORNERS_LABELS, "h")
        a_corners = self._get_stat_int(stats, CORNERS_LABELS, "a")
        h_poss = self._get_stat_int(stats, POSSESSION_LABELS, "h")
        a_poss = self._get_stat_int(stats, POSSESSION_LABELS, "a")
        if h_poss == 0 and a_poss == 0:
            h_poss, a_poss = 50, 50
        elif h_poss > 0 and a_poss == 0:
            a_poss = max(0, 100 - h_poss)
        elif a_poss > 0 and h_poss == 0:
            h_poss = max(0, 100 - a_poss)

        h_att = self._get_stat_int(stats, ATTACKS_LABELS, "h")
        a_att = self._get_stat_int(stats, ATTACKS_LABELS, "a")
        h_da = self._get_stat_int(stats, DANGEROUS_ATTACKS_LABELS, "h")
        a_da = self._get_stat_int(stats, DANGEROUS_ATTACKS_LABELS, "a")
        h_sotf = self._get_stat_int(stats, SHOTS_OFF_TARGET_LABELS, "h")
        a_sotf = self._get_stat_int(stats, SHOTS_OFF_TARGET_LABELS, "a")
        h_blk = self._get_stat_int(stats, BLOCKED_SHOTS_LABELS, "h")
        a_blk = self._get_stat_int(stats, BLOCKED_SHOTS_LABELS, "a")
        h_fouls = self._get_stat_int(stats, FOULS_LABELS, "h")
        a_fouls = self._get_stat_int(stats, FOULS_LABELS, "a")
        h_yellow = self._get_stat_int(stats, YELLOW_CARDS_LABELS, "h")
        a_yellow = self._get_stat_int(stats, YELLOW_CARDS_LABELS, "a")
        h_saves = self._get_stat_int(stats, SAVES_LABELS, "h")
        a_saves = self._get_stat_int(stats, SAVES_LABELS, "a")

        return MatchState(
            match_id=match_id or dados.get("match_id", "?"),
            home=dados.get("home_team", "?"),
            away=dados.get("away_team", "?"),
            league=dados.get("league", ""),
            country=dados.get("country", ""),
            minute=minute,
            home_score=home_score,
            away_score=away_score,
            status_raw=(dados.get("status_raw") or "").strip(),
            # Legacy (numérico, 0.0 fallback)
            home_bc=h_bc_raw if h_bc_raw is not None else 0,
            away_bc=a_bc_raw if a_bc_raw is not None else 0,
            home_xgot=h_xgot_raw if h_xgot_raw is not None else 0.0,
            away_xgot=a_xgot_raw if a_xgot_raw is not None else 0.0,
            home_xg=h_xg_raw if h_xg_raw is not None else 0.0,
            away_xg=a_xg_raw if a_xg_raw is not None else 0.0,
            home_sot=h_sot_raw if h_sot_raw is not None else 0,
            away_sot=a_sot_raw if a_sot_raw is not None else 0,
            home_shots=h_shots_raw if h_shots_raw is not None else 0,
            away_shots=a_shots_raw if a_shots_raw is not None else 0,
            home_xa=h_xa_raw if h_xa_raw is not None else 0.0,
            away_xa=a_xa_raw if a_xa_raw is not None else 0.0,
            # Stats completas
            home_corners=h_corners,
            away_corners=a_corners,
            home_possession=h_poss,
            away_possession=a_poss,
            home_dangerous_attacks=h_da,
            away_dangerous_attacks=a_da,
            home_attacks=h_att,
            away_attacks=a_att,
            home_shots_off_target=h_sotf,
            away_shots_off_target=a_sotf,
            home_blocked_shots=h_blk,
            away_blocked_shots=a_blk,
            home_fouls=h_fouls,
            away_fouls=a_fouls,
            home_yellow_cards=h_yellow,
            away_yellow_cards=a_yellow,
            home_saves=h_saves,
            away_saves=a_saves,
            all_stats=stats,   # v3.2 — bag completo pra leitura contextual
            home_red_cards=red_data.get("home_red", 0),
            away_red_cards=red_data.get("away_red", 0),
            # Raw (None = ausente; consumido pela TRINCA/Turbo)
            home_bc_raw=h_bc_raw,     away_bc_raw=a_bc_raw,
            home_xgot_raw=h_xgot_raw, away_xgot_raw=a_xgot_raw,
            home_xg_raw=h_xg_raw,     away_xg_raw=a_xg_raw,
            home_sot_raw=h_sot_raw,   away_sot_raw=a_sot_raw,
            home_shots_raw=h_shots_raw, away_shots_raw=a_shots_raw,
        )

    # ─── Parsers ────────────────────────────────────────────────────

    def _parse_score(self, score_raw: str, title: str = "") -> tuple:
        # Título é fonte mais limpa (ex: "RIE 1-2 SK | ...")
        if title:
            m = re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b", title.split("|")[0])
            if m:
                h, a = int(m.group(1)), int(m.group(2))
                if h <= 20 and a <= 20:
                    return h, a
        if not score_raw:
            return 0, 0
        # score_raw pode ter dígitos extras (período, HT score)
        # Pegar apenas os primeiros 2 números separados por - ou :
        m = re.search(r"(\d{1,2})\s*[-:]\s*(\d{1,2})", score_raw)
        if not m:
            return 0, 0
        h, a = int(m.group(1)), int(m.group(2))
        # Guard: futebol raramente passa de 9 gols por time
        if a > 9:
            a = int(str(a)[0])
        if h > 9:
            h = int(str(h)[0])
        return h, a

    def _parse_minute(self, status_raw: str, score_raw: str = "") -> int:
        """
        Parser estrito de minuto. Olha APENAS status_raw — score_raw é ignorado
        de propósito (era a causa do bug "min 1" extraído do placar "1-0").

        Retorna:
          0   → minuto desconhecido / pre-jogo (motor V1.2 trata como NO_TRADE).
          90  → jogo terminado (TERMINADO/FT/FINISHED).
          45  → intervalo (INTERVALO/HT).
          N   → minuto explícito do status (1-130).

        NOTA: não retorna -1 nem causa skip do jogo — o motor V1.2 já filtra
        jogos com minute=0 (NO_TRADE) e não emite sinal/Telegram.
        """
        status = (status_raw or "").strip()
        if not status:
            return 0
        score = (score_raw or "").strip()
        up = status.upper()
        # Formato MM:SS — busca primeiro no status, depois no score como fallback
        # (Flashscore às vezes deixa só "2º tempo" no header e o "MM:SS" no score)
        # MM:SS é seguro contra o bug do placar (placar "1-0" não tem ":").
        for source in (status, score):
            m = re.search(r"(\d{1,3}):(\d{2})", source)
            if m:
                n = int(m.group(1))
                if 0 <= n <= 130:
                    return n
        # Estados especiais (sem minuto explícito)
        if "TERMINADO" in up or "FINISHED" in up or "ENCERRADO" in up:
            return 90
        if re.search(r"\bFT\b", up):
            return 90
        if "INTERVALO" in up or "HALF TIME" in up or re.search(r"\bHT\b", up):
            return 45
        # Número standalone APENAS no status (NUNCA no score — bug do "1-0")
        m = re.search(r"\b(\d{1,3})\b", status)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 130:
                return n
        return 0

    def _get_stat_float(self, stats: dict, labels: list, side: str) -> float:
        # Legacy: retorna 0.0 quando label não existe (preservado pra não
        # quebrar regra antiga que espera float sempre).
        stats_lower = {k.lower(): v for k, v in stats.items()}
        for label in labels:
            key = label.lower()
            if key in stats_lower:
                val = stats_lower[key].get(side, "")
                return self._to_float(val)
        return 0.0

    def _get_stat_int(self, stats: dict, labels: list, side: str) -> int:
        return int(self._get_stat_float(stats, labels, side))

    def _get_stat_float_or_none(self, stats: dict, labels: list,
                                  side: str):
        """Novo: distingue ausência do feed (None) de zero real (0.0).
        Usado pra popular os campos _raw da MatchState (consumidos pela
        TRINCA/Turbo). NÃO substitui o legacy — coexiste."""
        stats_lower = {k.lower(): v for k, v in stats.items()}
        for label in labels:
            key = label.lower()
            if key in stats_lower:
                raw = stats_lower[key].get(side, None)
                if raw is None:
                    return None
                # Strip whitespace primeiro — "  " conta como ausente
                if isinstance(raw, str) and raw.strip() == "":
                    return None
                return self._to_float(raw)
        return None   # label não encontrado em nenhum dos idiomas

    def _get_stat_int_or_none(self, stats: dict, labels: list,
                                side: str):
        v = self._get_stat_float_or_none(stats, labels, side)
        return int(v) if v is not None else None

    def _to_float(self, s: str) -> float:
        if not s:
            return 0.0
        s = re.sub(r"[^\d.,\-]", "", str(s).strip().replace(",", "."))
        if not s or s in (".", "-"):
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0
