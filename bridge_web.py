"""
BacanaLive Web Bridge (bridge_web.py) — Motor Crawler Unificado Standalone Local
================================================================================
Motor Único, Completo e Autocontido para Ingestão e Processamento em Tempo Real.

Tudo em 1 único arquivo (sem dependências de pastas externas ou scripts adicionais):
  1. Extração Nativa Playwright com Bloqueio Seletivo de Recursos Pesados:
       - Filtra e aborta rotas de imagens (png, jpg, webp, gif, svg), fontes (woff, woff2, ttf) e mídias (mp4, mp3).
       - Reduz o consumo de banda e CPU em até 80%, acelerando as leituras de página.
  2. Motor de Descoberta Automática (DOM Discovery + HTTP Fallback):
       - Identifica todas as partidas ao vivo no Flashscore com categorização hierárquica de ligas e países.
       - Contingência automática em background caso o DOM demore para renderizar.
  3. Catálogo Persistente de Partidas & Deduplicação Inteligente:
       - Armazena em disco (./data/crawler_catalog_cache.json) o histórico de partidas do ciclo operacional.
  4. Cacheamento Inteligente por TIER (Adaptive Scan TTL):
       - Tier 0   (Sinais / Posições Abertas): TTL 12s (Alta frequência)
       - Tier 0.5 (Ligas Premium A/B/C):      TTL 25s (Prioritário)
       - Tier 1/2 (Janela 20-83' com Stats):  TTL 35s-45s (Operacional)
       - Tier 3   (Ligas Alternativas/Início): TTL 80s (Rodízio)
       - HT       (Intervalo / Half-Time):    TTL 150s (Economia máxima)
       - No-Stats (Sem suporte a xG/chutes):  TTL 600s (Backoff)
       - FT       (Partidas Encerradas):      TTL Infinito (Descarte automático)
  5. Despacho Multithread Assíncrono com HTTP Connection Pooling:
       - Envia payloads instantaneamente para o servidor web sem travar o loop de leitura.
  6. Ciclo de Refresh Forçado Completo a cada 180s:
       - Garante a sincronização de 100% dos jogos da grade ao vivo periodicamente.
  7. Desconexão Instantânea e Limpeza da Grade:
       - Ao fechar com Ctrl+C, notifica o servidor web para zerar a grade ao vivo.

Requisitos de Instalação:
    pip install requests playwright curl_cffi
    playwright install chromium

Execução Standalone Local:
    python bridge_web.py
"""

