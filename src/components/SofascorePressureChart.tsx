import React, { useState, useMemo } from "react";
import { Match, MatchEvent, MomentumPoint } from "../types";
import { Shield, Sparkles, Zap, Flame, Info, Filter, ArrowUpRight, ArrowDownRight } from "lucide-react";

interface SofascorePressureChartProps {
  match: Match;
  className?: string;
  showControls?: boolean;
}

// Reusable Team Shield Badge component with full image, emoji, and crest fallback support
export function TeamShieldBadge({
  team,
  isHome,
  size = "md",
}: {
  team: { name: string; shortName: string; logo?: string; color?: string };
  isHome: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const [imgError, setImgError] = useState(false);
  const isUrl =
    Boolean(team.logo) &&
    !imgError &&
    (team.logo!.startsWith("http") ||
      team.logo!.startsWith("/") ||
      team.logo!.startsWith("data:image"));

  const sizeClasses =
    size === "sm"
      ? "w-6 h-6 text-[10px]"
      : size === "lg"
      ? "w-10 h-10 text-sm"
      : "w-8 h-8 text-xs";

  const primaryColor = team.color || (isHome ? "#2563eb" : "#ea580c");

  return (
    <div
      className={`${sizeClasses} rounded-full flex items-center justify-center font-black shadow-sm border-2 overflow-hidden shrink-0 transition-transform`}
      style={{
        borderColor: primaryColor,
        backgroundColor: isHome ? "#eff6ff" : "#fff7ed",
      }}
    >
      {isUrl ? (
        <img
          src={team.logo}
          alt={team.shortName || team.name}
          className="w-full h-full object-cover"
          referrerPolicy="no-referrer"
          onError={() => setImgError(true)}
        />
      ) : team.logo && team.logo.length <= 6 && /[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}]/u.test(team.logo) ? (
        <span className="leading-none text-xs sm:text-sm select-none">{team.logo}</span>
      ) : (
        <div
          className="w-full h-full flex items-center justify-center text-white font-extrabold uppercase tracking-tight text-[11px]"
          style={{ backgroundColor: primaryColor }}
        >
          {team.shortName ? team.shortName.slice(0, 3) : team.name.slice(0, 3)}
        </div>
      )}
    </div>
  );
}

