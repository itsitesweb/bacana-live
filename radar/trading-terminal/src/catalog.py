"""
Catalog — registro persistente de jogos descobertos pelo live_daemon.

Indexado por match_id. Sobrevive a restart via logs/live_daemon_catalog.json.
Não toca state.json (posições/anti-spam continuam separados).

SEM lógica de regra. SEM Telegram. Apenas tracking de descoberta/scan/stale/no_stats.

Usado pelo modo --use-watchlist do live_daemon.py.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from src.premium_leagues import (is_premium_url, classify_premium,
                                  clean_league_name as _clean_league_name,
                                  LEVEL_NONE, REASON_NONE, REASON_TEAM_SLUG)


def _has_evidence_for_premium_c(meta: Optional[dict], entry: Optional[dict]) -> bool:
    """Premium C exige PELO MENOS UMA evidência além do slug da URL.

    O slug do time aparecer no whitelist é necessário mas NÃO suficiente:
    entries fantasmas tipo 'FS_UeD7XtzM_KGO4pUqO | min=None None' nunca
    deveriam virar premium só porque a URL contém 'bahia' ou 'corinthians'.

    Sinais aceitos (basta UM):
      a) league_meta (do ciclo atual de discovery) tem league_name OU country
      b) entry já persistido tem league_meta_raw com league_name OU country
      c) entry já persistido tem premium_league_name OU premium_country
      d) entry já foi escaneado com sucesso (ever_loaded_stats=True)
      e) entry tem last_minute populado (foi visto ao vivo ao menos uma vez)

    Sem nenhuma evidência → demote Premium C → não-premium.
    """
    m = meta or {}
    if m.get("league_name") or m.get("country"):
        return True
    e = entry or {}
    raw = e.get("league_meta_raw") or {}
    if raw.get("league_name") or raw.get("country"):
        return True
    if e.get("premium_league_name") or e.get("premium_country"):
        return True
    if e.get("ever_loaded_stats"):
        return True
    if e.get("last_minute") is not None:
        return True
    return False


# Regex pra extrair fingerprint do jogo (home_id, away_id) da URL.
# Mesmo jogo no Flashscore pode aparecer com 2 URLs:
#   a) /jogo/futebol/atletico-mg-hGLC5Bah/corinthians-QBGfQbSe       (sem mid)
#   b) /jogo/futebol/atletico-mg-hGLC5Bah/corinthians-QBGfQbSe/?mid=A3c2Hc54
# Ambas têm o MESMO fingerprint "hGLC5Bah_QBGfQbSe" → dedup.
_FINGERPRINT_RE = re.compile(
    r"/jogo/futebol/[a-z0-9-]+?-([A-Za-z0-9]{6,})/[a-z0-9-]+?-([A-Za-z0-9]{6,})",
    re.IGNORECASE,
)


def _match_fingerprint(url: str) -> str:
    """Extrai 'home_id_away_id' da URL — chave de deduplicação.
    Retorna string vazia se a URL não bater o padrão (jogo sem dedup possível)."""
    if not url:
        return ""
    m = _FINGERPRINT_RE.search(url)
    if not m:
        return ""
    return f"{m.group(1)}_{m.group(2)}"


def _is_mid_based(match_id: str) -> bool:
    """True se o match_id veio de '?mid=XXX' (preferido como canônico).
    Mid-based: FS_<id>  (sem underscore depois de FS_).
    Fingerprint-based: FS_<home_id>_<away_id> (2 partes)."""
    if not match_id or not match_id.startswith("FS_"):
        return False
    return "_" not in match_id[3:]


def _pick_canonical(entries: list) -> Optional[dict]:
    """Escolhe o entry canônico entre duplicados do mesmo jogo.

    Prioridade (do mais forte ao mais fraco):
      A) mid-based (URL tem ?mid=...)
      B) last_seen_at mais recente
      C) last_scanned_at mais recente
      D) last_minute maior (mais avançado no jogo)
      E) ever_loaded_stats=True
      F) URL mais longa (proxy para "mais nova")
    """
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]

    def _key(e):
        return (
            # A) mid-based primeiro (descendente: True > False)
            1 if _is_mid_based(e.get("match_id", "")) else 0,
            # B) last_seen_at desc
            e.get("last_seen_at") or "",
            # C) last_scanned_at desc
            e.get("last_scanned_at") or "",
            # D) last_minute desc
            int(e.get("last_minute") or 0),
            # E) ever_loaded_stats desc
            1 if e.get("ever_loaded_stats") else 0,
            # F) URL mais longa desc
            len(e.get("url") or ""),
        )

    return sorted(entries, key=_key, reverse=True)[0]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _no_stats_backoff_seconds(count: int) -> int:
    """Backoff ESCALONADO CURTO (v4.7+):
      1ª falha → 3 min
      2ª falha → 8 min
      3ª falha → 15 min
      4ª+ falha → 30 min

    HISTÓRICO: v2.10 usava 30 min na 1ª falha. Causava perda de
    monitoramento de jogos Premium A ao vivo: jogo entrava ao vivo,
    Flashscore ainda não tinha populado xG/xGOT, sistema entrava em
    backoff de 30 min, perdia bloco 30 inteiro. Coverage_guard
    reportava 11+ jogos premium fora da operação.

    Solução: escalonado curto. Se Flashscore demorar pra popular stats
    (normal nos primeiros 5-10 min de jogo), retry em 3 min pega o
    jogo logo após. Se falhar de novo, escalona pra evitar loop.
    """
    if count <= 1:
        return 3 * 60        # 1ª falha → 3 min
    if count == 2:
        return 8 * 60        # 2ª falha → 8 min
    if count == 3:
        return 15 * 60       # 3ª falha → 15 min
    return 30 * 60           # 4ª+ falha → 30 min (jogo realmente sem stats)


# R6 (v2.10): regex de reserve/youth aplicado no upsert do catalog.
import re as _re_reserve
_RESERVE_URL_PATTERNS = [
    "/u17", "/u18", "/u19", "/u20", "/u21", "/u23",
    "-u17-", "-u19-", "-u20-", "-u23-",
    "-sub-17", "-sub-19", "-sub-20", "-sub-23",
    "-reservas", "-reserves", "-youth", "-juniores",
    "-feminino", "-women",
]
_RESERVE_NAME_RE = _re_reserve.compile(
    r"\bU1[5-9]\b|\bU2[0-3]\b|\bSUB[-\s]?1[5-9]\b|\bSUB[-\s]?2[0-3]\b|"
    r"\bRESERVE[S]?\b|\bRESERVA[S]?\b|\bYOUTH\b|\bJUNIOR[S]?\b|"
    r"\bACADEMY\b|\bACADEMIA\b|\bWOMEN\b|\bFEMININ[OA]\b",
    _re_reserve.IGNORECASE,
)


class Catalog:
    """Catálogo de jogos descobertos pelo daemon (modo watchlist)."""

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = Path(persist_path) if persist_path else None
        self._games: dict = {}

    # ─── Persistence ────────────────────────────────────────────────

    def load(self) -> None:
        """Carrega catálogo do disco. Descarta se schema inválido."""
        if not self.persist_path or not self.persist_path.exists():
            self._games = {}
            return
        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                self._games = {}
                return
            cleaned = {}
            for mid, entry in data.items():
                if isinstance(entry, dict) and entry.get("url"):
                    # MIGRAÇÃO FORÇADA (v2.1 — country+competition):
                    # Recomputa SEMPRE is_premium / premium_reason / premium_level
                    # para limpar contaminação de catálogos antigos onde
                    # "Premier League | Kuwait", "Bundesliga | Singapura",
                    # "Premier League | Serra Leoa", "Premier League | Ilhas
                    # Faroé" foram marcados como premium A só pelo substring
                    # do nome — sem validação de country.
                    country = entry.get("premium_country", "") or ""
                    league_name_clean = _clean_league_name(
                        entry.get("premium_league_name", "") or "",
                        country=country,
                    )
                    cls = classify_premium(
                        entry["url"],
                        league_name=league_name_clean,
                        league_country=country,
                    )
                    # GATE PREMIUM C (v2.2 — evidência além do slug):
                    # se classify_premium retornou C SÓ porque o slug do
                    # time bate, mas o entry persistido não tem league_name,
                    # country, last_minute nem ever_loaded_stats, demote para
                    # não-premium. Limpa fantasmas tipo "FS_xxx | min=None None".
                    if cls.get("reason") == REASON_TEAM_SLUG:
                        if not _has_evidence_for_premium_c(None, entry):
                            cls = {
                                **cls,
                                "is_premium": False,
                                "reason": REASON_NONE,
                                "level": LEVEL_NONE,
                            }
                    entry["is_premium"] = bool(cls["is_premium"])
                    entry["premium_reason"] = cls["reason"]
                    entry["premium_level"] = cls.get("level", LEVEL_NONE)
                    entry["premium_league_name"] = cls["league_name"]
                    entry["premium_country"] = cls["country"] or country
                    entry.setdefault("league_meta_raw", {})
                    entry.setdefault("excluded_duplicate", False)
                    entry.setdefault("duplicate_of", "")
                    # LIMPEZA AMBÍGUA (v2.3): se o entry foi marcado
                    # finished_or_not_live por INVALID_MINUTE_STATUS ou
                    # AMBIGUOUS_MINUTE_STATUS, MAS nunca chegou a carregar
                    # stats nem teve last_scanned_at/last_minute, então
                    # a marcação veio de uma leitura ambígua (kickoff em
                    # curso). Limpar pra permitir o jogo voltar à watchlist.
                    if entry.get("finished_or_not_live"):
                        nlr = entry.get("not_live_reason", "")
                        if nlr in ("INVALID_MINUTE_STATUS",
                                    "AMBIGUOUS_MINUTE_STATUS"):
                            never_scanned = (
                                not entry.get("ever_loaded_stats")
                                and not entry.get("last_scanned_at")
                                and entry.get("last_minute") is None
                            )
                            if never_scanned:
                                entry["finished_or_not_live"] = False
                                entry["finished_or_not_live_at"] = None
                                entry["finished_or_not_live_until"] = None
                                entry["not_live_reason"] = ""
                    cleaned[mid] = entry
            self._games = cleaned
            # Recalcula dedup com base no estado persistido
            self.recompute_duplicates()
        except (json.JSONDecodeError, OSError):
            self._games = {}

    def save(self) -> None:
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "w") as f:
            json.dump(self._games, f, indent=2, ensure_ascii=False)

    # ─── Discovery ──────────────────────────────────────────────────

    @staticmethod
    def _is_reserve_or_youth(url: str,
                                league_meta: Optional[dict] = None) -> bool:
        """R6: detecta reserve/youth no URL ou metadados de liga.
        Usado pelo upsert_discovered pra bloquear no nascimento."""
        if url:
            url_low = url.lower()
            for pat in _RESERVE_URL_PATTERNS:
                if pat in url_low:
                    return True
        if league_meta:
            for k in ("league_name", "country"):
                v = (league_meta.get(k) or "").strip()
                if v and _RESERVE_NAME_RE.search(v):
                    return True
        return False

    def upsert_discovered(self, match_id: str, url: str,
                            league_meta: Optional[dict] = None) -> None:
        """Marca jogo como descoberto/visto agora. Cria entry se novo.

        Args:
            match_id: ID do jogo (FS_xxx).
            url: URL do Flashscore.
            league_meta: dict opcional com info da liga capturada pelo discovery:
                {"league_name": str, "country": str, "css_classes": str|list}.
                Usado pra classificar premium em 3 níveis (A: CSS destacado,
                B: nome de liga premium, C: slug do time — fallback).
        """
        # R6 (v2.10): blocklist no UPSERT. Detecta reserve/youth no URL
        # ou nos metadados de liga. Jogos bloqueados ficam marcados
        # como excluded_reserve=True e nunca entram em watchlist.
        if self._is_reserve_or_youth(url, league_meta):
            if match_id in self._games:
                self._games[match_id]["excluded_reserve"] = True
                self._games[match_id]["last_seen_at"] = _now_iso()
            else:
                self._games[match_id] = {
                    "match_id": match_id, "url": url,
                    "excluded_reserve": True,
                    "first_seen_at": _now_iso(),
                    "last_seen_at": _now_iso(),
                    "is_premium": False,
                    "premium_level": LEVEL_NONE,
                }
            return  # NÃO faz upsert completo — bloqueia já

        now = _now_iso()
        meta = league_meta or {}
        cls = classify_premium(
            url,
            league_name=meta.get("league_name"),
            league_country=meta.get("country"),
            league_css_classes=meta.get("css_classes"),
        )
        # GATE PREMIUM C — Premium C exige evidência além do slug
        # (league_meta atual OU entry existente com league/minute/stats).
        if cls.get("reason") == REASON_TEAM_SLUG:
            existing_for_evidence = self._games.get(match_id)
            if not _has_evidence_for_premium_c(meta, existing_for_evidence):
                cls = {
                    **cls,
                    "is_premium": False,
                    "reason": REASON_NONE,
                    "level": LEVEL_NONE,
                }
        if match_id in self._games:
            entry = self._games[match_id]
            entry["last_seen_at"] = now
            entry["url"] = url
            # Re-classifica em todo upsert pra capturar mudança de destaque
            # (Flashscore pode destacar/desdestacar liga ao vivo).
            entry["is_premium"] = bool(cls["is_premium"])
            entry["premium_reason"] = cls["reason"]
            entry["premium_level"] = cls.get("level", LEVEL_NONE)
            # Só atualiza nome/país se o discovery TROUXE — preserva valor anterior
            # quando o ciclo atual não capturou metadados da liga.
            if cls["league_name"]:
                entry["premium_league_name"] = cls["league_name"]
            if cls["country"]:
                entry["premium_country"] = cls["country"]
        else:
            self._games[match_id] = {
                "match_id": match_id,
                "url": url,
                "league_meta_raw": dict(meta),  # bruto do discovery (auditoria)
                "first_seen_at": now,
                "last_seen_at": now,
                "last_scanned_at": None,
                "last_minute": None,
                "last_score": None,
                "ever_loaded_stats": False,
                "no_stats_count": 0,
                "no_stats_until": None,
                "last_stale_at": None,
                "stale_until": None,
                "has_open_position": False,
                "last_signal_action": "",
                "last_signal_minute": 0,
                "last_bc_sum": 0,
                # Ajuste pós-cadência: jogo confirmado como finalizado/suspenso/
                # cancelado/postponed/aet/penalties pelo filtro is_live_match.
                # Não volta pra watchlist enquanto TTL ativo.
                "finished_or_not_live": False,
                "finished_or_not_live_at": None,
                "finished_or_not_live_until": None,
                "not_live_reason": "",
                # Classificação premium em 3 níveis (A>B>C):
                # A) flashscore_highlighted_league — CSS class do header destacada
                # B) premium_league_name — nome da liga no whitelist de nomes
                # C) premium_team_slug — slug do time no whitelist (legado)
                "is_premium": bool(cls["is_premium"]),
                "premium_reason": cls["reason"],
                "premium_level": cls.get("level", LEVEL_NONE),
                "premium_league_name": cls["league_name"] or "",
                "premium_country": cls["country"] or "",
                # Dedup canônico — recalculado a cada upsert
                "excluded_duplicate": False,
                "duplicate_of": "",
            }
        # Re-classifica duplicados após qualquer upsert
        self.recompute_duplicates()

    # ─── Post-scan updates ──────────────────────────────────────────

    def mark_scanned(self, match_id: str, *,
                     minute: Optional[int] = None,
                     score: Optional[str] = None,
                     bc_sum: Optional[int] = None) -> None:
        entry = self._games.get(match_id)
        if entry is None:
            return
        entry["last_scanned_at"] = _now_iso()
        if minute is not None:
            entry["last_minute"] = minute
        if score is not None:
            entry["last_score"] = score
        if bc_sum is not None:
            entry["last_bc_sum"] = bc_sum
        entry["ever_loaded_stats"] = True
        # Sucesso de extração reseta backoff de no_stats
        entry["no_stats_count"] = 0
        entry["no_stats_until"] = None

    def mark_no_stats(self, match_id: str) -> None:
        entry = self._games.get(match_id)
        if entry is None:
            return
        entry["no_stats_count"] = int(entry.get("no_stats_count", 0)) + 1
        backoff_s = _no_stats_backoff_seconds(entry["no_stats_count"])
        entry["no_stats_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=backoff_s)
        ).isoformat()
        entry["last_scanned_at"] = _now_iso()

    def mark_stale(self, match_id: str, ttl_minutes: int) -> None:
        entry = self._games.get(match_id)
        if entry is None:
            return
        entry["last_stale_at"] = _now_iso()
        entry["stale_until"] = (
            datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        ).isoformat()

    def mark_signal(self, match_id: str, action: str, minute: int) -> None:
        entry = self._games.get(match_id)
        if entry is None:
            return
        entry["last_signal_action"] = action
        entry["last_signal_minute"] = int(minute or 0)

    def set_position_open(self, match_id: str, has_open: bool) -> None:
        entry = self._games.get(match_id)
        if entry is None:
            return
        entry["has_open_position"] = bool(has_open)

    # ─── Queries ────────────────────────────────────────────────────

    def all(self) -> list:
        return list(self._games.values())

    def get(self, match_id: str) -> Optional[dict]:
        return self._games.get(match_id)

    def size(self) -> int:
        return len(self._games)

    def is_stale_active(self, match_id: str, now: Optional[datetime] = None) -> bool:
        entry = self._games.get(match_id)
        if not entry or not entry.get("stale_until"):
            return False
        ts = _parse_iso(entry["stale_until"])
        if ts is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now < ts

    def is_no_stats_active(self, match_id: str, now: Optional[datetime] = None) -> bool:
        entry = self._games.get(match_id)
        if not entry or not entry.get("no_stats_until"):
            return False
        ts = _parse_iso(entry["no_stats_until"])
        if ts is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now < ts

    def should_use_short_timeout(self, match_id: str) -> bool:
        """True se o jogo já falhou ao menos 1x em retornar stats.

        Usado pelo daemon (modo codigo_3_1) para passar timeout reduzido ao
        read_match — evita gastar 18s confirmando o que já sabemos:
        provavelmente não vai retornar stats também desta vez.
        """
        entry = self._games.get(match_id)
        if not entry:
            return False
        return int(entry.get("no_stats_count", 0) or 0) >= 1

    def is_premium(self, match_id: str) -> bool:
        """True se o jogo pertence a uma liga premium (Tier 0.5 da watchlist).
        Detecção feita no upsert via slug da URL do Flashscore (sem custo aqui)."""
        entry = self._games.get(match_id)
        if not entry:
            return False
        return bool(entry.get("is_premium", False))

    def count_premium(self) -> int:
        """Total de jogos premium no catálogo (independente de live/finished)."""
        return sum(1 for e in self._games.values() if e.get("is_premium"))

    # ─── Deduplicação canônica ────────────────────────────────────────

    def recompute_duplicates(self) -> dict:
        """Agrupa entries por fingerprint (home_id, away_id) e marca duplicados.

        Cada grupo elege UM canônico via _pick_canonical(); os demais ganham:
            excluded_duplicate = True
            duplicate_of = <canonical_match_id>

        O canônico tem:
            excluded_duplicate = False
            duplicate_of = ""

        Entries sem fingerprint (URL não-parseável) ficam intocados.

        Returns:
            {'groups_with_dups': int, 'duplicates_marked': int}
        """
        groups = {}
        for mid, e in self._games.items():
            fp = _match_fingerprint(e.get("url", ""))
            if not fp:
                continue
            groups.setdefault(fp, []).append(e)

        dups_marked = 0
        groups_with_dups = 0
        for fp, entries in groups.items():
            if len(entries) <= 1:
                # Sem duplicidade — garante flags limpas
                for e in entries:
                    e["excluded_duplicate"] = False
                    e["duplicate_of"] = ""
                continue
            groups_with_dups += 1
            canon = _pick_canonical(entries)
            canon_id = canon["match_id"]
            for e in entries:
                if e["match_id"] == canon_id:
                    e["excluded_duplicate"] = False
                    e["duplicate_of"] = ""
                else:
                    e["excluded_duplicate"] = True
                    e["duplicate_of"] = canon_id
                    dups_marked += 1
        return {"groups_with_dups": groups_with_dups,
                "duplicates_marked": dups_marked}

    def canonical_for_fingerprint(self, fingerprint: str) -> Optional[dict]:
        """Retorna o entry canônico para um fingerprint, ou None."""
        if not fingerprint:
            return None
        matches = [e for e in self._games.values()
                   if _match_fingerprint(e.get("url", "")) == fingerprint]
        return _pick_canonical(matches)

    def get_duplicates_of(self, canonical_mid: str) -> list:
        """Lista entries marcados como duplicate_of=canonical_mid."""
        return [e for e in self._games.values()
                if e.get("duplicate_of") == canonical_mid]

    def premium_audit_by_level(self, watchlist_set, now=None) -> dict:
        """Agrupa premiums por nível (A/B/C) com contadores operacionais.

        Returns:
            {
              "A": [{league, country, live, in_wl, passive, no_stats, entries}, ...],
              "B": [...mesmo formato...],
              "C": [{home_away, mid, in_wl, passive, ...}],  # por jogo (sem liga)
              "passive_entries": [{mid, home_away, league_name, level,
                                   passive_reason, minute, score}],
            }
        """
        from datetime import datetime, timezone
        if now is None:
            now = datetime.now(timezone.utc)

        # A: agregado por liga
        # B: agregado por liga
        a_groups = {}   # (league, country) → {live, in_wl, passive, no_stats, entries}
        b_groups = {}
        c_list = []     # entries C (slug-only — não tem liga, lista por jogo)
        passive_entries = []

        for e in self._games.values():
            mid = e.get("match_id")
            if not e.get("is_premium"):
                continue
            if e.get("excluded_duplicate"):
                continue
            level = e.get("premium_level", LEVEL_NONE)
            league = (e.get("premium_league_name") or "").strip() or "?"
            country = (e.get("premium_country") or "").strip() or "?"

            in_wl = mid in (watchlist_set or set())
            is_finished = self.is_finished_or_not_live_active(mid, now)
            is_no_stats = self.is_no_stats_active(mid, now)
            is_stale = self.is_stale_active(mid, now)
            # Live = catalogado, não-finished, não-stale (mesmo se sem stats)
            is_live = not is_finished and not is_stale

            # Detecta motivo da passive
            passive_reason = ""
            if not in_wl and is_live:
                if is_no_stats:
                    passive_reason = "no_stats_backoff"
                else:
                    passive_reason = "premium_overflow"
            elif is_finished:
                passive_reason = "finished"
            elif is_stale:
                passive_reason = "stale"

            agg_key = (league, country)
            if level == "A":
                groups = a_groups
            elif level == "B":
                groups = b_groups
            else:
                # C (slug fallback) — agrega por jogo, sem agregar liga
                c_list.append({
                    "match_id": mid,
                    "league": league, "country": country,
                    "in_wl": in_wl, "passive_reason": passive_reason,
                    "minute": e.get("last_minute"),
                    "score": e.get("last_score"),
                    "no_stats": is_no_stats,
                })
                if passive_reason:
                    passive_entries.append({
                        "mid": mid, "level": "C",
                        "league_name": league, "country": country,
                        "passive_reason": passive_reason,
                        "minute": e.get("last_minute"),
                        "score": e.get("last_score"),
                    })
                continue

            g = groups.setdefault(agg_key, {
                "league": league, "country": country,
                "live": 0, "in_wl": 0, "passive": 0, "no_stats": 0,
                "entries": [],
            })
            if is_live: g["live"] += 1
            if in_wl:  g["in_wl"] += 1
            if passive_reason: g["passive"] += 1
            if is_no_stats: g["no_stats"] += 1
            g["entries"].append({"mid": mid, "in_wl": in_wl,
                                 "passive_reason": passive_reason,
                                 "minute": e.get("last_minute"),
                                 "score": e.get("last_score")})
            if passive_reason:
                passive_entries.append({
                    "mid": mid, "level": level,
                    "league_name": league, "country": country,
                    "passive_reason": passive_reason,
                    "minute": e.get("last_minute"),
                    "score": e.get("last_score"),
                })

        def _flatten(groups):
            return sorted(groups.values(),
                          key=lambda g: (-g["live"], -g["in_wl"]))

        return {
            "A": _flatten(a_groups),
            "B": _flatten(b_groups),
            "C": sorted(c_list,
                         key=lambda c: (0 if c["in_wl"] else 1)),
            "passive_entries": passive_entries,
        }

    def leagues_audit(self) -> dict:
        """Agrupa o catálogo por liga e retorna estatísticas pra auditoria.

        Returns:
            {
                "premium":     [{league_name, country, reason, count, highlighted}, ...],
                "non_premium": [{league_name, country, count}, ...],
                "unknown_league_count": int,  # entries sem league_name (DOM falhou)
            }
        """
        premium_groups = {}    # (league, country, reason) → count
        non_premium_groups = {}  # (league, country) → count
        unknown = 0
        for e in self._games.values():
            ln = (e.get("premium_league_name") or "").strip()
            co = (e.get("premium_country") or "").strip()
            if not ln:
                unknown += 1
                continue
            if e.get("is_premium"):
                key = (ln, co, e.get("premium_reason", ""))
                premium_groups[key] = premium_groups.get(key, 0) + 1
            else:
                key = (ln, co)
                non_premium_groups[key] = non_premium_groups.get(key, 0) + 1
        premium = [
            {"league_name": k[0], "country": k[1], "reason": k[2],
             "highlighted": k[2] == "flashscore_highlighted_league",
             "count": v}
            for k, v in sorted(premium_groups.items(),
                                key=lambda kv: -kv[1])
        ]
        non_premium = [
            {"league_name": k[0], "country": k[1], "count": v}
            for k, v in sorted(non_premium_groups.items(),
                                key=lambda kv: -kv[1])
        ]
        return {
            "premium": premium,
            "non_premium": non_premium,
            "unknown_league_count": unknown,
        }

    def count_in_backoff(self, now: Optional[datetime] = None) -> int:
        """Total de jogos atualmente em backoff de no_stats (TTL ativo)."""
        now = now or datetime.now(timezone.utc)
        count = 0
        for mid in self._games:
            if self.is_no_stats_active(mid, now=now):
                count += 1
        return count

    # ─── Finished / not-live marker (ajuste pós-cadência) ─────────

    def mark_finished_or_not_live(self, match_id: str, reason: str,
                                    ttl_hours: int = 12) -> None:
        """Marca jogo como confirmado finalizado/suspenso/cancelado/postponed.

        Watchlist exclui esses jogos por TTL longo (12h por padrão) — evita
        reescaneá-los a cada ciclo quando o Flashscore continua listando-os
        no índice ao vivo.
        """
        entry = self._games.get(match_id)
        if entry is None:
            return
        now = datetime.now(timezone.utc)
        entry["finished_or_not_live"] = True
        entry["finished_or_not_live_at"] = now.isoformat()
        entry["finished_or_not_live_until"] = (
            now + timedelta(hours=ttl_hours)
        ).isoformat()
        entry["not_live_reason"] = str(reason or "")

    def is_finished_or_not_live_active(self, match_id: str,
                                        now: Optional[datetime] = None) -> bool:
        """True se o jogo está marcado como finalizado E o TTL não expirou."""
        entry = self._games.get(match_id)
        if not entry:
            return False
        if not entry.get("finished_or_not_live"):
            return False
        until = entry.get("finished_or_not_live_until")
        if not until:
            # Sem TTL — interpretamos como marcação permanente (no dia)
            return True
        ts = _parse_iso(until)
        if ts is None:
            return True
        now = now or datetime.now(timezone.utc)
        return now < ts

    def count_finished_or_not_live(self, now: Optional[datetime] = None) -> int:
        """Total de jogos no catálogo com TTL de finished_or_not_live ativo."""
        now = now or datetime.now(timezone.utc)
        return sum(1 for mid in self._games
                   if self.is_finished_or_not_live_active(mid, now=now))

    def prune_stale_entries(self, *,
                              not_seen_ttl_minutes: int = 30,
                              finished_ttl_hours: int = 12,
                              now: Optional[datetime] = None) -> dict:
        """Remove entradas mortas do catálogo para evitar saturação do Tier 3.

        Critérios de remoção (TODOS devem ser true):
          1. last_seen_at > not_seen_ttl_minutes atrás (discovery não vê mais)
             OU está finished há mais de finished_ttl_hours
          2. has_open_position == False (jogos com posição aberta NUNCA removem)
          3. Sem sinal ENTER recente (last_signal_minute deve estar antigo)

        Returns:
            dict com estatísticas: {'removed': N, 'kept': N, 'reason_counts': {...}}
        """
        now = now or datetime.now(timezone.utc)
        not_seen_threshold = now - timedelta(minutes=not_seen_ttl_minutes)
        finished_threshold = now - timedelta(hours=finished_ttl_hours)

        to_remove = []
        reason_counts = {"not_seen": 0, "finished_long_ago": 0}

        for mid, g in list(self._games.items()):
            # NUNCA remove jogo com posição aberta
            if g.get("has_open_position"):
                continue

            last_seen_str = g.get("last_seen_at") or g.get("first_seen_at") or ""
            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00")) \
                    if last_seen_str else None
            except (ValueError, AttributeError):
                last_seen = None

            # Critério A: não visto no discovery há muito tempo
            if last_seen and last_seen < not_seen_threshold:
                to_remove.append(mid)
                reason_counts["not_seen"] += 1
                continue

            # Critério B: marcado como finished há muito tempo (não é redundante
            # com TTL próprio do finished — esse remove DEFINITIVO do catálogo)
            finished_until_str = g.get("finished_or_not_live_until") or ""
            if finished_until_str:
                try:
                    finished_until = datetime.fromisoformat(
                        finished_until_str.replace("Z", "+00:00"))
                    # Se o TTL já passou + finished_threshold, podemos remover
                    if finished_until < finished_threshold:
                        to_remove.append(mid)
                        reason_counts["finished_long_ago"] += 1
                        continue
                except (ValueError, AttributeError):
                    pass

        for mid in to_remove:
            del self._games[mid]

        return {
            "removed": len(to_remove),
            "kept": len(self._games),
            "reason_counts": reason_counts,
        }
