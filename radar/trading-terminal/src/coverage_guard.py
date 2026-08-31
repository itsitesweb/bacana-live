"""
LIVE COVERAGE GUARD — auditoria automática de cobertura por ciclo (v2.4).

Objetivo:
  Detectar AUTOMATICAMENTE qualquer jogo que o discovery do Flashscore viu
  como ao vivo, mas que está fora da operação por bloqueio indevido, ausência
  de scan recente ou marcação errada de finished_or_not_live.

  Tiago não pode depender de olhar o Flashscore manualmente — o guard precisa
  achar e recuperar esses casos sozinho a cada ciclo.

Módulo PURO (sem efeitos colaterais externos): recebe o catálogo, a lista
de discovered live games, a watchlist e o instante do ciclo. Retorna um
CoverageReport com estatísticas, erros, jogos recuperados e mensagens
de Telegram crítico. As mutações no Catalog acontecem dentro do guard
via setters do próprio Catalog — explícitas e auditáveis.

NÃO toca:
  - Regra 3.1.2.0 / decisão / Telegram da regra
  - Anti-spam da regra
  - Supervisor / scraping / discovery
  - Premium A/B/C classification
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


# ─── Constantes ────────────────────────────────────────────────────────

# Motivos "fracos" — leituras inconclusivas que NÃO devem manter um jogo
# bloqueado por 12h quando o discovery continua vendo o mesmo jogo ao vivo.
WEAK_NOT_LIVE_REASONS = frozenset({
    "INVALID_MINUTE_STATUS",
    "AMBIGUOUS_MINUTE_STATUS",
})

# Sinais STRONG do filtro is_live_match. Esses NUNCA são revertidos pelo
# guard — se status_raw textualmente disse "Encerrado" / "Após Pênaltis" /
# "Suspenso" / "Adiado", confiamos no Flashscore.
STRONG_NOT_LIVE_REASONS = frozenset({
    "FINISHED_MATCH",
    "NOT_LIVE_STATUS",
})

# Janelas operacionais (em segundos)
DEFAULT_PREMIUM_A_SCAN_WINDOW_S = 180   # premium A deve scanar em <= 180s
DEFAULT_NON_PREMIUM_WARN_WINDOW_S = 480  # não-premium warn após 8min
DEFAULT_PREMIUM_A_MAX_BACKOFF_S = 180   # backoff premium A nunca > 3min

# Severidades
SEV_INFO     = "INFO"
SEV_WARN     = "WARN"
SEV_ERROR    = "ERROR"
SEV_CRITICAL = "CRITICAL"

# Tipos de evento (constantes)
COVERAGE_ERROR_DISCOVERED_NOT_CATALOGED  = "COVERAGE_ERROR_DISCOVERED_NOT_CATALOGED"
COVERAGE_ERROR_LIVE_MARKED_FINISHED       = "COVERAGE_ERROR_LIVE_MARKED_FINISHED"
COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST = "COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST"
COVERAGE_WARN_NON_PREMIUM_NOT_SCANNED     = "COVERAGE_WARN_NON_PREMIUM_NOT_SCANNED"
COVERAGE_AUTO_RECOVERED_LIVE_GAME         = "COVERAGE_AUTO_RECOVERED_LIVE_GAME"
COVERAGE_PREMIUM_A_BACKOFF_CAPPED         = "COVERAGE_PREMIUM_A_BACKOFF_CAPPED"


# ─── Data classes ──────────────────────────────────────────────────────

@dataclass
class CoverageEvent:
    """Um evento detectado pelo guard durante um ciclo."""
    severity: str
    event_type: str
    match_id: str
    home: str = ""
    away: str = ""
    league: str = ""
    country: str = ""
    reason_before: str = ""
    action_taken: str = ""
    reason_after: str = ""
    seconds_since_last_scan: Optional[int] = None
    premium_level: str = ""

    def as_log_dict(self, ts_iso: str) -> dict:
        return {
            "timestamp": ts_iso,
            "severity": self.severity,
            "event_type": self.event_type,
            "match_id": self.match_id,
            "home": self.home,
            "away": self.away,
            "league": self.league,
            "country": self.country,
            "reason_before": self.reason_before,
            "action_taken": self.action_taken,
            "reason_after": self.reason_after,
            "seconds_since_last_scan": self.seconds_since_last_scan,
            "premium_level": self.premium_level,
        }


@dataclass
class CoverageReport:
    """Saída do guard por ciclo."""
    stats: dict                         = field(default_factory=dict)
    events: list                        = field(default_factory=list)
    recovered_match_ids: list           = field(default_factory=list)
    telegram_critical: list             = field(default_factory=list)

    def error_count(self) -> int:
        return sum(1 for e in self.events
                   if e.severity in (SEV_ERROR, SEV_CRITICAL))

    def warn_count(self) -> int:
        return sum(1 for e in self.events if e.severity == SEV_WARN)


# ─── Helpers ───────────────────────────────────────────────────────────

def _parse_iso(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def _seconds_since(ts_iso: Optional[str], now: datetime) -> Optional[int]:
    ts = _parse_iso(ts_iso)
    if ts is None:
        return None
    return int((now - ts).total_seconds())


def _league_label(entry: dict) -> tuple:
    return ((entry.get("premium_league_name") or "").strip(),
            (entry.get("premium_country") or "").strip())


def _home_away_from_url(url: str) -> tuple:
    """Extrai (home_slug, away_slug) da URL — só pra display."""
    import re
    m = re.search(r"/jogo/futebol/([a-z0-9-]+)-[A-Za-z0-9]{6,}/([a-z0-9-]+)-[A-Za-z0-9]{6,}",
                   url or "", re.IGNORECASE)
    if not m:
        return ("?", "?")
    return (m.group(1).replace("-", " ").title(),
            m.group(2).replace("-", " ").title())


# ─── Função principal ─────────────────────────────────────────────────

def run_coverage_guard(*,
                       catalog,
                       discovered_live_ids: set,
                       watchlist_ids: set,
                       now: Optional[datetime] = None,
                       premium_a_scan_window_s: int = DEFAULT_PREMIUM_A_SCAN_WINDOW_S,
                       non_premium_warn_window_s: int = DEFAULT_NON_PREMIUM_WARN_WINDOW_S,
                       max_premium_a_backoff_s: int = DEFAULT_PREMIUM_A_MAX_BACKOFF_S,
                       dry_run: bool = False) -> CoverageReport:
    """Executa a auditoria de cobertura do ciclo atual.

    Args:
        catalog: instância de Catalog.
        discovered_live_ids: set de match_ids que o discovery do Flashscore
            VIU como ao vivo neste ciclo (ground truth).
        watchlist_ids: set de match_ids que entraram na watchlist final.
        now: instante de referência (default = utcnow).
        premium_a_scan_window_s: janela máxima entre discovery e scan para
            jogos premium A (default 180s).
        non_premium_warn_window_s: janela de warn pra jogos não-premium
            (default 480s = 8min).
        max_premium_a_backoff_s: backoff máximo permitido para premium A em
            no_stats_backoff (default 180s).
        dry_run: se True, NÃO aplica mutações no catálogo (só relatório).

    Returns:
        CoverageReport com stats, events, recovered_match_ids, telegram_critical.
    """
    now = now or datetime.now(timezone.utc)
    report = CoverageReport()
    report.stats = {
        "live_discovered": len(discovered_live_ids),
        "cataloged": 0,
        "eligible": 0,
        "scanned_this_cycle": 0,
        "blocked_finished": 0,
        "blocked_no_stats": 0,
        "recovered_live_games": 0,
        "premium_a_recovered": 0,
        "premium_a_backoff_capped": 0,
        "coverage_errors": 0,
        "coverage_warnings": 0,
    }

    # ─── Regra 1: todo discovered_live deve existir no catálogo ──────
    cataloged = 0
    for mid in discovered_live_ids:
        if catalog.get(mid) is None:
            report.events.append(CoverageEvent(
                severity=SEV_ERROR,
                event_type=COVERAGE_ERROR_DISCOVERED_NOT_CATALOGED,
                match_id=mid,
                reason_before="not_in_catalog",
                action_taken="none (caller deve fazer upsert_discovered)",
                reason_after="not_in_catalog",
            ))
            continue
        cataloged += 1
    report.stats["cataloged"] = cataloged

    # ─── Regras 4, 5, 6: jogos discovered+live com finished_or_not_live
    # por motivo FRACO → recuperar automaticamente ──────────────────
    for mid in discovered_live_ids:
        entry = catalog.get(mid)
        if entry is None:
            continue
        if not entry.get("finished_or_not_live"):
            continue
        # Se TTL já expirou, deixar o catalog cuidar naturalmente
        if not catalog.is_finished_or_not_live_active(mid, now):
            continue

        reason = entry.get("not_live_reason", "")
        is_weak = reason in WEAK_NOT_LIVE_REASONS
        is_strong = reason in STRONG_NOT_LIVE_REASONS
        league, country = _league_label(entry)
        home, away = _home_away_from_url(entry.get("url", ""))
        prem_level = entry.get("premium_level", "NONE")
        is_premium_a = (prem_level == "A")

        if is_strong:
            # Status forte (TERMINADO/Suspenso/etc.) — não tocamos. Mas
            # registramos um INFO se discovery viu como live (divergência).
            report.events.append(CoverageEvent(
                severity=SEV_INFO,
                event_type=COVERAGE_ERROR_LIVE_MARKED_FINISHED,
                match_id=mid, home=home, away=away,
                league=league, country=country,
                reason_before=reason,
                action_taken="no_recover (status forte confiável)",
                reason_after=reason,
                premium_level=prem_level,
            ))
            continue

        if is_weak or not reason:
            # Recover: discovery viu live, mas entry está bloqueado por
            # motivo fraco/sem motivo. Limpa flags.
            severity = SEV_CRITICAL if is_premium_a else SEV_ERROR
            event = CoverageEvent(
                severity=severity,
                event_type=COVERAGE_AUTO_RECOVERED_LIVE_GAME,
                match_id=mid, home=home, away=away,
                league=league, country=country,
                reason_before=reason or "(vazio)",
                action_taken="cleared finished_or_not_live; flag recovered_by_coverage_guard=True",
                reason_after="",
                premium_level=prem_level,
            )
            if not dry_run:
                entry["finished_or_not_live"] = False
                entry["finished_or_not_live_at"] = None
                entry["finished_or_not_live_until"] = None
                entry["not_live_reason"] = ""
                entry["recovered_by_coverage_guard"] = True
                entry["recovered_at"] = now.isoformat()
                entry["recovered_reason_before"] = reason or "(vazio)"
            report.events.append(event)
            report.recovered_match_ids.append(mid)
            report.stats["recovered_live_games"] += 1
            if is_premium_a:
                report.stats["premium_a_recovered"] += 1
                # Telegram crítico só pra premium A recuperado
                report.telegram_critical.append({
                    "title": "🚨 COVERAGE GUARD — JOGO AO VIVO RECUPERADO",
                    "match_id": mid,
                    "home": home, "away": away,
                    "league": league, "country": country,
                    "reason_before": reason or "(vazio)",
                    "premium_level": prem_level,
                })

    # ─── Regra 2/3: jogos premium A live não scanados em <= 180s ──────
    # Regra 3: warn pra não-premium não scanado em <= 8min.
    for mid in discovered_live_ids:
        entry = catalog.get(mid)
        if entry is None:
            continue
        # Pula entries que foram recovered neste ciclo (ainda dão tempo de
        # ser scaneados no próximo)
        if mid in report.recovered_match_ids:
            continue
        # Pula entries que continuam bloqueados (strong reason)
        if catalog.is_finished_or_not_live_active(mid, now):
            continue

        prem_level = entry.get("premium_level", "NONE")
        is_premium_a = (prem_level == "A")
        league, country = _league_label(entry)
        home, away = _home_away_from_url(entry.get("url", ""))
        sec_since_scan = _seconds_since(entry.get("last_scanned_at"), now)
        sec_since_first_seen = _seconds_since(entry.get("first_seen_at"), now)

        # Se o jogo é novo (first_seen < 30s atrás), ainda é cedo pra cobrar scan
        if sec_since_first_seen is not None and sec_since_first_seen < 30:
            continue

        # Premium A precisa de scan rápido
        if is_premium_a:
            window_violated = (sec_since_scan is None
                                or sec_since_scan > premium_a_scan_window_s)
            if window_violated:
                report.events.append(CoverageEvent(
                    severity=SEV_ERROR,
                    event_type=COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST,
                    match_id=mid, home=home, away=away,
                    league=league, country=country,
                    reason_before=("never_scanned" if sec_since_scan is None
                                    else f"last_scan_{sec_since_scan}s_ago"),
                    action_taken="flag para retry prioritário no próximo ciclo",
                    reason_after="awaiting_retry",
                    seconds_since_last_scan=sec_since_scan,
                    premium_level=prem_level,
                ))
                report.telegram_critical.append({
                    "title": "🚨 COVERAGE GUARD — PREMIUM A SEM SCAN",
                    "match_id": mid,
                    "home": home, "away": away,
                    "league": league, "country": country,
                    "reason_before": (f"sem scan há {sec_since_scan}s"
                                       if sec_since_scan else "nunca scaneado"),
                    "premium_level": prem_level,
                })
        else:
            # Não premium A — warn se >8min
            if sec_since_scan is not None and sec_since_scan > non_premium_warn_window_s:
                report.events.append(CoverageEvent(
                    severity=SEV_WARN,
                    event_type=COVERAGE_WARN_NON_PREMIUM_NOT_SCANNED,
                    match_id=mid, home=home, away=away,
                    league=league, country=country,
                    reason_before=f"last_scan_{sec_since_scan}s_ago",
                    action_taken="warn only (não-premium)",
                    reason_after=f"last_scan_{sec_since_scan}s_ago",
                    seconds_since_last_scan=sec_since_scan,
                    premium_level=prem_level,
                ))

    # ─── Regra 7: cap backoff premium A em max_premium_a_backoff_s ───
    for mid in discovered_live_ids:
        entry = catalog.get(mid)
        if entry is None or entry.get("premium_level") != "A":
            continue
        until_str = entry.get("no_stats_until")
        if not until_str:
            continue
        until = _parse_iso(until_str)
        if until is None:
            continue
        # Quanto falta?
        remaining_s = int((until - now).total_seconds())
        if remaining_s <= max_premium_a_backoff_s:
            continue
        # Backoff muito longo para premium A — cap.
        league, country = _league_label(entry)
        home, away = _home_away_from_url(entry.get("url", ""))
        new_until = (now + timedelta(seconds=max_premium_a_backoff_s)).isoformat()
        if not dry_run:
            entry["no_stats_until"] = new_until
        report.events.append(CoverageEvent(
            severity=SEV_WARN,
            event_type=COVERAGE_PREMIUM_A_BACKOFF_CAPPED,
            match_id=mid, home=home, away=away,
            league=league, country=country,
            reason_before=f"backoff até {until_str} ({remaining_s}s restantes)",
            action_taken=f"cap em {max_premium_a_backoff_s}s",
            reason_after=f"backoff até {new_until}",
            premium_level="A",
        ))
        report.stats["premium_a_backoff_capped"] += 1

    # ─── Sumário ──────────────────────────────────────────────────────
    eligible = 0
    scanned_this_cycle = 0
    blocked_finished = 0
    blocked_no_stats = 0
    for mid in discovered_live_ids:
        entry = catalog.get(mid)
        if entry is None:
            continue
        if catalog.is_finished_or_not_live_active(mid, now):
            blocked_finished += 1
            continue
        if catalog.is_no_stats_active(mid, now):
            blocked_no_stats += 1
        # Eligibility: catalog tem ele E não está em hard block
        eligible += 1
        # Scanned this cycle? — usa last_scanned_at >= now - 60s como proxy
        ts = _parse_iso(entry.get("last_scanned_at"))
        if ts is not None and (now - ts).total_seconds() < 60:
            scanned_this_cycle += 1

    report.stats["eligible"] = eligible
    report.stats["scanned_this_cycle"] = scanned_this_cycle
    report.stats["blocked_finished"] = blocked_finished
    report.stats["blocked_no_stats"] = blocked_no_stats
    report.stats["coverage_errors"] = report.error_count()
    report.stats["coverage_warnings"] = report.warn_count()

    return report


# ─── Render do display do terminal ─────────────────────────────────────

def format_terminal_summary(report: CoverageReport) -> str:
    """Formata o relatório por ciclo pra exibição no terminal."""
    s = report.stats
    lines = []
    lines.append("📡 COVERAGE GUARD")
    lines.append(f"   live_discovered: {s.get('live_discovered', 0)}")
    lines.append(f"   cataloged: {s.get('cataloged', 0)}")
    lines.append(f"   eligible: {s.get('eligible', 0)}")
    lines.append(f"   scanned_this_cycle: {s.get('scanned_this_cycle', 0)}")
    lines.append(f"   blocked_finished: {s.get('blocked_finished', 0)}")
    lines.append(f"   blocked_no_stats: {s.get('blocked_no_stats', 0)}")
    lines.append(f"   recovered_live_games: {s.get('recovered_live_games', 0)}")
    lines.append(f"   coverage_errors: {s.get('coverage_errors', 0)}")
    if s.get("coverage_warnings", 0) > 0:
        lines.append(f"   coverage_warnings: {s.get('coverage_warnings', 0)}")
    return "\n".join(lines)


def format_critical_event(ev: CoverageEvent) -> str:
    """Linha pra display de erro crítico no terminal."""
    home_away = f"{ev.home} x {ev.away}".strip(" x")
    if not home_away or home_away == "? x ?":
        home_away = ev.match_id
    league_part = f"{ev.league} | {ev.country}" if ev.league else ""
    return (
        "🚨 COVERAGE ERROR — JOGO AO VIVO FORA DA OPERAÇÃO\n"
        f"   Jogo:    {home_away}"
        + (f"  ({league_part})" if league_part else "") + "\n"
        f"   Motivo:  {ev.reason_before}\n"
        f"   Ação:    {ev.action_taken}\n"
        f"   Status:  {ev.reason_after}"
    )


def format_telegram_message(tg_item: dict) -> str:
    """Texto pronto para envio via Telegram."""
    lines = [tg_item["title"], ""]
    home_away = f"{tg_item.get('home','?')} x {tg_item.get('away','?')}"
    lines.append(f"Jogo:    {home_away}")
    league = tg_item.get("league", "")
    if league:
        country = tg_item.get("country", "")
        lines.append(f"Liga:    {league}"
                      + (f"  ({country})" if country else ""))
    lines.append(f"Motivo:  estava marcado como finished_or_not_live por "
                  f"{tg_item.get('reason_before', '?')}")
    lines.append("Ação:    flag removida, jogo voltou para elegibilidade/watchlist")
    lines.append("Status:  monitoramento retomado")
    return "\n".join(lines)


# ─── Persistência JSONL ────────────────────────────────────────────────

def append_to_jsonl(path, report: CoverageReport,
                     now: Optional[datetime] = None) -> int:
    """Anexa cada evento do relatório em logs/live_coverage_guard.jsonl.

    Returns:
        número de linhas anexadas.
    """
    import json
    from pathlib import Path
    now = now or datetime.now(timezone.utc)
    ts_iso = now.isoformat()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(p, "a", encoding="utf-8") as f:
        for ev in report.events:
            f.write(json.dumps(ev.as_log_dict(ts_iso), ensure_ascii=False) + "\n")
            count += 1
    return count