export function SofascorePressureChart({ match, className = "", showControls = true }: SofascorePressureChartProps) {
  const [hoveredMinute, setHoveredMinute] = useState<number | null>(null);
  const [metricMode, setMetricMode] = useState<"pressure" | "dangerous_attacks" | "xg">("pressure");
  const [selectedEvent, setSelectedEvent] = useState<MatchEvent | null>(null);

  const timeline = match.momentumTimeline || [];
  const events = match.events || [];
  const stats = match.stats;

  // Build a normalized 1-90 timeline with exact minute points
  const fullTimeline = useMemo(() => {
    const map = new Map<number, MomentumPoint>();
    timeline.forEach((pt) => map.set(pt.minute, pt));

    const result: Array<{
      minute: number;
      homeVal: number; // 0 to 100
      awayVal: number; // 0 to 100
      homeRaw: number;
      awayRaw: number;
      homeDangerous: boolean;
      awayDangerous: boolean;
      homeShot: boolean;
      awayShot: boolean;
      events: MatchEvent[];
    }> = [];

    for (let m = 1; m <= 90; m++) {
      const existing = map.get(m);
      const minEvents = events.filter((e) => e.minute === m);
      const isPlayed = m <= match.minute || match.status === "FT";

      if (!isPlayed) {
        result.push({
          minute: m,
          homeVal: 0,
          awayVal: 0,
          homeRaw: 0,
          awayRaw: 0,
          homeDangerous: false,
          awayDangerous: false,
          homeShot: false,
          awayShot: false,
          events: minEvents,
        });
        continue;
      }

      let homePressure = existing?.homePressure ?? 50;
      let awayPressure = existing?.awayPressure ?? 50;
      const homeDang = !!existing?.homeDangerousAttack;
      const awayDang = !!existing?.awayDangerousAttack;
      const homeShot = !!existing?.homeShot;
      const awayShot = !!existing?.awayShot;

      // Metric adjustment
      let homeHeight = 0;
      let awayHeight = 0;

      if (metricMode === "pressure") {
        const homeBoost = homeDang ? 25 : homeShot ? 15 : 0;
        const awayBoost = awayDang ? 25 : awayShot ? 15 : 0;
        homeHeight = Math.min(100, Math.max(8, homePressure * 0.9 + homeBoost));
        awayHeight = Math.min(100, Math.max(8, awayPressure * 0.9 + awayBoost));

        if (homeHeight > 65) awayHeight = Math.max(5, awayHeight * 0.4);
        if (awayHeight > 65) homeHeight = Math.max(5, homeHeight * 0.4);
      } else if (metricMode === "dangerous_attacks") {
        homeHeight = homeDang ? 90 : homeShot ? 60 : Math.max(0, homePressure - 40);
        awayHeight = awayDang ? 90 : awayShot ? 60 : Math.max(0, awayPressure - 40);
      } else if (metricMode === "xg") {
        const homeXgStep = homeShot ? (stats.xG.home > 0 ? 70 : 40) : homeDang ? 30 : 5;
        const awayXgStep = awayShot ? (stats.xG.away > 0 ? 70 : 40) : awayDang ? 30 : 5;
        homeHeight = homeXgStep;
        awayHeight = awayXgStep;
      }

      result.push({
        minute: m,
        homeVal: homeHeight,
        awayVal: awayHeight,
        homeRaw: homePressure,
        awayRaw: awayPressure,
        homeDangerous: homeDang,
        awayDangerous: awayDang,
        homeShot,
        awayShot,
        events: minEvents,
      });
    }

    return result;
  }, [timeline, events, match.minute, match.status, metricMode, stats.xG]);

  const firstHalfData = useMemo(() => fullTimeline.slice(0, 45), [fullTimeline]);
  const secondHalfData = useMemo(() => fullTimeline.slice(45, 90), [fullTimeline]);

  // Events grouped for 1H and 2H
  const firstHalfEvents = useMemo(() => events.filter((e) => e.minute <= 45), [events]);
  const secondHalfEvents = useMemo(() => events.filter((e) => e.minute > 45 && e.minute <= 90), [events]);

  // Summary statistics for 1T and 2T
  const halfStats = useMemo(() => {
    const h1HomeBars = firstHalfData.filter((d) => d.minute <= match.minute && d.homeVal > d.awayVal);
    const h1AwayBars = firstHalfData.filter((d) => d.minute <= match.minute && d.awayVal > d.homeVal);
    const h2HomeBars = secondHalfData.filter((d) => d.minute <= match.minute && d.homeVal > d.awayVal);
    const h2AwayBars = secondHalfData.filter((d) => d.minute <= match.minute && d.awayVal > d.homeVal);

    const total1HPlayed = Math.min(45, match.minute);
    const total2HPlayed = Math.max(0, match.minute - 45);

    return {
      h1HomeDom: total1HPlayed > 0 ? Math.round((h1HomeBars.length / total1HPlayed) * 100) : 50,
      h1AwayDom: total1HPlayed > 0 ? Math.round((h1AwayBars.length / total1HPlayed) * 100) : 50,
      h2HomeDom: total2HPlayed > 0 ? Math.round((h2HomeBars.length / total2HPlayed) * 100) : 50,
      h2AwayDom: total2HPlayed > 0 ? Math.round((h2AwayBars.length / total2HPlayed) * 100) : 50,
    };
  }, [firstHalfData, secondHalfData, match.minute]);

  const hoveredDataPoint = hoveredMinute ? fullTimeline.find((d) => d.minute === hoveredMinute) : null;

  // Render event badge at top or bottom edge
  const renderEventBadge = (event: MatchEvent, halfStartMin: number) => {
    const relMin = event.minute - halfStartMin; // 0 to 44
    const leftPercent = Math.min(97, Math.max(3, (relMin / 44) * 100));
    const isHome = event.team === "home";

    return (
      <button
        key={event.id || `${event.type}-${event.minute}-${event.team}`}
        onClick={(e) => {
          e.stopPropagation();
          setSelectedEvent(event);
        }}
        className={`absolute -translate-x-1/2 z-30 transition-transform hover:scale-125 focus:outline-none ${
          isHome ? "-top-3.5" : "-bottom-3.5"
        }`}
        style={{ left: `${leftPercent}%` }}
        title={`${event.type.toUpperCase()}: ${event.player || match[isHome ? 'homeTeam' : 'awayTeam'].name} (${event.minute}')`}
      >
        {event.type === "goal" ? (
          <div className="w-6 h-6 rounded-full bg-white dark:bg-slate-900 border-2 border-emerald-500 shadow-md flex items-center justify-center text-xs ring-2 ring-emerald-500/20">
            <span className="text-[12px] leading-none select-none">⚽</span>
          </div>
        ) : event.type === "yellow_card" ? (
          <div className="w-3.5 h-5 rounded-[3px] bg-amber-400 border border-amber-600 shadow-md flex items-center justify-center ring-2 ring-amber-400/20">
            <div className="w-2 h-3.5 bg-amber-300 rounded-[1px]" />
          </div>
        ) : event.type === "red_card" ? (
          <div className="w-3.5 h-5 rounded-[3px] bg-rose-600 border border-rose-800 shadow-md flex items-center justify-center ring-2 ring-rose-600/20">
            <div className="w-2 h-3.5 bg-rose-500 rounded-[1px]" />
          </div>
        ) : event.type === "sub" ? (
          <div className="w-5 h-5 rounded-full bg-slate-800 border border-slate-600 text-slate-300 shadow flex items-center justify-center text-[10px]">
            🔄
          </div>
        ) : (
          <div className="w-5 h-5 rounded-full bg-amber-500 text-black border border-amber-600 shadow flex items-center justify-center text-[10px] font-bold">
            ⚡
          </div>
        )}
      </button>
    );
  };

  // Render a half container (1st Half or 2nd Half)
  const renderHalfCard = (data: typeof firstHalfData, halfEvents: MatchEvent[], halfNum: 1 | 2) => {
    const halfStartMin = halfNum === 1 ? 1 : 46;
    const isHalfActive = (halfNum === 1 && match.minute >= 1) || (halfNum === 2 && match.minute >= 46) || match.status === "FT";
    const isCurrentHalf = (halfNum === 1 && match.minute <= 45 && match.status !== "FT") || (halfNum === 2 && match.minute > 45 && match.status !== "FT");

    return (
      <div className="relative flex-1 flex flex-col">
        {/* Outer Bicolor Box: Exactly 50% Top Blue & 50% Bottom Sand */}
        <div className="relative w-full h-44 rounded-2xl border border-slate-300 dark:border-slate-800 shadow-sm overflow-hidden flex flex-col select-none cursor-crosshair">
          {/* Top Half Background (Pale Blue) */}
          <div className="relative w-full h-1/2 bg-[#e9f2fe] dark:bg-blue-950/30 flex items-end">
            {/* Half title badge */}
            <div className="absolute top-1.5 right-2.5 z-10 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-900/80 px-2 py-0.5 rounded-full backdrop-blur-xs border border-slate-200 dark:border-slate-800">
              <span>{halfNum}º Tempo</span>
              <span className="text-slate-400 font-mono">({halfNum === 1 ? "1'-45'" : "46'-90'"})</span>
              {isCurrentHalf && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
              )}
            </div>
          </div>

          {/* Central Baseline Dividing Line (Crisp separator) */}
          <div className="w-full h-[1.5px] bg-slate-300 dark:bg-slate-600/90 shrink-0 z-10 pointer-events-none" />

          {/* Bottom Half Background (Pale Sand / Amber) */}
          <div className="relative w-full h-1/2 bg-[#faebd7] dark:bg-amber-950/25 flex items-start" />

          {/* Overlaid Bars Container: Exact match with baseline */}
          <div
            className="absolute inset-0 z-20 flex items-stretch justify-between px-1.5 sm:px-2.5"
            onMouseLeave={() => setHoveredMinute(null)}
          >
            {/* Live minute hairline */}
            {isCurrentHalf && match.minute >= halfStartMin && match.minute < halfStartMin + 45 && (
              <div
                className="absolute top-0 bottom-0 w-[2px] bg-emerald-500 z-30 pointer-events-none animate-pulse"
                style={{
                  left: `${((match.minute - halfStartMin) / 44) * 100}%`,
                }}
              >
                <div className="absolute -top-1 -translate-x-1/2 px-1 py-0.5 bg-emerald-600 text-[9px] font-black text-white rounded font-mono shadow">
                  {match.minute}'
                </div>
              </div>
            )}

            {/* Hover hairline */}
            {hoveredMinute && hoveredMinute >= halfStartMin && hoveredMinute < halfStartMin + 45 && (
              <div
                className="absolute top-0 bottom-0 w-[1.5px] bg-blue-600 dark:bg-blue-400 z-30 pointer-events-none"
                style={{
                  left: `${((hoveredMinute - halfStartMin) / 44) * 100}%`,
                }}
              />
            )}

            {/* 45 Minute Columns */}
            {data.map((pt) => {
              const isPlayed = pt.minute <= match.minute || match.status === "FT";
              const isHovered = hoveredMinute === pt.minute;

              // Height percentages (0 to 92% max of the half-card)
              const homeHeightPct = isPlayed ? Math.max(0, Math.min(92, (pt.homeVal / 100) * 92)) : 0;
              const awayHeightPct = isPlayed ? Math.max(0, Math.min(92, (pt.awayVal / 100) * 92)) : 0;

              return (
                <div
                  key={pt.minute}
                  onMouseEnter={() => setHoveredMinute(pt.minute)}
                  className="relative flex-1 h-full flex flex-col items-center group"
                >
                  {/* Top Cell (Home Team): Bars grow UPWARDS from central baseline */}
                  <div className="w-full h-1/2 flex items-end justify-center pb-[1px]">
                    {isPlayed && homeHeightPct > 0 && (
                      <div
                        className={`w-[2.5px] sm:w-[3.5px] md:w-[4px] rounded-t-[1.5px] transition-all ${
                          isHovered
                            ? "bg-blue-700 dark:bg-blue-300 shadow-md scale-110"
                            : pt.homeDangerous
                            ? "bg-[#1d4ed8] shadow-xs"
                            : "bg-[#2563eb]"
                        }`}
                        style={{ height: `${homeHeightPct}%` }}
                      />
                    )}
                  </div>

                  {/* Bottom Cell (Away Team): Bars grow DOWNWARDS from central baseline */}
                  <div className="w-full h-1/2 flex items-start justify-center pt-[1px]">
                    {isPlayed && awayHeightPct > 0 && (
                      <div
                        className={`w-[2.5px] sm:w-[3.5px] md:w-[4px] rounded-b-[1.5px] transition-all ${
                          isHovered
                            ? "bg-amber-600 dark:bg-amber-400 shadow-md scale-110"
                            : pt.awayDangerous
                            ? "bg-[#c2410c] shadow-xs"
                            : "bg-[#ea580c]"
                        }`}
                        style={{ height: `${awayHeightPct}%` }}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Event Badges on Top Edge (Home Events) */}
          {halfEvents
            .filter((e) => e.team === "home")
            .map((e) => renderEventBadge(e, halfStartMin))}

          {/* Event Badges on Bottom Edge (Away Events) */}
          {halfEvents
            .filter((e) => e.team === "away")
            .map((e) => renderEventBadge(e, halfStartMin))}
        </div>

        {/* Minute Grid Axis Labels Below Card */}
        <div className="flex justify-between items-center px-2 py-1 text-[10px] font-mono text-slate-500 dark:text-slate-400">
          <span>{halfStartMin}'</span>
          <span>{halfStartMin + 15}'</span>
          <span>{halfStartMin + 30}'</span>
          <span>{halfStartMin + 44}'</span>
        </div>
      </div>
    );
  };

  return (
    <div className={`bg-white dark:bg-slate-900/95 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-lg space-y-4 ${className}`}>
      {/* Top Header & Mode Filter */}
      {showControls && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
              <Flame className="w-5 h-5" />
            </span>
            <div>
              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                Gráfico de Pressão & Momentum Sofascore
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-extrabold uppercase">
                  1T & 2T Separados
                </span>
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Barras azuis apontando para cima ({match.homeTeam.name}) e barras laranjas para baixo ({match.awayTeam.name}).
              </p>
            </div>
          </div>

          {/* Metric Selector Buttons */}
          <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-950 p-1 rounded-xl border border-slate-200 dark:border-slate-800 self-start sm:self-auto">
            <button
              onClick={() => setMetricMode("pressure")}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                metricMode === "pressure"
                  ? "bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-xs"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Pressão Geral
            </button>
            <button
              onClick={() => setMetricMode("dangerous_attacks")}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                metricMode === "dangerous_attacks"
                  ? "bg-white dark:bg-slate-800 text-amber-600 dark:text-amber-400 shadow-xs"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Ataques Perigosos
            </button>
            <button
              onClick={() => setMetricMode("xg")}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                metricMode === "xg"
                  ? "bg-white dark:bg-slate-800 text-purple-600 dark:text-purple-400 shadow-xs"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              xG / Chances
            </button>
          </div>
        </div>
      )}

      {/* Main Sofascore Bar Chart Row */}
      <div className="flex items-stretch gap-3">
        {/* Left Team Badges Stack (Matches Screenshot: Home Top Blue, Away Bottom Sand) */}
        <div className="w-16 sm:w-20 shrink-0 flex flex-col justify-between rounded-2xl border border-slate-300 dark:border-slate-800 overflow-hidden shadow-sm h-44">
          {/* Top Home Team Cell */}
          <div
            className="flex-1 bg-[#e9f2fe] dark:bg-blue-950/40 border-b border-slate-300 dark:border-slate-700 p-2 flex flex-col items-center justify-center text-center gap-1 group cursor-pointer"
            title={`${match.homeTeam.name} (Mandante - Topo)`}
          >
            <TeamShieldBadge team={match.homeTeam} isHome={true} size="md" />
            <span className="text-[10px] font-black text-blue-700 dark:text-blue-300 truncate max-w-[65px] leading-tight">
              {match.homeTeam.shortName || match.homeTeam.name}
            </span>
          </div>

          {/* Bottom Away Team Cell */}
          <div
            className="flex-1 bg-[#faebd7] dark:bg-amber-950/30 p-2 flex flex-col items-center justify-center text-center gap-1 group cursor-pointer"
            title={`${match.awayTeam.name} (Visitante - Baixo)`}
          >
            <TeamShieldBadge team={match.awayTeam} isHome={false} size="md" />
            <span className="text-[10px] font-black text-amber-800 dark:text-amber-300 truncate max-w-[65px] leading-tight">
              {match.awayTeam.shortName || match.awayTeam.name}
            </span>
          </div>
        </div>

        {/* Right Charts: 1º Tempo and 2º Tempo side-by-side */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Card 1: 1º Tempo */}
          {renderHalfCard(firstHalfData, firstHalfEvents, 1)}

          {/* Card 2: 2º Tempo */}
          {renderHalfCard(secondHalfData, secondHalfEvents, 2)}
        </div>
      </div>

      {/* Hover Info Tooltip Bar */}
      {hoveredDataPoint && (
        <div className="bg-slate-950 text-white rounded-xl p-3 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs shadow-xl animate-in fade-in duration-150">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded bg-blue-600 text-white font-black font-mono">
              Minuto {hoveredDataPoint.minute}'
            </span>
            <span className="text-slate-400">
              {hoveredDataPoint.minute <= 45 ? "1º Tempo" : "2º Tempo"}
            </span>
          </div>

          <div className="flex items-center gap-4 font-mono">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
              <span className="text-blue-400 font-bold">{match.homeTeam.shortName}:</span>
              <span className="text-white font-black">{hoveredDataPoint.homeVal}%</span>
              {hoveredDataPoint.homeDangerous && (
                <span className="text-[10px] text-amber-300 bg-amber-950/60 px-1 rounded font-sans">⚡ Ataque</span>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
              <span className="text-amber-400 font-bold">{match.awayTeam.shortName}:</span>
              <span className="text-white font-black">{hoveredDataPoint.awayVal}%</span>
              {hoveredDataPoint.awayDangerous && (
                <span className="text-[10px] text-amber-300 bg-amber-950/60 px-1 rounded font-sans">⚡ Ataque</span>
              )}
            </div>
          </div>

          {hoveredDataPoint.events.length > 0 && (
            <div className="flex items-center gap-1.5">
              {hoveredDataPoint.events.map((e, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded-md bg-emerald-950 border border-emerald-500 text-emerald-300 text-[10px] font-bold"
                >
                  {e.type === "goal" ? "⚽ GOL" : e.type.toUpperCase()}: {e.player || e.team}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Selected Event Modal / Toast */}
      {selectedEvent && (
        <div className="bg-emerald-950/50 border border-emerald-500/40 rounded-xl p-3 text-xs text-emerald-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-base">{selectedEvent.type === "goal" ? "⚽" : "📋"}</span>
            <div>
              <strong>{selectedEvent.type === "goal" ? "GOL CONFIRMADO" : selectedEvent.type.toUpperCase()}</strong> aos {selectedEvent.minute}' por{" "}
              <span className="text-white font-bold">{selectedEvent.player || (selectedEvent.team === "home" ? match.homeTeam.name : match.awayTeam.name)}</span>
              {selectedEvent.assistPlayer && <span> (Assistência: {selectedEvent.assistPlayer})</span>}
            </div>
          </div>
          <button
            onClick={() => setSelectedEvent(null)}
            className="text-emerald-400 hover:text-white text-xs font-bold px-2 py-0.5 bg-emerald-900/60 rounded"
          >
            Fechar
          </button>
        </div>
      )}

      {/* Legend & Summary Info */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-xs bg-[#2563eb]" />
            <span>{match.homeTeam.name} (Mandante)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-xs bg-[#ea580c]" />
            <span>{match.awayTeam.name} (Visitante)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span>⚽ Gol</span>
            <span>🟨 Cartão Amarelo</span>
            <span>🟥 Cartão Vermelho</span>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span>
            Domínio 1T: <strong className="text-blue-500">{halfStats.h1HomeDom}%</strong> vs{" "}
            <strong className="text-amber-500">{halfStats.h1AwayDom}%</strong>
          </span>
          {match.minute > 45 && (
            <span>
              Domínio 2T: <strong className="text-blue-500">{halfStats.h2HomeDom}%</strong> vs{" "}
              <strong className="text-amber-500">{halfStats.h2AwayDom}%</strong>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