import os
import sys
import time
import json
import re
import signal
import threading
import queue
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.parse

    class SimpleResponse:
        def __init__(self, text, status_code=200, json_data=None):
            self.text = text
            self.status_code = status_code
            self._json_data = json_data

        def json(self):
            if self._json_data is not None:
                return self._json_data
            return json.loads(self.text)

    class SimpleSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, headers=None, timeout=6):
            h = dict(self.headers)
            if headers:
                h.update(headers)
            req = urllib.request.Request(url, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as res:
                    body = res.read().decode('utf-8', errors='ignore')
                    return SimpleResponse(body, status_code=res.status)
            except urllib.error.HTTPError as e:
                return SimpleResponse("", status_code=e.code)
            except Exception:
                return SimpleResponse("", status_code=500)

        def post(self, url, headers=None, data=None, json=None, timeout=6):
            h = dict(self.headers)
            if headers:
                h.update(headers)
            payload_bytes = b""
            if json is not None:
                import json as _j
                payload_bytes = _j.dumps(json).encode('utf-8')
                h["Content-Type"] = "application/json"
            elif data is not None:
                if isinstance(data, str):
                    payload_bytes = data.encode('utf-8')
                else:
                    payload_bytes = data
            req = urllib.request.Request(url, data=payload_bytes, headers=h, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as res:
                    body = res.read().decode('utf-8', errors='ignore')
                    return SimpleResponse(body, status_code=res.status)
            except urllib.error.HTTPError as e:
                return SimpleResponse("", status_code=e.code)
            except Exception:
                return SimpleResponse("", status_code=500)

    class SimpleRequests:
        @staticmethod
        def get(url, headers=None, timeout=6):
            return SimpleSession().get(url, headers=headers, timeout=timeout)

        @staticmethod
        def post(url, headers=None, data=None, json=None, timeout=6):
            return SimpleSession().post(url, headers=headers, data=data, json=json, timeout=timeout)

        @staticmethod
        def Session():
            return SimpleSession()

    requests = SimpleRequests()

# =============================================================================
# 1. CONFIGURAÇÃO STANDALONE LOCAL & AMBIENTE
# =============================================================================
CURRENT_DIR = Path(__file__).resolve().parent
DATA_DIR = CURRENT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

LOCAL_SERVER_URL = os.environ.get("BACANALIVE_LOCAL_URL", "http://127.0.0.1:3000")
DASHBOARD_WEBHOOK = os.environ.get(
    "BACANALIVE_WEBHOOK_URL",
    f"{LOCAL_SERVER_URL}/api/crawler/webhook/flashscore-live"
)

WEBHOOK_SECRET = os.environ.get("BACANALIVE_WEBHOOK_SECRET", "sec_flashscore_982a17f")

HEADERS = {
    "Content-Type": "application/json",
    "x-webhook-token": WEBHOOK_SECRET,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

RUNNING = True

def notify_crawler_shutdown():
    """Notifica o servidor web local que o crawler foi encerrado, zerando a grade de partidas instantaneamente."""
    try:
        url = DASHBOARD_WEBHOOK.rsplit("/api/", 1)[0] + "/api/crawler/disconnect"
        print("🧹 Zerando grade de partidas ao vivo no servidor web...")
        requests.post(url, headers=HEADERS, json={"status": "stopped", "reason": "user_exit"}, timeout=1.5)
    except Exception:
        pass

def handle_exit(signum, frame):
    global RUNNING
    print("\n🛑 Sinal de encerramento recebido. Finalizando bridge_web.py...")
    RUNNING = False
    notify_crawler_shutdown()

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

# =============================================================================
# 2. MODELO DE DADOS MATCHSTATE UNIFICADO
# =============================================================================
@dataclass
class MatchState:
    """Representação estruturada de uma partida para o BacanaLive."""
    match_id: str = ""
    home: str = ""
    away: str = ""
    league: str = ""
    country: str = ""
    minute: int = 0
    home_score: int = 0
    away_score: int = 0
    home_bc: int = 0
    away_bc: int = 0
    home_xgot: float = 0.0
    away_xgot: float = 0.0
    home_red_cards: int = 0
    away_red_cards: int = 0
    home_sot: int = 0
    away_sot: int = 0
    home_shots: int = 0
    away_shots: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0
    home_corners: int = 0
    away_corners: int = 0
    home_possession: int = 50
    away_possession: int = 50
    home_dangerous_attacks: int = 0
    away_dangerous_attacks: int = 0
    home_attacks: int = 0
    away_attacks: int = 0
    home_shots_off_target: int = 0
    away_shots_off_target: int = 0
    home_blocked_shots: int = 0
    away_blocked_shots: int = 0
    home_fouls: int = 0
    away_fouls: int = 0
    home_yellow_cards: int = 0
    away_yellow_cards: int = 0
    home_saves: int = 0
    away_saves: int = 0
    home_xa: float = 0.0
    away_xa: float = 0.0
    all_stats: dict = field(default_factory=dict)
    home_bc_raw: Optional[int] = None
    away_bc_raw: Optional[int] = None
    home_xgot_raw: Optional[float] = None
    away_xgot_raw: Optional[float] = None
    home_xg_raw: Optional[float] = None
    away_xg_raw: Optional[float] = None
    home_sot_raw: Optional[int] = None
    away_sot_raw: Optional[int] = None
    home_shots_raw: Optional[int] = None
    away_shots_raw: Optional[int] = None
    status_raw: str = ""
    start_time: str = ""
    start_date: str = ""
    kickoff_ts: int = 0
    events: list = field(default_factory=list)

# =============================================================================
# 3. FILTRO DE LIGAS FEMININAS E E-SOCCER
# =============================================================================
IGNORED_PATTERNS = [
    r"\besoccer\b", r"\be-soccer\b", r"\besports\b", r"\be-sports\b",
    r"\bcyber\b", r"\bvirtual\b", r"\bgt league\b", r"\bgt battle\b",
    r"\bfifa\b", r"\bpes\b", r"\bvolta\b", r"\b2x2\b", r"\b3x3\b", r"\b4x4\b",
    r"\b5x5\b", r"\b6x6\b", r"\b7x7\b", r"\b8x8\b", r"\bgg league\b",
    r"\bh2h gg\b", r"\be-football\b", r"\befootball\b", r"\bpenalty\b",
    r"\bsrl\b", r"\bsimulated\b", r"\bshort football\b",
    r"\bfeminino\b", r"\bfeminina\b", r"\bwomen\b", r"\bwoman\b",
    r"\bladies\b", r"\bfrauen\b", r"\bdames\b", r"\bfemmes\b",
    r"\bdamen\b", r"\bkvinner\b", r"\bnaiset\b", r"\bmulheres\b",
    r"\b\(w\)\b", r"\b\[w\]\b", r"\b\(f\)\b", r"\b\[f\]\b", r"\b\(fem\)\b",
    r"\bwfc\b", r"\bffc\b", r"\bwomen's\b"
]

def is_ignored_match(league: str, country: str, home: str, away: str) -> bool:
    """Verifica e descarta partidas de Ligas Femininas ou E-Soccer."""
    text = f"{league} {country} {home} {away}".lower()
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

# =============================================================================
# 4. LIGAS PREMIUM (TIER 0.5)
# =============================================================================
PREMIUM_LEAGUES_KEYWORDS = [
    "premier league", "la liga", "laliga", "serie a", "bundesliga", "ligue 1",
    "champions league", "europa league", "conference league", "brasileirao", "brasileirão",
    "copa do brasil", "copa libertadores", "copa sudamericana", "eredivisie",
    "primeira liga", "liga portugal", "mls", "major league soccer", "saudi pro league",
    "championship", "fa cup", "copa del rey", "dfb pokal", "coppa italia"
]

def is_premium_league(league_name: str, country_name: str) -> bool:
    """Classifica se o jogo pertence a uma liga de alta liquidez/Tier 0.5."""
    full = f"{country_name} {league_name}".lower()
    for kw in PREMIUM_LEAGUES_KEYWORDS:
        if kw in full:
            return True
    return False

# =============================================================================
# 5. FILA ASSÍNCRONA MULTITHREAD COM HTTP CONNECTION POOLING
# =============================================================================
_payload_queue = queue.Queue(maxsize=3000)

def _create_http_session():
    session = requests.Session()
    if HAS_REQUESTS:
        try:
            retry_strategy = Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504],
            )
            adapter = HTTPAdapter(pool_connections=30, pool_maxsize=30, max_retries=retry_strategy)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
        except Exception:
            pass
    return session

def _async_dispatcher_worker():
    session = _create_http_session()
    while RUNNING:
        try:
            payload = _payload_queue.get(timeout=0.5)
            if payload is None:
                break
            try:
                res = session.post(
                    DASHBOARD_WEBHOOK,
                    headers=HEADERS,
                    data=payload,
                    timeout=2.5
                )
                if res.status_code not in (200, 201):
                    pass
            except Exception:
                pass
            finally:
                _payload_queue.task_done()
        except queue.Empty:
            continue
        except Exception:
            pass

_dispatcher_thread = threading.Thread(target=_async_dispatcher_worker, daemon=True)
_dispatcher_thread.start()

def _heartbeat_worker():
    session = _create_http_session()
    hb_url = f"{LOCAL_SERVER_URL}/api/crawler/heartbeat"
    while RUNNING:
        try:
            active_count = len(catalog_mgr.matches) if 'catalog_mgr' in globals() else 0
            session.post(
                hb_url,
                headers=HEADERS,
                json={
                    "crawlerId": "BacanaLive_Bridge",
                    "version": "2.5",
                    "activeMatches": active_count,
                    "status": "running"
                },
                timeout=2.0
            )
        except Exception:
            pass
        time.sleep(8.0)

_hb_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
_hb_thread.start()

def emit_match_update(match_data: dict, tier_tag: str = "T1"):
    """Serializa e enfileira a partida para envio assíncrono ao Dashboard."""
    try:
        body = json.dumps({
            "action": "batch_update",
            "matches": [match_data],
            "tier_tag": tier_tag,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        _payload_queue.put_nowait(body)
    except queue.Full:
        pass
    except Exception:
        pass

# =============================================================================
# 6. CONFIGURAÇÃO LOCAL DINÂMICA (Sincronizada com Config Local do Dashboard)
# =============================================================================
CONFIG_CACHE_PATH = DATA_DIR / "bacanalive_config.json"

def fetch_operational_crawler_config() -> dict:
    """Carrega parâmetros do motor crawler definidos no Dashboard Local Config."""
    defaults = {
        "maxWatchlistSize": 15,
        "discoveryIntervalSeconds": 180,
        "tier3ReservedSlots": 2,
        "minEntryMinute": 20,
        "maxEntryMinute": 83,
        "antiSpamCooldownMinutes": 5,
        "autoPruneMinutes": 30,
        "routeResourceBlock": True,
        "tierFilter": {
            "enableTier0Signals": True,
            "enableTier05Premium": True,
            "enableTier1": True,
            "enableTier2": True,
            "enableTier3Rotation": True,
        }
    }
    # 1. Tenta carregar dinamicamente da API local do Dashboard Standalone
    try:
        cfg_url = f"{LOCAL_SERVER_URL}/api/rules/config"
        r = requests.get(cfg_url, timeout=0.8)
        if r.status_code == 200:
            c_conf = r.json().get("config", {}).get("crawlerConfig")
            if c_conf:
                defaults.update(c_conf)
                return defaults
    except Exception:
        pass

    # 2. Fallback para arquivo JSON persistido em disco
    if CONFIG_CACHE_PATH.exists():
        try:
            with open(CONFIG_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                c_conf = data.get("operationalConfig", {}).get("crawlerConfig")
                if c_conf:
                    defaults.update(c_conf)
        except Exception:
            pass
    return defaults

def fetch_dismissed_matches() -> Set[str]:
    """Obtém o conjunto de IDs de partidas apagadas manualmente pelo usuário para não re-inserir."""
    try:
        url = f"{LOCAL_SERVER_URL}/api/matches/dismissed"
        r = requests.get(url, timeout=0.8)
        if r.status_code == 200:
            return set(r.json().get("dismissedMatchIds", []))
    except Exception:
        pass
    return set()

# =============================================================================
# 7. CATÁLOGO DE PARTIDAS & MOTOR DE CACHE POR TIER (ADAPTIVE SCAN TTL)
# =============================================================================
class MatchTier:
    TIER_0 = "TIER_0"       # Sinais / Posições Abertas (TTL: 12s)
    TIER_05 = "TIER_05"     # Ligas Premium A/B/C (TTL: 25s)
    TIER_1 = "TIER_1"       # Janela 20-83' com Stats & Perigo (TTL: 35s)
    TIER_2 = "TIER_2"       # Janela 20-83' Normal (TTL: 45s)
    TIER_3 = "TIER_3"       # Ligas Alternativas / Fora de Janela (TTL: 80s)
    HT = "HT"               # Intervalo / Half-Time (TTL: 150s)
    NO_STATS = "NO_STATS"   # Sem stats disponíveis (TTL: 600s)
    FINISHED = "FINISHED"   # Encerrado (TTL: Infinito)

# TTLs adaptativos por TIER em segundos para evitar varreduras redundantes
TIER_SCAN_TTL_SECONDS = {
    MatchTier.TIER_0: 10.0,       # Sinais / Posições Abertas (TTL: 10s)
    MatchTier.TIER_05: 20.0,     # Ligas Premium A/B/C (TTL: 20s)
    MatchTier.TIER_1: 25.0,       # Janela 20-83' com Stats & Perigo (TTL: 25s)
    MatchTier.TIER_2: 35.0,       # Janela 20-83' Normal (TTL: 35s)
    MatchTier.TIER_3: 50.0,       # Ligas Alternativas / Fora de Janela (TTL: 50s)
    MatchTier.HT: 90.0,           # Intervalo / Half-Time (TTL: 90s)
    MatchTier.NO_STATS: 180.0,    # Sem stats disponíveis (TTL: 180s)
    MatchTier.FINISHED: 999999.0
}

class MatchCatalogEntry:
    def __init__(self, match_id: str, url: str, league: str = "", country: str = "", home: str = "", away: str = ""):
        self.match_id: str = match_id
        self.url: str = url
        self.league: str = league
        self.country: str = country
        self.home: str = home
        self.away: str = away
        self.first_seen_at: float = time.time()
        self.last_seen_at: float = time.time()
        self.last_scanned_at: float = 0.0
        self.minute: int = 0
        self.status: str = "LIVE"
        self.home_score: int = 0
        self.away_score: int = 0
        self.ad: int = 0
        self.ao: int = 0
        self.stage_code: str = ""
        self.kickoff_time_str: str = ""
        self.start_date_iso: str = ""
        self.is_premium: bool = is_premium_league(league, country)
        self.tier: str = MatchTier.TIER_3
        self.has_open_position: bool = False
        self.last_signal_time: float = 0.0
        self.had_stats: bool = False
        self.no_stats_until: float = 0.0
        self.is_finished: bool = False
        self.last_scanned_minute: int = 0
        self.stagnant_minute_count: int = 0
        self.cached_payload: Optional[dict] = None

    def get_current_minute(self) -> int:
        """Calcula o minuto exato da partida em tempo real baseado nos timestamps oficiais FlashScore."""
        if self.is_finished:
            return self.minute or 90

        now_epoch = int(time.time())
        if self.stage_code == "12":  # 1º Tempo
            if self.ad > 0:
                return max(1, (now_epoch - self.ad) // 60)
            return max(1, self.minute)
        elif self.stage_code == "38":  # Intervalo / Half-Time
            return 45
        elif self.stage_code == "13":  # 2º Tempo
            if self.ao > 0:
                return max(46, 45 + (now_epoch - self.ao) // 60)
            elif self.ad > 0:
                return max(46, (now_epoch - self.ad) // 60)
            return max(46, self.minute)
        elif self.stage_code in ("14", "15"):  # Prorrogação
            if self.ao > 0:
                return max(91, 90 + (now_epoch - self.ao) // 60)
            return max(91, self.minute)

        if self.ad > 0:
            elapsed = (now_epoch - self.ad) // 60
            if elapsed <= 45:
                return max(1, elapsed)
            elif elapsed <= 60:
                return 45
            else:
                return max(46, elapsed - 15)

        return self.minute or 1

    def determine_tier(self, anti_spam_minutes: float = 5.0) -> str:
        """Calcula dinamicamente o Tier do jogo para definir sua cadência de cache."""
        now = time.time()
        if self.is_finished:
            self.tier = MatchTier.FINISHED
            return self.tier

        if now < self.no_stats_until:
            self.tier = MatchTier.NO_STATS
            return self.tier

        if self.status == "HT" or (self.minute == 45 and self.status != "2H"):
            self.tier = MatchTier.HT
            return self.tier

        if self.has_open_position or ((now - self.last_signal_time) < (anti_spam_minutes * 60)):
            self.tier = MatchTier.TIER_0
            return self.tier

        if self.is_premium:
            self.tier = MatchTier.TIER_05
            return self.tier

        m = self.minute or 0
        if 20 <= m <= 83:
            if self.had_stats:
                self.tier = MatchTier.TIER_1
            else:
                self.tier = MatchTier.TIER_2
            return self.tier

        self.tier = MatchTier.TIER_3
        return self.tier

    def should_scan(self, now: Optional[float] = None, anti_spam_minutes: float = 5.0) -> Tuple[bool, str, float]:
        """Avalia se a partida precisa de uma nova requisição de rede ou se pode usar o cache."""
        if now is None:
            now = time.time()

        current_tier = self.determine_tier(anti_spam_minutes)
        ttl = TIER_SCAN_TTL_SECONDS.get(current_tier, 35.0)

        elapsed = now - self.last_scanned_at
        if elapsed < ttl:
            remaining = ttl - elapsed
            return False, current_tier, remaining

        return True, current_tier, 0.0

class MatchCatalogManager:
    """Gerenciador central do Catálogo de Jogos com Cache Persistente em Disco."""
    def __init__(self, persistence_file: Path):
        self.persistence_file: Path = persistence_file
        self.matches: Dict[str, MatchCatalogEntry] = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        if not self.persistence_file.exists():
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("matches", []):
                    mid = item.get("match_id")
                    if mid:
                        e = MatchCatalogEntry(
                            match_id=mid,
                            url=item.get("url", ""),
                            league=item.get("league", ""),
                            country=item.get("country", ""),
                            home=item.get("home", ""),
                            away=item.get("away", "")
                        )
                        e.first_seen_at = item.get("first_seen_at", time.time())
                        e.last_seen_at = item.get("last_seen_at", time.time())
                        e.last_scanned_at = item.get("last_scanned_at", 0.0)
                        e.minute = item.get("minute", 0)
                        e.status = item.get("status", "LIVE")
                        e.home_score = item.get("home_score", 0)
                        e.away_score = item.get("away_score", 0)
                        e.is_finished = item.get("is_finished", False)
                        self.matches[mid] = e
        except Exception:
            pass

    def save(self):
        try:
            items = []
            with self.lock:
                for e in self.matches.values():
                    items.append({
                        "match_id": e.match_id,
                        "url": e.url,
                        "league": e.league,
                        "country": e.country,
                        "home": e.home,
                        "away": e.away,
                        "first_seen_at": e.first_seen_at,
                        "last_seen_at": e.last_seen_at,
                        "last_scanned_at": e.last_scanned_at,
                        "minute": e.minute,
                        "status": e.status,
                        "home_score": e.home_score,
                        "away_score": e.away_score,
                        "is_finished": e.is_finished,
                    })
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump({"updated_at": time.time(), "matches": items}, f, indent=2)
        except Exception:
            pass

    def upsert_discovered(
        self,
        match_id: str,
        url: str,
        league: str = "",
        country: str = "",
        home: str = "",
        away: str = "",
        home_score: int = 0,
        away_score: int = 0,
        minute: int = 0,
        status: str = "LIVE",
        ad: int = 0,
        ao: int = 0,
        stage_code: str = "",
        kickoff_time_str: str = "",
        start_date_iso: str = ""
    ):
        with self.lock:
            if match_id not in self.matches:
                entry = MatchCatalogEntry(
                    match_id=match_id,
                    url=url,
                    league=league,
                    country=country,
                    home=home,
                    away=away
                )
                entry.home_score = home_score
                entry.away_score = away_score
                entry.minute = minute
                entry.status = status or "LIVE"
                entry.ad = ad
                entry.ao = ao
                entry.stage_code = stage_code
                entry.kickoff_time_str = kickoff_time_str
                entry.start_date_iso = start_date_iso
                self.matches[match_id] = entry
            else:
                entry = self.matches[match_id]
                entry.last_seen_at = time.time()
                if url and not entry.url:
                    entry.url = url
                if league:
                    entry.league = league
                    entry.is_premium = is_premium_league(league, country or entry.country)
                if country:
                    entry.country = country
                if home and (not entry.home or entry.home == "?"):
                    entry.home = home
                if away and (not entry.away or entry.away == "?"):
                    entry.away = away
                if minute > 0:
                    entry.minute = minute
                if ad > 0:
                    entry.ad = ad
                if ao > 0:
                    entry.ao = ao
                if stage_code:
                    entry.stage_code = stage_code
                if kickoff_time_str:
                    entry.kickoff_time_str = kickoff_time_str
                if start_date_iso:
                    entry.start_date_iso = start_date_iso
                if status:
                    entry.status = status
                entry.home_score = home_score
                entry.away_score = away_score

    def mark_finished(self, match_id: str):
        with self.lock:
            if match_id in self.matches:
                self.matches[match_id].is_finished = True
                self.matches[match_id].tier = MatchTier.FINISHED

    def update_scan_result(self, match_id: str, minute: int, status: str, home_score: int, away_score: int, had_stats: bool, no_stats: bool = False) -> bool:
        """Atualiza a partida e verifica se o jogo terminou por status ou por tempo estagnado >= 90' em 3 varreduras consecutivas."""
        with self.lock:
            if match_id in self.matches:
                entry = self.matches[match_id]
                entry.last_scanned_at = time.time()
                entry.status = status
                entry.home_score = home_score
                entry.away_score = away_score
                entry.had_stats = had_stats
                if no_stats:
                    entry.no_stats_until = time.time() + 600.0

                is_status_finished = status.upper() in ("FT", "ENDED", "FINISHED", "ENCERRADO", "TERMINADO", "AET", "PEN", "FIM") or minute > 120
                if is_status_finished:
                    entry.is_finished = True
                    entry.tier = MatchTier.FINISHED
                    print(f"🛑 [FIM DE JOGO - STATUS OFICIAL] Partida {entry.home} x {entry.away} detectada como ENCERRADA ({status} / {minute}').")
                    return True

                # Dica/Regra operacional: se o jogo estiver com o tempo parado em 3 varreduras seguintes e acima de 90', esse jogo já terminou.
                if minute >= 90:
                    if entry.last_scanned_minute == minute:
                        entry.stagnant_minute_count += 1
                    else:
                        entry.last_scanned_minute = minute
                        entry.stagnant_minute_count = 1

                    if entry.stagnant_minute_count >= 3:
                        entry.is_finished = True
                        entry.tier = MatchTier.FINISHED
                        print(f"🛑 [FIM DE JOGO - TEMPO ESTAGNADO 3x] Partida {entry.home} x {entry.away} detectada como ENCERRADA (tempo parado em {minute}' por 3 varreduras).")
                        return True
                elif minute == 0 and not had_stats:
                    # Partida sem estatísticas e com minuto 0
                    if entry.last_scanned_minute == 0:
                        entry.stagnant_minute_count += 1
                    else:
                        entry.last_scanned_minute = 0
                        entry.stagnant_minute_count = 1
                    if entry.stagnant_minute_count >= 3:
                        entry.no_stats_until = time.time() + 600.0
                else:
                    entry.last_scanned_minute = minute
                    entry.stagnant_minute_count = 0

                entry.minute = minute
        return False

    def prune_stale(self, max_unseen_minutes: float = 30.0):
        now = time.time()
        cutoff = now - (max_unseen_minutes * 60)
        with self.lock:
            to_del = []
            for mid, e in self.matches.items():
                if e.is_finished:
                    to_del.append(mid)
                elif e.last_seen_at < cutoff and not e.has_open_position:
                    to_del.append(mid)
            for mid in to_del:
                del self.matches[mid]

    def select_watchlist_by_tiers(
        self,
        max_size: int = 15,
        tier3_reserved: int = 2,
        min_entry_minute: int = 20,
        max_entry_minute: int = 83,
        anti_spam_minutes: float = 5.0,
        tier_filter: Optional[dict] = None
    ) -> List[Tuple[MatchCatalogEntry, str]]:
        now = time.time()
        tier_filter = tier_filter or {}
        enable_t0 = tier_filter.get("enableTier0Signals", True)
        enable_t05 = tier_filter.get("enableTier05Premium", True)
        enable_t1 = tier_filter.get("enableTier1", True)
        enable_t2 = tier_filter.get("enableTier2", True)
        enable_t3 = tier_filter.get("enableTier3Rotation", True)

        bucket_t0: List[MatchCatalogEntry] = []
        bucket_t05: List[MatchCatalogEntry] = []
        bucket_t1: List[MatchCatalogEntry] = []
        bucket_t2: List[MatchCatalogEntry] = []
        bucket_t3: List[MatchCatalogEntry] = []

        with self.lock:
            for e in self.matches.values():
                if e.is_finished:
                    continue

                needs_scan, tier, rem_ttl = e.should_scan(now, anti_spam_minutes)
                if not needs_scan:
                    continue

                if tier == MatchTier.TIER_0 and enable_t0:
                    bucket_t0.append(e)
                elif tier == MatchTier.TIER_05 and enable_t05:
                    bucket_t05.append(e)
                elif tier == MatchTier.TIER_1 and enable_t1:
                    bucket_t1.append(e)
                elif tier == MatchTier.TIER_2 and enable_t2:
                    bucket_t2.append(e)
                elif tier == MatchTier.TIER_3 and enable_t3:
                    bucket_t3.append(e)

        bucket_t05.sort(key=lambda x: x.last_scanned_at)
        bucket_t1.sort(key=lambda x: x.last_scanned_at)
        bucket_t2.sort(key=lambda x: x.last_scanned_at)
        bucket_t3.sort(key=lambda x: x.last_scanned_at)

        selected: List[Tuple[MatchCatalogEntry, str]] = []

        for e in bucket_t0:
            selected.append((e, MatchTier.TIER_0))

        remaining_slots = max(0, max_size - len(selected))

        t3_quota = min(tier3_reserved, len(bucket_t3), remaining_slots)
        t3_selected = bucket_t3[:t3_quota]
        remaining_slots -= len(t3_selected)

        t05_quota = min(len(bucket_t05), remaining_slots)
        for e in bucket_t05[:t05_quota]:
            selected.append((e, MatchTier.TIER_05))
        remaining_slots -= t05_quota

        for e in bucket_t1:
            if remaining_slots <= 0:
                break
            selected.append((e, MatchTier.TIER_1))
            remaining_slots -= 1

        for e in bucket_t2:
            if remaining_slots <= 0:
                break
            selected.append((e, MatchTier.TIER_2))
            remaining_slots -= 1

        for e in t3_selected:
            selected.append((e, MatchTier.TIER_3))

        return selected

CATALOG_FILE = DATA_DIR / "crawler_catalog_cache.json"
catalog_mgr = MatchCatalogManager(CATALOG_FILE)

# =============================================================================
# 8. SCRIPTS JAVASCRIPT & MOTOR DE DESCOBERTA / EXTRAÇÃO NATIVA PLAYWRIGHT
# =============================================================================
def _extract_match_id(url: str) -> str:
    m = re.search(r"/jogo/([A-Za-z0-9]{5,12})", url)
    if m:
        return f"FS_{m.group(1)}"
    m = re.search(r"/match/([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}"
    m = re.search(r"mid=([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}"
    m = re.search(r"/jogo/[^/]+/[^/]+-([A-Za-z0-9]+)", url)
    if m:
        return f"FS_{m.group(1)}"
    return "FS_UNKNOWN"

def _get_raw_id(mid_or_url: str) -> str:
    if not mid_or_url:
        return ""
    clean = str(mid_or_url).strip()
    if clean.startswith("FS_") or clean.startswith("fs_"):
        return clean[3:]
    m = re.search(r"/jogo/([A-Za-z0-9]{5,12})", clean)
    if m:
        return m.group(1)
    m = re.search(r"/match/([A-Za-z0-9]+)", clean)
    if m:
        return m.group(1)
    return clean

def _normalize_stats_url(url: str) -> str:
    base = url.split("#")[0].rstrip("/")
    return base + "#/match-summary/match-statistics/0"

SCRIPT_RED_CARDS = r"""
() => {
  let homeRed = 0, awayRed = 0;
  // Localizar exclusivamente ícones/elementos com classes formais de cartão vermelho ou segundo amarelo
  const redCards = document.querySelectorAll('.card-ico--red, .card-ico--yellow-red, [class*="card-ico--red"], [class*="card-ico--yellow-red"]');
  redCards.forEach(card => {
    const parentRow = card.closest('.smv__incident, [class*="incidentRow"], [class*="smh__incident"]') || card.parentElement;
    if (!parentRow) return;
    const isHome = parentRow.closest('.smv__homeParticipant, .smv__incidentHomeScore, [class*="--home"], [class*="incidentSubRow--home"]') !== null ||
                   parentRow.matches('.smv__incidentHomeScore, [class*="--home"]');
    const isAway = parentRow.closest('.smv__awayParticipant, .smv__incidentAwayScore, [class*="--away"], [class*="incidentSubRow--away"]') !== null ||
                   parentRow.matches('.smv__incidentAwayScore, [class*="--away"]');
    if (isHome) homeRed++;
    else if (isAway) awayRed++;
  });
  return JSON.stringify({home_red: homeRed, away_red: awayRed});
}
"""

_JS_CLICK_AO_VIVO = r"""
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

_JS_EXTRACT_ALL_MATCH_URLS = r"""
() => {
  const matches = [];
  const seen = new Set();

  // Modern Flashscore DOM parser for Live matches
  const matchElements = document.querySelectorAll('[id^="g_1_"], .event__match');
  matchElements.forEach(el => {
    let rawId = (el.id || '').replace(/^g_1_/, '').trim();
    if (!rawId) {
      const idAttr = el.getAttribute('id') || '';
      if (idAttr.startsWith('g_1_')) rawId = idAttr.substring(4);
    }
    if (!rawId || rawId.length < 5 || seen.has(rawId)) return;
    seen.add(rawId);

    const homeEl = el.querySelector('.event__homeParticipant, .event__participant--home, [class*="homeParticipant"], [class*="participant--home"]');
    const awayEl = el.querySelector('.event__awayParticipant, .event__participant--away, [class*="awayParticipant"], [class*="participant--away"]');
    const homeScoreEl = el.querySelector('.event__score--home, [class*="score--home"]');
    const awayScoreEl = el.querySelector('.event__score--away, [class*="score--away"]');
    const stageEl = el.querySelector('.event__stage--block, .event__time, [class*="stage--block"], [class*="event__stage"]');

    const home = homeEl ? (homeEl.textContent || '').trim() : '';
    const away = awayEl ? (awayEl.textContent || '').trim() : '';
    const hScore = homeScoreEl ? parseInt((homeScoreEl.textContent || '0').trim(), 10) || 0 : 0;
    const aScore = awayScoreEl ? parseInt((awayScoreEl.textContent || '0').trim(), 10) || 0 : 0;
    const stage = stageEl ? (stageEl.textContent || '').trim() : '';

    // Filtrar partidas que já terminaram ou estão agendadas
    const isFinished = el.classList.contains('event__match--finished') ||
                       el.classList.contains('event__match--scheduled') ||
                       /encerrado|terminado|fim|finished|ft\b|ap\b|pen\b/i.test(stage) ||
                       /adiado|cancelado|postponed|cancelled/i.test(stage);
    if (isFinished) return;

    let minute = 0;
    const mDigits = stage.match(/\b(\d{1,3})\b/);
    if (mDigits) {
      minute = parseInt(mDigits[1], 10);
    } else if (stage.includes('1T') || stage.includes('1H')) {
      minute = 25;
    } else if (stage.includes('HT') || stage.toLowerCase().includes('intervalo')) {
      minute = 45;
    } else if (stage.includes('2T') || stage.includes('2H')) {
      minute = 70;
    }

    if (minute > 120) return;

    const isLive = el.classList.contains('event__match--live') || 
                   stage.includes("'") || 
                   minute > 0 || 
                   stage.includes('1T') || stage.includes('2T') || stage.includes('HT');

    if (!isLive) return;

    matches.push({
      mid: `FS_${rawId}`,
      url: `https://www.flashscore.com.br/jogo/${rawId}`,
      home: home,
      away: away,
      home_score: hScore,
      away_score: aScore,
      minute: minute,
      stage: stage || 'LIVE',
      is_live: isLive
    });
  });

  return matches;
}
"""

_JS_EXPAND_LEAGUES = r"""
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

_JS_EXTRACT_LEAGUE_META = r"""
() => {
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

  const parseLeagueHeader = (wrapper) => {
    let titleEl = wrapper.querySelector('[class*="headerLeague__title-text"]');
    if (!titleEl) {
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

    if (league) {
      league = league.replace(
        /\s*[A-ZÁÀÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝ]{3,}\s*:?\s*$/, ''
      ).trim();
    }

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

  const result = {};
  const stats = { total_links: 0 };
  const containers = document.querySelectorAll('[class*="sportName"]');

  for (const container of containers) {
    let currentLeague = null;
    for (const child of container.children) {
      if (hasClass(child, ['headerLeague__wrapper', 'headerLeague'])) {
        currentLeague = parseLeagueHeader(child);
        continue;
      }
      if (hasClass(child, ['event__match'])) {
        const rawId = (child.id || '').replace(/^g_1_/, '').trim();
        if (rawId && currentLeague) {
          result[`FS_${rawId}`] = Object.assign({header_found: true}, currentLeague);
        }
      }
    }
  }

  return {result: result, stats: stats};
}
"""

def http_fallback_discover_live() -> list:
    """Fallback ultra-rápido via feed HTTP oficial do Flashscore filtrando estritamente partidas AO VIVO."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo",
        "Referer": "https://www.flashscore.com.br/"
    }
    feed_urls = [
        "https://www.flashscore.com.br/x/feed/f_1_0_3_pt-br_1",
        "https://www.flashscore.com/x/feed/f_1_0_1_en-gb_1",
        "https://www.flashscore.com.br/x/feed/f_1_1_3_pt-br_1"
    ]
    
    live_matches = []
    seen = set()
    now_epoch = int(time.time())

    for u in feed_urls:
        try:
            r = requests.get(u, headers=headers, timeout=6)
            if r.status_code == 200 and "~ZA÷" in r.text:
                sections = r.text.split("~ZA÷")
                for sec in sections[1:]:
                    raw_header = sec.split("~AA÷")[0]
                    header_line = raw_header.split("¬")[0].strip()

                    # 1. Extração precisa de País e Liga separados
                    c_m = re.search(r'¬ZY÷([^¬]+)', raw_header)
                    if c_m:
                        c_name = c_m.group(1).strip()
                    elif ":" in header_line:
                        c_name = header_line.split(":", 1)[0].strip().title()
                    else:
                        c_name = "Internacional"

                    if ":" in header_line:
                        l_name = header_line.split(":", 1)[1].strip()
                    else:
                        l_name = header_line or "Geral"

                    # Se a liga tiver o nome do país como prefixo repetido, limpar
                    if l_name.lower().startswith(c_name.lower() + ":"):
                        l_name = l_name[len(c_name) + 1:].strip()

                    match_blocks = sec.split("~AA÷")
                    for mb in match_blocks[1:]:
                        mid_m = re.match(r'([A-Za-z0-9]+)', mb)
                        if not mid_m:
                            continue
                        raw_id = mid_m.group(1)
                        if raw_id in seen:
                            continue

                        status_code_m = re.search(r'¬AB÷(\d+)', mb)
                        status_code = status_code_m.group(1) if status_code_m else "0"

                        stage_m = re.search(r'¬AC÷([^¬]+)', mb)
                        stage_code = stage_m.group(1).strip() if stage_m else ""

                        # No Flashscore: AB=2 é EXCLUSIVAMENTE partida AO VIVO. AB=3 / AC=3,16,17,18,19,20,21 é ENCERRADO (finished).
                        if status_code != "2" or stage_code in ("3", "16", "17", "18", "19", "20", "21"):
                            continue

                        home_m = re.search(r'¬AE÷([^¬]+)', mb)
                        away_m = re.search(r'¬AF÷([^¬]+)', mb)
                        home = home_m.group(1).strip() if home_m else ""
                        away = away_m.group(1).strip() if away_m else ""

                        if not home or not away:
                            continue

                        seen.add(raw_id)
                        h_score_m = re.search(r'¬AG÷(\d+)', mb)
                        a_score_m = re.search(r'¬AH÷(\d+)', mb)
                        h_score = int(h_score_m.group(1)) if h_score_m else 0
                        a_score = int(a_score_m.group(1)) if a_score_m else 0

                        # Timestamps oficiais de início do 1T e 2T
                        ad_m = re.search(r'¬AD÷(\d+)', mb) or re.search(r'¬ADE÷(\d+)', mb)
                        ao_m = re.search(r'¬AO÷(\d+)', mb)
                        ad_val = int(ad_m.group(1)) if ad_m else 0
                        ao_val = int(ao_m.group(1)) if ao_m else 0

                        # Cálculo exato do tempo de jogo em tempo real
                        minute = 1
                        status_str = "LIVE"

                        if stage_code == "12":  # 1º Tempo
                            minute = max(1, (now_epoch - ad_val) // 60) if ad_val > 0 else 25
                            status_str = "1H"
                        elif stage_code == "38":  # Intervalo / HT
                            minute = 45
                            status_str = "HT"
                        elif stage_code == "13":  # 2º Tempo (permite 46 até 90, 95, 97+ sem travar)
                            if ao_val > 0:
                                minute = max(46, 45 + (now_epoch - ao_val) // 60)
                            elif ad_val > 0:
                                minute = max(46, (now_epoch - ad_val) // 60)
                            else:
                                minute = 60
                            status_str = "2H"
                        elif stage_code in ("14", "15"):  # Prorrogação
                            minute = max(91, 90 + (now_epoch - ao_val) // 60) if ao_val > 0 else 95
                            status_str = "ET"
                        else:
                            if ad_val > 0:
                                elapsed = (now_epoch - ad_val) // 60
                                if elapsed <= 45:
                                    minute = max(1, elapsed)
                                    status_str = "1H"
                                elif elapsed <= 60:
                                    minute = 45
                                    status_str = "HT"
                                else:
                                    minute = max(46, elapsed - 15)
                                    status_str = "2H"

                        # Formatação do horário de início da partida
                        start_time_str = ""
                        start_date_iso = ""
                        if ad_val > 0:
                            try:
                                dt = datetime.fromtimestamp(ad_val)
                                start_time_str = dt.strftime("%H:%M")
                                start_date_iso = datetime.fromtimestamp(ad_val, tz=timezone.utc).isoformat()
                            except Exception:
                                pass

                        live_matches.append({
                            "mid": f"FS_{raw_id}",
                            "url": f"https://www.flashscore.com.br/jogo/{raw_id}",
                            "league": l_name,
                            "country": c_name,
                            "home": home,
                            "away": away,
                            "home_score": h_score,
                            "away_score": a_score,
                            "minute": minute,
                            "status": status_str,
                            "ad": ad_val,
                            "ao": ao_val,
                            "stage_code": stage_code,
                            "startTime": start_time_str,
                            "startDate": start_date_iso
                        })

                if len(live_matches) > 0:
                    break
        except Exception:
            continue

    return live_matches

def discover_live_games(context, base_url: str, cookie_accept_fn=None, timeout_ms: int = 12000) -> list:
    """Abre o Flashscore, ativa filtro AO VIVO, expande ligas e coleta dados das partidas em andamento."""
    page = None
    try:
        page = context.new_page()
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

        try:
            page.wait_for_selector('.filters__tab, [class*="event__match"], [id^="g_1_"]', timeout=4000, state="attached")
            page.evaluate(_JS_CLICK_AO_VIVO)
            page.wait_for_timeout(500)
        except Exception:
            pass

        try:
            page.evaluate(_JS_EXPAND_LEAGUES)
            page.wait_for_timeout(400)
        except Exception:
            pass

        dom_matches = []
        try:
            dom_matches = page.evaluate(_JS_EXTRACT_ALL_MATCH_URLS) or []
        except Exception:
            pass

        league_meta = {}
        try:
            walker_result = page.evaluate(_JS_EXTRACT_LEAGUE_META) or {}
            league_meta = walker_result.get("result", {}) or {}
        except Exception:
            pass

        enriched_matches = []
        for m in dom_matches:
            mid = m.get("mid", "")
            meta = league_meta.get(mid, {})
            l_name = meta.get("league_name") or m.get("league", "FlashScore Live")
            c_name = meta.get("country") or m.get("country", "Internacional")
            
            # Só incluir se for ao vivo ou tiver times válidos
            if m.get("home") and m.get("away"):
                m["league"] = l_name
                m["country"] = c_name
                enriched_matches.append(m)

        if len(enriched_matches) == 0:
            print("ℹ️ [Discovery] 0 jogos no DOM. Acionando contingência HTTP feed...")
            fb = http_fallback_discover_live()
            if len(fb) > 0:
                return fb

        return enriched_matches

    except Exception as e:
        print(f"⚠️ [Discovery DOM Exception]: {e}. Usando contingência HTTP...")
        return http_fallback_discover_live()
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass

# =============================================================================
# 9. FLASHSCORE READER & FEED STATS EXTRACTION ENGINE
# =============================================================================
def _http_get_text(url: str, headers: dict = None, timeout: float = 4.0) -> str:
    """Requisição HTTP segura e universal (compatível com ou sem requests instalado)."""
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.text
        return ""
    except Exception:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

def fetch_flashscore_feed_stats(raw_id: str) -> dict:
    """Extrai estatísticas detalhadas ao vivo via feed HTTP oficial do Flashscore com suporte completo a xG, xGOT, Chances Claras, Finalizações e Cantos."""
    if not raw_id:
        return {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo",
        "Referer": f"https://www.flashscore.com.br/jogo/{raw_id}/"
    }
    stats = {}
    feed_urls = [
        f"https://www.flashscore.com.br/x/feed/df_st_0_{raw_id}",
        f"https://www.flashscore.com.br/x/feed/df_st_1_{raw_id}",
        f"https://www.flashscore.com/x/feed/df_st_0_{raw_id}",
        f"https://www.flashscore.com/x/feed/df_st_1_{raw_id}",
    ]
    for url in feed_urls:
        try:
            text = _http_get_text(url, headers=headers, timeout=3.5)
            if text and "¬SG÷" in text:
                main_part = text
                if "SE÷Jogo" in text:
                    parts = re.split(r'~SE÷|¬SE÷', text)
                    for p in parts:
                        if p.startswith("Jogo") or "SE÷Jogo" in p:
                            main_part = p
                            break

                # No feed do Flashscore: ¬SG÷ (Nome da Stat), ¬SH÷ (Valor Mandante), ¬SI÷ (Valor Visitante)
                pattern = re.compile(r'¬SG÷([^¬~]+).*?¬SH÷([^¬~]+).*?¬SI÷([^¬~]+)', re.DOTALL)
                for m in pattern.finditer(main_part):
                    name = m.group(1).strip()
                    home_val = m.group(2).strip()
                    away_val = m.group(3).strip()
                    if name and (home_val or away_val) and name not in stats:
                        stats[name] = {"h": home_val, "a": away_val}

                if len(stats) > 0:
                    break
        except Exception:
            continue
    return stats

def fetch_flashscore_feed_meta(raw_id: str) -> Optional[dict]:
    """Extrai metadados em tempo real (placar oficial, minuto exato, término e suporte a estatísticas) via dc_1."""
    if not raw_id:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo",
        "Referer": f"https://www.flashscore.com.br/jogo/{raw_id}/"
    }
    try:
        text = _http_get_text(f"https://www.flashscore.com.br/x/feed/dc_1_{raw_id}", headers=headers, timeout=3.5)
        if not text:
            return None
        lines = text.split("¬")
        d = {l.split("÷")[0]: l.split("÷")[1] for l in lines if "÷" in l}

        status_code = d.get("DA", "0")
        stage_code = d.get("DB", "")
        ad_val = int(d.get("DC", 0)) if d.get("DC") and d.get("DC").isdigit() else 0
        ao_val = int(d.get("DD", 0)) if d.get("DD") and d.get("DD").isdigit() else 0
        h_score = int(d.get("DE", 0)) if d.get("DE") is not None and d.get("DE").isdigit() else 0
        a_score = int(d.get("DF", 0)) if d.get("DF") is not None and d.get("DF").isdigit() else 0
        dx_features = d.get("DX", "")
        has_stats_tab = "ST" in dx_features

        is_finished = (status_code == "3" or stage_code in ("3", "16", "17", "18", "19", "20", "21"))
        is_live = (status_code == "2" and not is_finished)

        now_epoch = int(time.time())
        minute = 1
        status_str = "LIVE"

        if is_finished:
            minute = 90
            status_str = "FT"
        elif stage_code == "12":
            minute = max(1, (now_epoch - ad_val) // 60) if ad_val > 0 else 25
            status_str = "1H"
        elif stage_code == "38":
            minute = 45
            status_str = "HT"
        elif stage_code == "13":
            if ao_val > 0:
                minute = max(46, 45 + (now_epoch - ao_val) // 60)
            elif ad_val > 0:
                minute = max(46, (now_epoch - ad_val) // 60)
            else:
                minute = 60
            status_str = "2H"
        elif stage_code in ("14", "15"):
            minute = max(91, 90 + (now_epoch - ao_val) // 60) if ao_val > 0 else 95
            status_str = "ET"
        else:
            if ad_val > 0:
                elapsed = (now_epoch - ad_val) // 60
                if elapsed <= 45:
                    minute = max(1, elapsed)
                    status_str = "1H"
                elif elapsed <= 60:
                    minute = 45
                    status_str = "HT"
                else:
                    minute = max(46, elapsed - 15)
                    status_str = "2H"

        return {
            "is_live": is_live,
            "is_finished": is_finished,
            "status_code": status_code,
            "stage_code": stage_code,
            "home_score": h_score,
            "away_score": a_score,
            "minute": minute,
            "status_str": status_str,
            "has_stats_tab": has_stats_tab,
            "ad": ad_val,
            "ao": ao_val
        }
    except Exception:
        return None

def fetch_flashscore_feed_incidents(raw_id: str) -> dict:
    """Extrai cartões vermelhos, placar atualizado, minuto máximo e lista cronológica de eventos via feed HTTP."""
    if not raw_id:
        return {"home_red": 0, "away_red": 0, "home_score": None, "away_score": None, "stage": "", "latest_minute": 0, "events": []}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-fsign": "SW9D1eZo",
        "Referer": f"https://www.flashscore.com.br/jogo/{raw_id}/"
    }
    red_data = {
        "home_red": 0,
        "away_red": 0,
        "home_score": None,
        "away_score": None,
        "stage": "",
        "latest_minute": 0,
        "home_goals_count": 0,
        "away_goals_count": 0,
        "had_goals": False,
        "events": []
    }
    try:
        text = _http_get_text(f"https://www.flashscore.com.br/x/feed/df_sui_1_{raw_id}", headers=headers, timeout=3.0)
        if text:
            raw_events = []
            ev_idx = 0
            for item in text.split("~"):
                low = item.lower()
                
                # Minuto do evento (IB) e minuto extra (IT / IKX)
                ev_minute = 0
                ib_m = re.search(r'¬IB÷(\d+)', item)
                if ib_m:
                    ev_minute = int(ib_m.group(1))
                    if ev_minute > red_data["latest_minute"]:
                        red_data["latest_minute"] = ev_minute

                extra_min = None
                it_m = re.search(r'¬IT÷(\d+)', item)
                if it_m:
                    extra_min = int(it_m.group(1))

                # Lado da equipe (IA: 1 = Home, 2 = Away)
                ev_team = "home"
                ia_m = re.search(r'¬?IA÷([12])', item)
                if ia_m and ia_m.group(1) == "2":
                    ev_team = "away"

                # Nome do Jogador Principal (IF / IFB / PN / IN / IR)
                player_name = ""
                for p_pat in [r'¬IF÷([^¬~]+)', r'¬IFB÷([^¬~]+)', r'¬PN÷([^¬~]+)', r'¬IN÷([^¬~]+)', r'¬IR÷([^¬~]+)']:
                    pm = re.search(p_pat, item)
                    if pm:
                        player_name = pm.group(1).strip()
                        break

                # Assistência ou Jogador Substituto (IG / IGB / AS / I4)
                assist_name = ""
                for a_pat in [r'¬IG÷([^¬~]+)', r'¬IGB÷([^¬~]+)', r'¬AS÷([^¬~]+)', r'¬I4÷([^¬~]+)']:
                    am = re.search(a_pat, item)
                    if am:
                        assist_name = am.group(1).strip()
                        break

                # Detalhe do evento (IH / IK / ID)
                detail_text = ""
                ih_m = re.search(r'¬IH÷([^¬~]+)', item)
                if ih_m:
                    detail_text = ih_m.group(1).strip()

                # Placar no momento do evento (INX x IOX)
                score_moment = ""
                inx_m = re.search(r'¬INX÷(\d+)', item)
                iox_m = re.search(r'¬IOX÷(\d+)', item)
                if inx_m and iox_m:
                    score_moment = f"{inx_m.group(1)} - {iox_m.group(1)}"

                # Cartões vermelhos estritos: inspecionar exclusivamente o campo ¬IK÷ (Incident Kind)
                ik_m = re.search(r'¬?IK÷([^¬~]+)', item, re.IGNORECASE)
                if ik_m:
                    ik_val = ik_m.group(1).lower().strip()
                    is_yellow_only = "amarelo" in ik_val and not ("2º" in ik_val or "segundo" in ik_val or "vermelho" in ik_val)
                    is_red = ("cartão vermelho" in ik_val or "cartao vermelho" in ik_val or "red card" in ik_val or "2º cartão amarelo/vermelho" in ik_val or "2º amarelo" in ik_val or "segundo amarelo" in ik_val or "tarjeta roja" in ik_val) and not is_yellow_only
                    is_yellow = ("amarelo" in ik_val or "yellow card" in ik_val or "tarjeta amarilla" in ik_val) and not is_red
                    is_sub = ("substitui" in ik_val or "substitution" in ik_val or "troca" in ik_val)
                    is_var = ("var" in ik_val or "vídeo árbitro" in ik_val or "video referee" in ik_val)

                    if is_red:
                        if ev_team == "home":
                            red_data["home_red"] += 1
                        else:
                            red_data["away_red"] += 1

                    # Determinar tipo para o Feed de Eventos
                    ev_type = None
                    if is_red:
                        ev_type = "red_card"
                    elif is_yellow:
                        ev_type = "yellow_card"
                    elif is_sub:
                        ev_type = "sub"
                    elif is_var:
                        ev_type = "var"

                    if ev_type and ev_minute > 0:
                        ev_idx += 1
                        raw_events.append({
                            "id": f"ev_{raw_id}_{ev_idx}_{ev_minute}",
                            "minute": ev_minute,
                            "extraMinute": extra_min,
                            "type": ev_type,
                            "team": ev_team,
                            "player": player_name or None,
                            "assistPlayer": assist_name or None,
                            "detail": detail_text or None,
                            "score": score_moment or None
                        })

                # Estágio da partida (1T, 2T, Intervalo, etc.)
                if "ac÷" in low:
                    st_m = re.search(r'¬?AC÷([^¬~]+)', item)
                    if st_m:
                        st_name = st_m.group(1).strip()
                        if st_name:
                            red_data["stage"] = st_name

                # Detecção de Gols nos eventos
                if "¬ik÷gol" in low or "¬ik÷golo" in low or "¬ik÷goal" in low or "¬ik÷pen" in low:
                    red_data["had_goals"] = True
                    if inx_m and iox_m:
                        red_data["home_score"] = int(inx_m.group(1))
                        red_data["away_score"] = int(iox_m.group(1))
                    else:
                        if ev_team == "home":
                            red_data["home_goals_count"] += 1
                        else:
                            red_data["away_goals_count"] += 1

                    if ev_minute > 0:
                        ev_idx += 1
                        is_penalty = "penal" in low or "pênalti" in low
                        raw_events.append({
                            "id": f"ev_{raw_id}_{ev_idx}_{ev_minute}",
                            "minute": ev_minute,
                            "extraMinute": extra_min,
                            "type": "penalty_scored" if is_penalty else "goal",
                            "team": ev_team,
                            "player": player_name or None,
                            "assistPlayer": assist_name or None,
                            "detail": detail_text or ("Pênalti" if is_penalty else None),
                            "score": score_moment or None
                        })

            if red_data["home_score"] is None and red_data["had_goals"]:
                red_data["home_score"] = red_data["home_goals_count"]
                red_data["away_score"] = red_data["away_goals_count"]

            # Ordenar eventos cronologicamente do mais recente para o mais antigo (ou vice-versa)
            raw_events.sort(key=lambda x: (x["minute"], x.get("extraMinute") or 0))
            red_data["events"] = raw_events
    except Exception:
        pass
    return red_data

class FlashscoreReader:
    """Lê estatísticas detalhadas de uma partida no Flashscore via Feed HTTP + Playwright Híbrido."""
    def __init__(self, headless: bool = True, locale: str = "pt-BR", browser_data_dir: str = None):
        self.headless = headless
        self.locale = locale
        self._browser_dir = browser_data_dir or str(DATA_DIR / ".browser_data")
        self._pw = None
        self._context = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self._browser_dir,
            headless=self.headless,
            locale=self.locale,
            viewport={"width": 1366, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )
        return self

    def __exit__(self, *args):
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

    def read_match(self, url: str, match_id: str = None, timeout_ms: int = 15000, fallback_catalog_entry=None) -> Optional[MatchState]:
        if match_id is None:
            match_id = self._extract_match_id(url)
        raw_id = _get_raw_id(match_id or url)

        c_entry = fallback_catalog_entry
        if not c_entry and match_id in catalog_mgr.matches:
            c_entry = catalog_mgr.matches[match_id]

        h_team = c_entry.home if c_entry else "?"
        a_team = c_entry.away if c_entry else "?"
        l_name = c_entry.league if c_entry else ""
        c_name = c_entry.country if c_entry else ""
        start_time_str = c_entry.kickoff_time_str if c_entry else ""
        start_date_iso = c_entry.start_date_iso if c_entry else ""

        # 1. Consulta metadados oficiais instantâneos (dc_1)
        meta = fetch_flashscore_feed_meta(raw_id) if raw_id else None

        if meta and meta.get("is_finished"):
            # Jogo já encerrou oficialmente
            return MatchState(
                match_id=match_id or raw_id or "?",
                home=h_team,
                away=a_team,
                league=l_name,
                country=c_name,
                minute=meta.get("minute", 90),
                home_score=meta.get("home_score", 0),
                away_score=meta.get("away_score", 0),
                status_raw="FT",
                home_bc=0, away_bc=0, home_xgot=0.0, away_xgot=0.0, home_xg=0.0, away_xg=0.0,
                home_sot=0, away_sot=0, home_shots=0, away_shots=0, home_xa=0.0, away_xa=0.0,
                home_corners=0, away_corners=0, home_possession=50, away_possession=50,
                home_dangerous_attacks=0, away_dangerous_attacks=0, home_attacks=0, away_attacks=0,
                home_shots_off_target=0, away_shots_off_target=0, home_blocked_shots=0, away_blocked_shots=0,
                home_fouls=0, away_fouls=0, home_yellow_cards=0, away_yellow_cards=0,
                home_red_cards=0, away_red_cards=0, home_saves=0, away_saves=0
            )

        # 2. Tenta extração de estatísticas via Feed HTTP oficial Flashscore
        if raw_id:
            feed_stats = fetch_flashscore_feed_stats(raw_id)
            if feed_stats:
                feed_red = fetch_flashscore_feed_incidents(raw_id)
                h_score = meta["home_score"] if meta else (c_entry.home_score if c_entry else 0)
                a_score = meta["away_score"] if meta else (c_entry.away_score if c_entry else 0)
                if feed_red.get("home_score") is not None:
                    h_score = feed_red["home_score"]
                if feed_red.get("away_score") is not None:
                    a_score = feed_red["away_score"]

                min_val = meta["minute"] if meta else (c_entry.get_current_minute() if c_entry else 0)
                if feed_red.get("latest_minute", 0) > min_val:
                    min_val = feed_red["latest_minute"]

                st_val = meta["status_str"] if meta else (feed_red.get("stage") or (c_entry.status if c_entry else "LIVE"))

                dados = {
                    "title": f"{h_team} {h_score}-{a_score} {a_team}",
                    "score_raw": f"{h_score}-{a_score}",
                    "home_score": h_score,
                    "away_score": a_score,
                    "minute": min_val,
                    "status_raw": f"{min_val}'" if min_val > 0 else st_val,
                    "home_team": h_team,
                    "away_team": a_team,
                    "country": c_name,
                    "league": l_name,
                    "start_time": start_time_str,
                    "start_date": start_date_iso,
                    "stats": feed_stats
                }
                return self._to_match_state(dados, feed_red, match_id)

            # Se meta confirmou que o jogo NÃO tem aba de estatísticas ('ST' não está em DX), não perde tempo no Playwright
            if meta and not meta.get("has_stats_tab", False):
                h_score = meta["home_score"]
                a_score = meta["away_score"]
                min_val = meta["minute"]
                st_val = meta["status_str"]
                dados = {
                    "title": f"{h_team} {h_score}-{a_score} {a_team}",
                    "score_raw": f"{h_score}-{a_score}",
                    "home_score": h_score,
                    "away_score": a_score,
                    "minute": min_val,
                    "status_raw": f"{min_val}'" if min_val > 0 else st_val,
                    "home_team": h_team,
                    "away_team": a_team,
                    "country": c_name,
                    "league": l_name,
                    "start_time": start_time_str,
                    "start_date": start_date_iso,
                    "stats": {}
                }
                return self._to_match_state(dados, {"home_red": 0, "away_red": 0}, match_id)

        # 3. Fallback via Playwright DOM se necessário
        if not self._context:
            return None

        per_step_ms = max(3000, min(int(timeout_ms), 8000))
        wait_selector_ms = max(2000, min(int(timeout_ms), 5000))

        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(per_step_ms)

            stats_url = self._ensure_stats_url(url)
            page.goto(stats_url, wait_until="domcontentloaded", timeout=per_step_ms)
            self._accept_cookies(page)
            
            try:
                page.wait_for_selector('[class*="wcl-category"], [class*="statRow"]', timeout=wait_selector_ms)
            except Exception:
                pass

            page.wait_for_timeout(600)
            raw = page.evaluate(self._get_extraction_script())
            dados = json.loads(raw)
            try:
                red_raw = page.evaluate(SCRIPT_RED_CARDS)
                red_data = json.loads(red_raw)
            except Exception:
                red_data = {"home_red": 0, "away_red": 0}

            # Preencher com metadados/catalog caso DOM retorne vazio
            if meta:
                if not dados.get("home_score") and meta.get("home_score") is not None:
                    dados["home_score"] = meta["home_score"]
                    dados["away_score"] = meta["away_score"]
                if not dados.get("minute") or int(dados.get("minute", 0)) == 0:
                    dados["minute"] = meta["minute"]
                    dados["status_raw"] = meta["status_str"]

            if not dados.get("stats") and raw_id:
                feed_stats = fetch_flashscore_feed_stats(raw_id)
                if feed_stats:
                    dados["stats"] = feed_stats

            return self._to_match_state(dados, red_data, match_id)
        except Exception as e:
            if meta or c_entry:
                h_s = meta["home_score"] if meta else (c_entry.home_score if c_entry else 0)
                a_s = meta["away_score"] if meta else (c_entry.away_score if c_entry else 0)
                m_v = meta["minute"] if meta else (c_entry.get_current_minute() if c_entry else 0)
                s_t = meta["status_str"] if meta else (c_entry.status if c_entry else "LIVE")
                dados = {
                    "title": f"{h_team} {h_s}-{a_s} {a_team}",
                    "score_raw": f"{h_s}-{a_s}",
                    "home_score": h_s,
                    "away_score": a_s,
                    "minute": m_v,
                    "status_raw": f"{m_v}'" if m_v > 0 else s_t,
                    "home_team": h_team,
                    "away_team": a_team,
                    "country": c_name,
                    "league": l_name,
                    "start_time": start_time_str,
                    "start_date": start_date_iso,
                    "stats": {}
                }
                return self._to_match_state(dados, {"home_red": 0, "away_red": 0}, match_id)
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def _ensure_stats_url(self, url: str) -> str:
        clean = url.split("#")[0]
        if "/resumo/estatisticas/total/" in clean:
            return clean
        if "?" in clean:
            path, _, query = clean.partition("?")
            query = "?" + query
        else:
            path, query = clean, ""
        path = path.rstrip("/") + "/resumo/estatisticas/total/"
        return path + query

    def _extract_match_id(self, url: str) -> str:
        return _extract_match_id(url)

    def _accept_cookies(self, page):
        for s in ['button:has-text("ACEITAR")', 'button:has-text("Accept")', '#onetrust-accept-btn-handler', 'button:has-text("Aceitar tudo")']:
            try:
                btn = page.locator(s).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    def _get_extraction_script(self) -> str:
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

          const scoreEl = document.querySelector('[class*="detailScore__wrapper"], [class*="detailScore"], .detailScore__matchInfo');
          const scoreRaw = scoreEl ? scoreEl.textContent.trim() : '';
          const statusEl = document.querySelector('[class*="detailStatus"], [class*="liveTime"], [class*="eventTime"], [class*="fixedHeaderDuel__detailStatus"]');
          const statusRaw = statusEl ? statusEl.textContent.trim() : '';

          let homeTeam = '', awayTeam = '';
          const hParticipant = document.querySelector('[class*="duelParticipant__home"] [class*="participantName"], [class*="participant__participantName--home"], [class*="homeTeam"] [class*="name"]');
          const aParticipant = document.querySelector('[class*="duelParticipant__away"] [class*="participantName"], [class*="participant__participantName--away"], [class*="awayTeam"] [class*="name"]');
          if (hParticipant && aParticipant) {
            homeTeam = hParticipant.textContent.trim();
            awayTeam = aParticipant.textContent.trim();
          } else {
            const teamEls = document.querySelectorAll('[class*="participant__participantName"], [class*="duelParticipant"] [class*="participantName"]');
            const teamsSet = [...new Set(Array.from(teamEls).map(e => e.textContent.trim()).filter(Boolean))];
            homeTeam = teamsSet[0] || '';
            awayTeam = teamsSet[1] || '';
          }

          if (!homeTeam || !awayTeam) {
            const titleClean = (document.title || '').split('|')[0].split('-')[0].trim();
            const titleMatch = titleClean.match(/^(.+?)\s+[-xX–vsVS.]+\s+(.+?)$/);
            if (titleMatch) {
              if (!homeTeam) homeTeam = titleMatch[1].trim();
              if (!awayTeam) awayTeam = titleMatch[2].trim();
            }
          }

          let countryName = '';
          let leagueName = '';
          const countryEl = document.querySelector('[class*="tournamentHeader__country"], [class*="tournamentHeader__category"], [class*="breadcrumb"] span:first-child, [class*="breadcrumb"] a:first-child');
          const leagueEl = document.querySelector('[class*="tournamentHeader__league"], [class*="tournamentHeader__title"], [class*="tournamentHeader"] a:last-child');
          if (countryEl) countryName = countryEl.textContent.replace(/[:\s]+$/, '').trim();
          if (leagueEl) leagueName = leagueEl.textContent.trim();

          return JSON.stringify({
            title: document.title || '',
            score_raw: scoreRaw,
            status_raw: statusRaw,
            home_team: homeTeam || '?',
            away_team: awayTeam || '?',
            country: countryName,
            league: leagueName,
            stats: stats,
          });
        }
        """

    def _to_match_state(self, dados: dict, red_data: dict, match_id: str) -> MatchState:
        if dados.get("home_score") is not None and dados.get("away_score") is not None:
            try:
                home_score = int(dados["home_score"])
                away_score = int(dados["away_score"])
            except Exception:
                home_score, away_score = self._parse_score(dados.get("score_raw", ""), dados.get("title", ""))
        else:
            home_score, away_score = self._parse_score(dados.get("score_raw", ""), dados.get("title", ""))

        if dados.get("minute") is not None and int(dados.get("minute", 0)) > 0:
            minute = int(dados["minute"])
        else:
            minute = self._parse_minute(dados.get("status_raw", ""), dados.get("score_raw", ""))

        if minute == 0 and red_data and red_data.get("latest_minute", 0) > 0:
            minute = int(red_data["latest_minute"])

        stats = dados.get("stats", {})

        BC_LABELS = [
            "Chances claras", "Big chances", "Grandes oportunidades", "Grandes chances",
            "Chances Claras", "Grandes Oportunidades", "Big Chances"
        ]
        XGOT_LABELS = [
            "xG das finalizações no alvo (xGOT)", "xG on target (xGOT)", "xG na baliza (xGOT)",
            "xG no alvo (xGOT)", "xGOT", "Golos esperados no alvo (xGOT)", "Gols esperados no alvo (xGOT)"
        ]
        XG_LABELS = [
            "Gols esperados (xG)", "Golos esperados (xG)", "Expected goals (xG)",
            "xG (esperado)", "xG", "Expected goals", "Gols esperados"
        ]
        SOT_LABELS = [
            "Finalizações no alvo", "Finalizações ao gol", "Remates à baliza",
            "Shots on target", "Chutes ao gol", "Remates no alvo", "Chutes no gol"
        ]
        SHOTS_LABELS = [
            "Total de finalizações", "Total shots", "Remates totais",
            "Finalizações totais", "Chutes", "Finalizações", "Total Shots"
        ]
        XA_LABELS = [
            "Assistências esperadas (xA)", "Expected assists (xA)", "xA (esperado)", "xA"
        ]
        CORNERS_LABELS = [
            "Escanteios", "Pontapés de canto", "Cantos", "Corner kicks", "Corners", "Córners"
        ]
        POSSESSION_LABELS = [
            "Posse de bola", "Posse de bola (%)", "Posse", "Ball possession", "Possession"
        ]
        ATTACKS_LABELS = [
            "Ataques", "Total attacks", "Attacks"
        ]
        DANGEROUS_ATTACKS_LABELS = [
            "Ataques Perigosos", "Ataques perigosos", "Dangerous attacks"
        ]
        SHOTS_OFF_TARGET_LABELS = [
            "Finalizações para fora", "Remates para fora", "Shots off target", "Chutes fora"
        ]
        BLOCKED_SHOTS_LABELS = [
            "Finalizações bloqueadas", "Chutes travados", "Remates bloqueados", "Blocked shots"
        ]
        FOULS_LABELS = [
            "Faltas", "Fouls"
        ]
        YELLOW_CARDS_LABELS = [
            "Cartões amarelos", "Cartões Amarelos", "Yellow cards"
        ]
        RED_CARDS_LABELS = [
            "Cartões vermelhos", "Cartões Vermelhos", "Red cards", "Tarjetas rojas", "Cartão vermelho"
        ]
        SAVES_LABELS = [
            "Defesas do goleiro", "Defesas", "Goalkeeper saves", "Saves"
        ]

        h_bc = self._get_stat_int_or_none(stats, BC_LABELS, "h")
        a_bc = self._get_stat_int_or_none(stats, BC_LABELS, "a")
        h_xgot = self._get_stat_float_or_none(stats, XGOT_LABELS, "h")
        a_xgot = self._get_stat_float_or_none(stats, XGOT_LABELS, "a")
        h_xg = self._get_stat_float_or_none(stats, XG_LABELS, "h")
        a_xg = self._get_stat_float_or_none(stats, XG_LABELS, "a")
        h_sot = self._get_stat_int_or_none(stats, SOT_LABELS, "h")
        a_sot = self._get_stat_int_or_none(stats, SOT_LABELS, "a")
        h_shots = self._get_stat_int_or_none(stats, SHOTS_LABELS, "h")
        a_shots = self._get_stat_int_or_none(stats, SHOTS_LABELS, "a")
        h_xa = self._get_stat_float_or_none(stats, XA_LABELS, "h")
        a_xa = self._get_stat_float_or_none(stats, XA_LABELS, "a")

        h_poss = self._get_stat_int(stats, POSSESSION_LABELS, "h")
        a_poss = self._get_stat_int(stats, POSSESSION_LABELS, "a")
        if h_poss == 0 and a_poss == 0:
            h_poss, a_poss = 50, 50

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
            home_bc=h_bc if h_bc is not None else 0,
            away_bc=a_bc if a_bc is not None else 0,
            home_xgot=h_xgot if h_xgot is not None else 0.0,
            away_xgot=a_xgot if a_xgot is not None else 0.0,
            home_xg=h_xg if h_xg is not None else 0.0,
            away_xg=a_xg if a_xg is not None else 0.0,
            home_sot=h_sot if h_sot is not None else 0,
            away_sot=a_sot if a_sot is not None else 0,
            home_shots=h_shots if h_shots is not None else 0,
            away_shots=a_shots if a_shots is not None else 0,
            home_xa=h_xa if h_xa is not None else 0.0,
            away_xa=a_xa if a_xa is not None else 0.0,
            home_corners=self._get_stat_int(stats, CORNERS_LABELS, "h"),
            away_corners=self._get_stat_int(stats, CORNERS_LABELS, "a"),
            home_possession=h_poss,
            away_possession=a_poss,
            home_dangerous_attacks=self._get_stat_int(stats, DANGEROUS_ATTACKS_LABELS, "h"),
            away_dangerous_attacks=self._get_stat_int(stats, DANGEROUS_ATTACKS_LABELS, "a"),
            home_attacks=self._get_stat_int(stats, ATTACKS_LABELS, "h"),
            away_attacks=self._get_stat_int(stats, ATTACKS_LABELS, "a"),
            home_shots_off_target=self._get_stat_int(stats, SHOTS_OFF_TARGET_LABELS, "h"),
            away_shots_off_target=self._get_stat_int(stats, SHOTS_OFF_TARGET_LABELS, "a"),
            home_blocked_shots=self._get_stat_int(stats, BLOCKED_SHOTS_LABELS, "h"),
            away_blocked_shots=self._get_stat_int(stats, BLOCKED_SHOTS_LABELS, "a"),
            home_fouls=self._get_stat_int(stats, FOULS_LABELS, "h"),
            away_fouls=self._get_stat_int(stats, FOULS_LABELS, "a"),
            home_yellow_cards=self._get_stat_int(stats, YELLOW_CARDS_LABELS, "h"),
            away_yellow_cards=self._get_stat_int(stats, YELLOW_CARDS_LABELS, "a"),
            home_saves=self._get_stat_int(stats, SAVES_LABELS, "h"),
            away_saves=self._get_stat_int(stats, SAVES_LABELS, "a"),
            all_stats=stats,
            home_red_cards=self._get_stat_int(stats, RED_CARDS_LABELS, "h") if self._get_stat_int_or_none(stats, RED_CARDS_LABELS, "h") is not None else red_data.get("home_red", 0),
            away_red_cards=self._get_stat_int(stats, RED_CARDS_LABELS, "a") if self._get_stat_int_or_none(stats, RED_CARDS_LABELS, "a") is not None else red_data.get("away_red", 0),
            home_bc_raw=h_bc,
            away_bc_raw=a_bc,
            home_xgot_raw=h_xgot,
            away_xgot_raw=a_xgot,
            home_xg_raw=h_xg,
            away_xg_raw=a_xg,
            home_sot_raw=h_sot,
            away_sot_raw=a_sot,
            home_shots_raw=h_shots,
            away_shots_raw=a_shots,
            start_time=dados.get("start_time", ""),
            start_date=dados.get("start_date", ""),
            events=red_data.get("events", []) if red_data else [],
        )

    def _parse_score(self, score_raw: str, title: str = "") -> tuple:
        if title:
            m = re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b", title.split("|")[0])
            if m:
                h, a = int(m.group(1)), int(m.group(2))
                if h <= 20 and a <= 20:
                    return h, a
        if not score_raw:
            return 0, 0
        m = re.search(r"(\d{1,2})\s*[-:]\s*(\d{1,2})", score_raw)
        if not m:
            return 0, 0
        return int(m.group(1)), int(m.group(2))

    def _parse_minute(self, status_raw: str, score_raw: str = "") -> int:
        status = (status_raw or "").strip()
        if not status:
            return 0
        up = status.upper()
        for source in (status, score_raw):
            m = re.search(r"(\d{1,3}):(\d{2})", source)
            if m:
                n = int(m.group(1))
                if 0 <= n <= 130:
                    return n
        if "TERMINADO" in up or "FINISHED" in up or "ENCERRADO" in up or re.search(r"\bFT\b", up):
            return 90
        if "INTERVALO" in up or "HALF TIME" in up or re.search(r"\bHT\b", up):
            return 45
        m = re.search(r"\b(\d{1,3})\b", status)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 130:
                return n
        return 0

    def _get_stat_float(self, stats: dict, labels: list, side: str) -> float:
        stats_lower = {k.lower().strip(): v for k, v in stats.items()}
        for label in labels:
            key = label.lower().strip()
            if key in stats_lower:
                val = stats_lower[key].get(side, "")
                return self._to_float(val)
        for label in labels:
            key = label.lower().strip()
            for sk, sv in stats_lower.items():
                if key in sk or sk in key:
                    val = sv.get(side, "")
                    v = self._to_float(val)
                    if v > 0:
                        return v
        return 0.0

    def _get_stat_int(self, stats: dict, labels: list, side: str) -> int:
        return int(self._get_stat_float(stats, labels, side))

    def _get_stat_float_or_none(self, stats: dict, labels: list, side: str):
        stats_lower = {k.lower().strip(): v for k, v in stats.items()}
        for label in labels:
            key = label.lower().strip()
            if key in stats_lower:
                raw = stats_lower[key].get(side, None)
                if raw is not None and str(raw).strip() != "":
                    return self._to_float(raw)
        for label in labels:
            key = label.lower().strip()
            for sk, sv in stats_lower.items():
                if key in sk or sk in key:
                    raw = sv.get(side, None)
                    if raw is not None and str(raw).strip() != "":
                        return self._to_float(raw)
        return None

    def _get_stat_int_or_none(self, stats: dict, labels: list, side: str):
        v = self._get_stat_float_or_none(stats, labels, side)
        return int(v) if v is not None else None

    def _to_float(self, s: str) -> float:
        if not s:
            return 0.0
        m = re.search(r'([\d]+(?:[\.,]\d+)?)', str(s).strip())
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                return 0.0
        return 0.0

# =============================================================================
# 10. LOOP PRINCIPAL DO MOTOR CRAWLER STANDALONE
# =============================================================================
def run_unified_bridge():
    print("=" * 78)
    print("🚀 BacanaLive Web Bridge (bridge_web.py) — Motor Crawler Unificado Standalone")
    print(f"📡 Webhook Destino: {DASHBOARD_WEBHOOK}")
    print(f"⚙️ Config Local Sync: {LOCAL_SERVER_URL}/api/rules/config")
    print("=" * 78)

    has_playwright = False
    try:
        import playwright
        has_playwright = True
        print("✅ Motor Nativo Playwright Detectado e Carregado!")
    except Exception as e:
        has_playwright = False
        print(f"ℹ️ Playwright não instalado ({e}). Operando via contingência API ultra-rápida.")

    if has_playwright:
        cfg = fetch_operational_crawler_config()
        last_discovery_time = 0.0
        is_discovering = False

        def perform_discovery(context_ref, accept_cookies_fn):
            nonlocal last_discovery_time, is_discovering
            if is_discovering:
                return
            is_discovering = True
            try:
                print(f"🔭 [Discovery] Varrendo grade Flashscore para catalogar novos jogos...")
                live_matches = discover_live_games(
                    context_ref,
                    "https://www.flashscore.com.br/",
                    cookie_accept_fn=accept_cookies_fn,
                    timeout_ms=12000
                )
                last_discovery_time = time.time()
                dismissed_ids = fetch_dismissed_matches()
                print(f"✨ [Discovery] {len(live_matches)} partidas AO VIVO catalogadas! ({len(dismissed_ids)} suprimidas manualmente)")

                for item in live_matches:
                    mid = item.get("mid")
                    if not mid or mid in dismissed_ids:
                        continue
                    url = item.get("url")
                    l_name = item.get("league", "")
                    c_name = item.get("country", "")
                    home = item.get("home", "")
                    away = item.get("away", "")
                    h_score = item.get("home_score", 0)
                    a_score = item.get("away_score", 0)
                    minute = item.get("minute", 0)
                    status = item.get("status", "LIVE")
                    ad_val = item.get("ad", 0)
                    ao_val = item.get("ao", 0)
                    stage_code = item.get("stage_code", "")
                    st_str = item.get("startTime", "")
                    sd_iso = item.get("startDate", "")

                    if is_ignored_match(l_name, c_name, home, away):
                        continue

                    catalog_mgr.upsert_discovered(
                        match_id=mid,
                        url=url,
                        league=l_name,
                        country=c_name,
                        home=home,
                        away=away,
                        home_score=h_score,
                        away_score=a_score,
                        minute=minute,
                        status=status,
                        ad=ad_val,
                        ao=ao_val,
                        stage_code=stage_code,
                        kickoff_time_str=st_str,
                        start_date_iso=sd_iso
                    )

                catalog_mgr.prune_stale(max_unseen_minutes=cfg.get("autoPruneMinutes", 30))
                catalog_mgr.save()
            except Exception as d_err:
                print(f"⚠️ [Discovery] Falha na descoberta DOM ({d_err}). Acionando fallback HTTP...")
                try:
                    fb_matches = http_fallback_discover_live()
                    last_discovery_time = time.time()
                    dismissed_ids = fetch_dismissed_matches()
                    for item in fb_matches:
                        mid = item.get("mid")
                        if not mid or mid in dismissed_ids:
                            continue
                        url = item.get("url")
                        l_name = item.get("league", "")
                        c_name = item.get("country", "")
                        home = item.get("home", "")
                        away = item.get("away", "")
                        h_score = item.get("home_score", 0)
                        a_score = item.get("away_score", 0)
                        minute = item.get("minute", 0)
                        status = item.get("status", "LIVE")
                        ad_val = item.get("ad", 0)
                        ao_val = item.get("ao", 0)
                        stage_code = item.get("stage_code", "")
                        st_str = item.get("startTime", "")
                        sd_iso = item.get("startDate", "")

                        if is_ignored_match(l_name, c_name, home, away):
                            continue

                        catalog_mgr.upsert_discovered(
                            match_id=mid,
                            url=url,
                            league=l_name,
                            country=c_name,
                            home=home,
                            away=away,
                            home_score=h_score,
                            away_score=a_score,
                            minute=minute,
                            status=status,
                            ad=ad_val,
                            ao=ao_val,
                            stage_code=stage_code,
                            kickoff_time_str=st_str,
                            start_date_iso=sd_iso
                        )
                    catalog_mgr.save()
                except Exception as fb_err:
                    print(f"⚠️ [Discovery Fallback Error]: {fb_err}")
            finally:
                is_discovering = False

        with FlashscoreReader(headless=True) as reader:
            if cfg.get("routeResourceBlock", True):
                try:
                    reader._context.route(
                        "**/*.{png,jpg,jpeg,webp,gif,svg,woff,woff2,ttf,otf,mp4,mp3}",
                        lambda route: route.abort() if route.request.resource_type in ("image", "font", "media") else route.continue_()
                    )
                    print("🚀 [Playwright] Bloqueador seletivo de imagens, fontes e mídias ativado!")
                except Exception as route_err:
                    print(f"ℹ️ Route blocker: {route_err}")

            perform_discovery(reader._context, reader._accept_cookies)

            cycle_count = 0
            last_forced_refresh_time = time.time()

            while RUNNING:
                try:
                    cfg = fetch_operational_crawler_config()

                    disc_interval = cfg.get("discoveryIntervalSeconds", 180)
                    if (time.time() - last_discovery_time) > disc_interval:
                        perform_discovery(reader._context, reader._accept_cookies)

                    # Força refresh completo em todas as partidas a cada 180s
                    if (time.time() - last_forced_refresh_time) >= 180:
                        print("\n🔄 [Refresh Forçado 180s] Forçando re-varredura completa em todas as partidas da grade...")
                        for m_id, entry in catalog_mgr.matches.items():
                            if not entry.is_finished:
                                entry.last_scanned_at = 0.0
                        last_forced_refresh_time = time.time()

                    max_wl = cfg.get("maxWatchlistSize", 15)
                    t3_res = cfg.get("tier3ReservedSlots", 2)
                    min_m = cfg.get("minEntryMinute", 20)
                    max_m = cfg.get("maxEntryMinute", 83)
                    anti_spam = cfg.get("antiSpamCooldownMinutes", 5)
                    t_filter = cfg.get("tierFilter", {})

                    watchlist_items = catalog_mgr.select_watchlist_by_tiers(
                        max_size=max_wl,
                        tier3_reserved=t3_res,
                        min_entry_minute=min_m,
                        max_entry_minute=max_m,
                        anti_spam_minutes=anti_spam,
                        tier_filter=t_filter
                    )

                    if not watchlist_items:
                        # Descobre quanto tempo falta para o próximo jogo precisar de refresh
                        now_t = time.time()
                        min_rem = 15.0
                        with catalog_mgr.lock:
                            for e in catalog_mgr.matches.values():
                                if not e.is_finished:
                                    _, _, rem = e.should_scan(now_t, anti_spam)
                                    if rem > 0 and rem < min_rem:
                                        min_rem = rem
                        
                        sleep_s = max(4.0, min(min_rem, 15.0))
                        print(f"⏳ [Aguardando TTL Cache] Catálogo: {len(catalog_mgr.matches)} partidas ativas sincronizadas. Próximo lote em {int(sleep_s)}s...")
                        time.sleep(sleep_s)
                        continue

                    cycle_count += 1
                    print(f"\n⚡ [SCAN #{cycle_count}] Watchlist Ativa: {len(watchlist_items)} jogos precisando de refresh (Total no Catálogo: {len(catalog_mgr.matches)})")

                    scanned_count = 0
                    for entry, tier_name in watchlist_items:
                        if not RUNNING:
                            break

                        try:
                            ms = reader.read_match(entry.url, match_id=entry.match_id, timeout_ms=4500, fallback_catalog_entry=entry)
                            if ms:
                                is_ended = (ms.minute or 0) > 125 or ms.status_raw in ("FT", "Ended", "Finished", "Encerrado", "TERMINADO", "AET", "PEN")
                                if is_ended:
                                    catalog_mgr.mark_finished(entry.match_id)
                                    emit_match_update({
                                        "id": f"fs_{ms.match_id}",
                                        "status": "FT",
                                        "minute": ms.minute or 90,
                                        "homeTeam": {"name": ms.home or entry.home or "Mandante"},
                                        "awayTeam": {"name": ms.away or entry.away or "Visitante"}
                                    }, tier_tag="FT")
                                    continue

                                league_f = ms.league or entry.league or "FlashScore Live"
                                country_f = (ms.country or entry.country or "Internacional").replace(":", "").strip()

                                # Se a liga começar com o nome do país, remover para evitar duplicação
                                if ":" in league_f:
                                    pfx, sep, sfx = league_f.partition(":")
                                    if pfx.strip().lower() == country_f.lower() or not country_f or country_f == "Internacional":
                                        if not country_f or country_f == "Internacional":
                                            country_f = pfx.strip().title()
                                        league_f = sfx.strip()

                                home_name = ms.home if (ms.home and ms.home != "?") else (entry.home or "Mandante")
                                away_name = ms.away if (ms.away and ms.away != "?") else (entry.away or "Visitante")

                                if is_ignored_match(league_f, country_f, home_name, away_name):
                                    continue

                                p_home = ms.home_possession if ms.home_possession > 0 else 50
                                p_away = ms.away_possession if ms.away_possession > 0 else (100 - p_home)

                                has_real_stats = (ms.home_bc > 0 or ms.away_bc > 0 or ms.home_xgot > 0 or ms.away_xgot > 0 or ms.home_sot > 0 or ms.away_sot > 0)
                                real_minute = ms.minute or entry.get_current_minute() or 0

                                is_finished_stagnant = catalog_mgr.update_scan_result(
                                    match_id=entry.match_id,
                                    minute=real_minute,
                                    status=ms.status_raw or "LIVE",
                                    home_score=ms.home_score,
                                    away_score=ms.away_score,
                                    had_stats=has_real_stats,
                                    no_stats=(not has_real_stats)
                                )

                                if is_finished_stagnant or entry.is_finished:
                                    catalog_mgr.mark_finished(entry.match_id)
                                    emit_match_update({
                                        "id": f"fs_{ms.match_id}",
                                        "status": "FT",
                                        "minute": real_minute or 90,
                                        "homeTeam": {"name": home_name, "score": ms.home_score},
                                        "awayTeam": {"name": away_name, "score": ms.away_score}
                                    }, tier_tag="FT")
                                    continue

                                start_time_str = ms.start_time or entry.kickoff_time_str or ""
                                start_date_iso = ms.start_date or entry.start_date_iso or ""

                                payload = {
                                    "id": f"fs_{ms.match_id}",
                                    "homeTeam": {"name": home_name, "score": ms.home_score, "redCards": ms.home_red_cards},
                                    "awayTeam": {"name": away_name, "score": ms.away_score, "redCards": ms.away_red_cards},
                                    "score": {"home": ms.home_score, "away": ms.away_score},
                                    "homeScore": ms.home_score,
                                    "awayScore": ms.away_score,
                                    "league": league_f,
                                    "country": country_f or "Internacional",
                                    "leagueCountry": country_f or "Internacional",
                                    "startTime": start_time_str,
                                    "startDate": start_date_iso,
                                    "minute": real_minute,
                                    "status": ms.status_raw or ("1H" if real_minute <= 45 else "2H"),
                                    "statistics": {
                                        "possession": {"home": p_home, "away": p_away},
                                        "shotsOnTarget": {"home": ms.home_sot, "away": ms.away_sot},
                                        "shotsOffTarget": {"home": ms.home_shots_off_target, "away": ms.away_shots_off_target},
                                        "corners": {"home": ms.home_corners, "away": ms.away_corners},
                                        "dangerousAttacks": {"home": ms.home_dangerous_attacks, "away": ms.away_dangerous_attacks},
                                        "attacks": {"home": ms.home_attacks, "away": ms.away_attacks},
                                        "xg": {"home": ms.home_xg, "away": ms.away_xg},
                                        "xgot": {"home": ms.home_xgot, "away": ms.away_xgot},
                                        "bigChances": {"home": ms.home_bc, "away": ms.away_bc},
                                        "yellowCards": {"home": ms.home_yellow_cards, "away": ms.away_yellow_cards},
                                        "redCards": {"home": ms.home_red_cards, "away": ms.away_red_cards},
                                        "goalkeeperSaves": {"home": ms.home_saves, "away": ms.away_saves},
                                    },
                                    "events": ms.events if getattr(ms, "events", None) else [],
                                    "updatedAt": datetime.now(timezone.utc).isoformat()
                                }

                                emit_match_update(payload, tier_tag=tier_name)
                                scanned_count += 1
                                print(f"  [{tier_name}] {home_name} {ms.home_score}x{ms.away_score} {away_name} ({ms.minute}') | xG: {ms.home_xg:.2f}x{ms.away_xg:.2f} | BC: {ms.home_bc}x{ms.away_bc}")
                        except Exception as item_err:
                            print(f"  ⚠️ Erro ao ler jogo {entry.match_id}: {item_err}")
                            entry.last_scanned_at = time.time()

                    print(f"✅ Ciclo #{cycle_count} concluído! {scanned_count} jogos transmitidos ao Dashboard. Aguardando 12s para próximo scan...")
                    time.sleep(12.0)
                except Exception as loop_err:
                    print(f"⚠️ Erro no loop de varredura: {loop_err}")
                    time.sleep(5.0)
    else:
        # Contingência HTTP API com Catálogo Persistente & Cache por TIER
        session = _create_http_session()
        session.headers.update(HEADERS)
        cycle_count = 0
        last_forced_refresh_time = time.time()

        while RUNNING:
            try:
                cycle_count += 1
                cfg = fetch_operational_crawler_config()
                anti_spam = cfg.get("antiSpamCooldownMinutes", 5)

                dismissed_ids = fetch_dismissed_matches()
                url = "https://api.sofascore.app/api/v1/sport/football/events/live"
                res = session.get(url, timeout=8)
                if res.status_code == 200:
                    events = res.json().get("events", [])
                    for event in events:
                        ev_id = f"live_{event.get('id')}"
                        if ev_id in dismissed_ids:
                            continue
                        t_info = event.get("tournament", {})
                        l_name = t_info.get("name", "Geral")
                        c_name = t_info.get("category", {}).get("name", "Mundo")
                        h_name = event.get("homeTeam", {}).get("name", "Home")
                        a_name = event.get("awayTeam", {}).get("name", "Away")
                        if is_ignored_match(l_name, c_name, h_name, a_name):
                            continue
                        catalog_mgr.upsert_discovered(ev_id, "", league=l_name, country=c_name, home=h_name, away=a_name)

                    now = time.time()
                    dispatched_count = 0
                    cached_skipped = 0

                    for event in events:
                        ev_id = f"live_{event.get('id')}"
                        if ev_id in dismissed_ids:
                            continue
                        t_info = event.get("tournament", {})
                        l_name = t_info.get("name", "Geral")
                        c_name = t_info.get("category", {}).get("name", "Mundo")
                        h_name = event.get("homeTeam", {}).get("name", "Home")
                        a_name = event.get("awayTeam", {}).get("name", "Away")

                        if is_ignored_match(l_name, c_name, h_name, a_name):
                            continue

                        status_raw = event.get("status", {}).get("description", "LIVE")
                        minute = event.get("time", {}).get("minute", 0)

                        if status_raw in ("Ended", "Finished", "FT", "Encerrado") or minute > 125:
                            catalog_mgr.mark_finished(ev_id)
                            emit_match_update({
                                "id": ev_id,
                                "status": "FT",
                                "minute": minute or 90,
                                "homeTeam": {"name": h_name},
                                "awayTeam": {"name": a_name}
                            }, tier_tag="FT")
                            continue

                        entry = catalog_mgr.matches.get(ev_id)
                        if entry:
                            needs_scan, tier_name, rem_ttl = entry.should_scan(now, anti_spam)
                            if not needs_scan:
                                cached_skipped += 1
                                continue

                        stats_url = f"https://api.sofascore.app/api/v1/event/{event.get('id')}/statistics"
                        s_res = session.get(stats_url, timeout=3.5)
                        stats_data = {}
                        has_stats = False

                        if s_res.status_code == 200:
                            all_stats = s_res.json().get("statistics", [])
                            if all_stats and len(all_stats) > 0:
                                groups = all_stats[0].get("groups", [])
                                for g in groups:
                                    for item in g.get("statisticsItems", []):
                                        n = item.get("name", "")
                                        stats_data[n] = {
                                            "home": item.get("homeValue", 0),
                                            "away": item.get("awayValue", 0)
                                        }
                                has_stats = True

                        h_score = event.get("homeScore", {}).get("current", 0)
                        a_score = event.get("awayScore", {}).get("current", 0)

                        is_finished_stagnant = catalog_mgr.update_scan_result(
                            match_id=ev_id,
                            minute=minute,
                            status=status_raw,
                            home_score=h_score,
                            away_score=a_score,
                            had_stats=has_stats
                        )

                        if is_finished_stagnant:
                            catalog_mgr.mark_finished(ev_id)
                            emit_match_update({
                                "id": ev_id,
                                "status": "FT",
                                "minute": minute or 90,
                                "homeTeam": {"name": h_name},
                                "awayTeam": {"name": a_name}
                            }, tier_tag="FT")
                            continue

                        p_home = stats_data.get("Ball possession", {}).get("home", 50)
                        p_away = stats_data.get("Ball possession", {}).get("away", 50)

                        payload = {
                            "id": ev_id,
                            "homeTeam": {"name": h_name, "score": h_score},
                            "awayTeam": {"name": a_name, "score": a_score},
                            "score": {"home": h_score, "away": a_score},
                            "homeScore": h_score,
                            "awayScore": a_score,
                            "league": l_name,
                            "country": c_name or "Internacional",
                            "leagueCountry": c_name or "Internacional",
                            "minute": minute or 0,
                            "status": status_raw,
                            "statistics": {
                                "possession": {"home": p_home, "away": p_away},
                                "shotsOnTarget": {"home": stats_data.get("Shots on target", {}).get("home", 0), "away": stats_data.get("Shots on target", {}).get("away", 0)},
                                "corners": {"home": stats_data.get("Corner kicks", {}).get("home", 0), "away": stats_data.get("Corner kicks", {}).get("away", 0)},
                                "dangerousAttacks": {"home": stats_data.get("Dangerous attacks", {}).get("home", 0), "away": stats_data.get("Dangerous attacks", {}).get("away", 0)},
                                "xg": {"home": stats_data.get("Expected goals", {}).get("home", 0.0), "away": stats_data.get("Expected goals", {}).get("away", 0.0)},
                                "bigChances": {"home": stats_data.get("Big chances", {}).get("home", 0), "away": stats_data.get("Big chances", {}).get("away", 0)},
                            },
                            "updatedAt": datetime.now(timezone.utc).isoformat()
                        }

                        emit_match_update(payload, tier_tag=entry.tier if entry else "T2")
                        dispatched_count += 1
                        time.sleep(0.05)

                    print(f"📡 [Ciclo API #{cycle_count}] {dispatched_count} jogos enviados ({cached_skipped} economizados via cache TTL). Aguardando 30s...")
                time.sleep(30.0)
            except Exception as e:
                print(f"❌ Erro na varredura: {e}")
                time.sleep(10.0)

    notify_crawler_shutdown()
    print("✅ bridge_web.py finalizado. Grade zerada no dashboard.")

if __name__ == "__main__":
    run_unified_bridge()
