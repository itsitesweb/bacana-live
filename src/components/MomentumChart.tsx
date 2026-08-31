import React, { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  AreaChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import { Match } from "../types";
import { ShieldAlert, Zap, Target, Flame, Activity, Clock, Filter, TrendingUp, TrendingDown, Minus, BarChart2 } from "lucide-react";
import { SofascorePressureChart, TeamShieldBadge } from "./SofascorePressureChart";

interface MomentumChartProps {
  match: Match;
}

export function MomentumChart({ match }: MomentumChartProps) {
  const [chartMode, setChartMode] = useState<"sofascore" | "pressure" | "differential">("sofascore");
  const [differentialViewType, setDifferentialViewType] = useState<"bipolar_area" | "dominance_bars" | "simultaneous_lines">("bipolar_area");
  const [timeRange, setTimeRange] = useState<"all" | "last15" | "1h" | "2h">("all");

  // Filter timeline based on selected timeRange
  let rawTimeline = match.momentumTimeline || [];
  if (timeRange === "last15") {
    const minMinute = Math.max(1, match.minute - 15);
    rawTimeline = rawTimeline.filter((pt) => pt.minute >= minMinute);
  } else if (timeRange === "1h") {
    rawTimeline = rawTimeline.filter((pt) => pt.minute <= 45);
  } else if (timeRange === "2h") {
    rawTimeline = rawTimeline.filter((pt) => pt.minute > 45);
  }

  // Format data for Recharts composed visualization
  const chartData = rawTimeline.map((pt) => {
    const eventAtMin = match.events.find((e) => e.minute === pt.minute);

    // Dynamic combined offensive intensity (0-100) combining possession and dangerous attacks
    const homeOffensiveIntensity = Math.min(
      100,
      Math.round(
        pt.homePressure * 0.6 +
          (pt.homeDangerousAttack ? 25 : 0) +
          (pt.homeShot ? 15 : 0)
      )
    );

    const awayOffensiveIntensity = Math.min(
      100,
      Math.round(
        pt.awayPressure * 0.6 +
          (pt.awayDangerousAttack ? 25 : 0) +
          (pt.awayShot ? 15 : 0)
      )
    );

    const diff = homeOffensiveIntensity - awayOffensiveIntensity;

    return {
      minute: pt.minute,
      homePressure: pt.homePressure,
      awayPressure: pt.awayPressure,
      homeIntensity: homeOffensiveIntensity,
      awayIntensity: awayOffensiveIntensity,
      diff: diff,
      // Home dominance is positive (0 to +100)
      homeDiff: diff > 0 ? diff : 0,
      // Away dominance is negative (-100 to 0) so both teams are shown symmetrically around baseline 0
      awayDiff: diff < 0 ? diff : 0,
      awayDiffAbs: Math.abs(diff < 0 ? diff : 0),
      homeDangerousBar: pt.homeDangerousAttack ? (pt.homeShot ? 85 : 55) : 0,
      awayDangerousBar: pt.awayDangerousAttack ? (pt.awayShot ? 85 : 55) : 0,
      homeShot: pt.homeShot,
      awayShot: pt.awayShot,
      event: eventAtMin ? eventAtMin.type : undefined,
      eventTeam: eventAtMin ? eventAtMin.team : undefined,
      eventPlayer: eventAtMin ? eventAtMin.player : undefined,
      eventDetail: eventAtMin ? `${eventAtMin.type.toUpperCase()}: ${eventAtMin.player || eventAtMin.detail || ""}` : undefined,
    };
  });

  const currentHomePressure = match.stats.pressureIndex.home;
  const currentAwayPressure = match.stats.pressureIndex.away;
  const totalPressure = currentHomePressure + currentAwayPressure || 1;
  const homePressurePct = Math.round((currentHomePressure / totalPressure) * 100);

  // Offensive efficiency: dangerous attacks vs total attacks
  const homeDangerousRatio = match.stats.attacks.home
    ? Math.round((match.stats.dangerousAttacks.home / match.stats.attacks.home) * 100)
    : 50;
  const awayDangerousRatio = match.stats.attacks.away
    ? Math.round((match.stats.dangerousAttacks.away / match.stats.attacks.away) * 100)
    : 50;

  // 5-Minute chances created variation
  const curMin = Math.max(1, match.minute);
  const totalHomeBc = match.stats.bigChances?.home ?? Math.max(0, Math.floor(match.stats.shotsOnTarget.home / 2));
  const totalAwayBc = match.stats.bigChances?.away ?? Math.max(0, Math.floor(match.stats.shotsOnTarget.away / 2));
  const totalBc = totalHomeBc + totalAwayBc;
  const last5Points = (match.momentumTimeline || []).filter((pt) => pt.minute > Math.max(1, curMin - 5) && pt.minute <= curMin);
  const prev5Points = (match.momentumTimeline || []).filter((pt) => pt.minute > Math.max(1, curMin - 10) && pt.minute <= Math.max(1, curMin - 5));
  let homeLast5 = last5Points.filter((pt) => pt.homeShot).length;
  let awayLast5 = last5Points.filter((pt) => pt.awayShot).length;
  let homePrev5 = prev5Points.filter((pt) => pt.homeShot).length;
  let awayPrev5 = prev5Points.filter((pt) => pt.awayShot).length;
  if (homeLast5 === 0 && awayLast5 === 0) {
    homeLast5 = last5Points.filter((pt) => pt.homeDangerousAttack).length;
    awayLast5 = last5Points.filter((pt) => pt.awayDangerousAttack).length;
    homePrev5 = prev5Points.filter((pt) => pt.homeDangerousAttack).length;
    awayPrev5 = prev5Points.filter((pt) => pt.awayDangerousAttack).length;
  }
  let totalLast5 = homeLast5 + awayLast5;
  let totalPrev5 = homePrev5 + awayPrev5;
  let variationPct5Min = 0;
  if (totalPrev5 > 0) {
    variationPct5Min = Math.round(((totalLast5 - totalPrev5) / totalPrev5) * 100);
  } else if (totalLast5 > 0) {
    variationPct5Min = 100;
  } else if (totalBc > 0) {
    const avg5Min = (totalBc / curMin) * 5;
    const recentPressure = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;
    const estLast5 = +(avg5Min * (recentPressure / 50)).toFixed(1);
    const estPrev5 = +avg5Min.toFixed(1);
    variationPct5Min = estPrev5 > 0 ? Math.round(((estLast5 - estPrev5) / estPrev5) * 100) : 0;
    totalLast5 = estLast5;
    totalPrev5 = estPrev5;
  }

  return (
    <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-5 shadow-lg space-y-4">
      {/* Top Header with title and controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Flame className="w-5 h-5 text-amber-400" />
            <h3 className="text-base font-bold text-white tracking-wide">
              Gráfico Dinâmico de Pressão Ofensiva & Intensidade
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Mapeamento dinâmico calculado com base na posse de bola no terço final, volume de ataques perigosos e finalizações minuto a minuto.
          </p>
        </div>

        {/* Right side: 5-Min chances variation + Live Momentum Gauge */}
        <div className="flex flex-wrap items-center gap-3 shrink-0">
          {/* Numerical 5-Minute Chances Variation */}
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs ${
              variationPct5Min > 0
                ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-300"
                : variationPct5Min < 0
                ? "bg-rose-950/40 border-rose-500/50 text-rose-300"
                : "bg-slate-950 border-slate-800 text-slate-400"
            }`}
            title="Variação de chances criadas nos últimos 5 minutos vs janela anterior"
          >
            <span
              className={`p-1 rounded-md ${
                variationPct5Min > 0 ? "bg-emerald-500/20 text-emerald-400" : variationPct5Min < 0 ? "bg-rose-500/20 text-rose-400" : "bg-slate-800"
              }`}
            >
              {variationPct5Min > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : variationPct5Min < 0 ? <TrendingDown className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
            </span>
            <div>
              <span className="text-[9px] text-slate-400 block font-bold uppercase leading-none">Δ Chances (5')</span>
              <span className="text-xs font-black font-mono">
                {variationPct5Min > 0 ? `+${variationPct5Min}%` : `${variationPct5Min}%`}
              </span>
            </div>
          </div>

          {/* Live Momentum Gauge */}
          <div className="flex items-center gap-3 bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-800 shrink-0">
            <div className="text-right">
              <span className="text-[11px] font-semibold text-slate-400 block">{match.homeTeam.shortName}</span>
              <span className="text-sm font-bold text-emerald-400">{currentHomePressure}%</span>
            </div>

            <div className="w-24 h-2.5 bg-slate-800 rounded-full overflow-hidden flex">
              <div
                className="h-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${homePressurePct}%` }}
              />
              <div
                className="h-full bg-cyan-500 transition-all duration-500"
                style={{ width: `${100 - homePressurePct}%` }}
              />
            </div>

            <div>
              <span className="text-[11px] font-semibold text-slate-400 block">{match.awayTeam.shortName}</span>
              <span className="text-sm font-bold text-cyan-400">{currentAwayPressure}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Control Filter Bars: Mode + Time Window */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-800/80">
        {/* Mode Selector */}
        <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setChartMode("sofascore")}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              chartMode === "sofascore"
                ? "bg-blue-600 text-white shadow-sm border border-blue-400/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            Visual Sofascore (1T & 2T)
          </button>
          <button
            onClick={() => setChartMode("pressure")}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
              chartMode === "pressure"
                ? "bg-slate-800 text-emerald-400 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Painéis Separados
          </button>
          <button
            onClick={() => setChartMode("differential")}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
              chartMode === "differential"
                ? "bg-slate-800 text-emerald-400 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Diferencial (+/-)
          </button>
        </div>

        {/* Time Window Filter (for recharts views) */}
        {chartMode !== "sofascore" && (
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <span className="text-[11px] font-medium text-slate-500 px-2 flex items-center gap-1">
              <Clock className="w-3 h-3" /> Janela:
            </span>
            <button
              onClick={() => setTimeRange("all")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                timeRange === "all" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Jogo Completo
            </button>
            <button
              onClick={() => setTimeRange("last15")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                timeRange === "last15" ? "bg-slate-800 text-amber-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Últimos 15 min
            </button>
            <button
              onClick={() => setTimeRange("1h")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                timeRange === "1h" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              1º Tempo
            </button>
            <button
              onClick={() => setTimeRange("2h")}
              className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                timeRange === "2h" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              2º Tempo
            </button>
          </div>
        )}
      </div>

      {/* Main Dynamic Canvas */}
      {chartMode === "sofascore" ? (
        <SofascorePressureChart match={match} showControls={false} className="border-0 p-0 shadow-none bg-transparent dark:bg-transparent" />
      ) : chartMode === "differential" ? (
        /* Differential Momentum Chart (+ is Home dominant, - is Away dominant) */
        <div className="space-y-3 pt-2">
          {/* Header indicator showing both teams and the balance */}
          <div className="grid grid-cols-1 sm:grid-cols-3 items-center gap-2 p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs">
            {/* Home team indicator */}
            <div className="flex items-center gap-2">
              <TeamShieldBadge team={match.homeTeam} isHome={true} size="sm" />
              <div>
                <span className="font-bold text-emerald-400 block truncate">{match.homeTeam.name}</span>
                <span className="text-[10px] text-slate-400">Zona Superior (+)</span>
              </div>
            </div>

            {/* Central status */}
            <div className="text-center font-mono text-[11px] text-slate-300 bg-slate-900/90 px-3 py-1.5 rounded-lg border border-slate-800 flex flex-col items-center justify-center">
              {currentHomePressure > currentAwayPressure ? (
                <span className="text-emerald-400 font-bold">
                  ▲ +{currentHomePressure - currentAwayPressure}% {match.homeTeam.shortName}
                </span>
              ) : currentAwayPressure > currentHomePressure ? (
                <span className="text-cyan-400 font-bold">
                  ▼ +{currentAwayPressure - currentHomePressure}% {match.awayTeam.shortName}
                </span>
              ) : (
                <span className="text-slate-300">⚖ Equilíbrio (0%)</span>
              )}
              <span className="text-[9px] text-slate-500 font-normal">Saldo de Pressão ao Vivo</span>
            </div>

            {/* Away team indicator */}
            <div className="flex items-center justify-end gap-2 text-right">
              <div>
                <span className="font-bold text-cyan-400 block truncate">{match.awayTeam.name}</span>
                <span className="text-[10px] text-slate-400">Zona Inferior (-)</span>
              </div>
              <TeamShieldBadge team={match.awayTeam} isHome={false} size="sm" />
            </div>
          </div>

          {/* Sub-view Style Selector for Differential view */}
          <div className="flex items-center justify-between gap-2 px-1 text-xs">
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setDifferentialViewType("bipolar_area")}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                  differentialViewType === "bipolar_area"
                    ? "bg-slate-800 text-cyan-300 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Curva Bipolar (+/-)
              </button>
              <button
                type="button"
                onClick={() => setDifferentialViewType("dominance_bars")}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                  differentialViewType === "dominance_bars"
                    ? "bg-slate-800 text-cyan-300 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Barras de Pressão (+/-)
              </button>
              <button
                type="button"
                onClick={() => setDifferentialViewType("simultaneous_lines")}
                className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${
                  differentialViewType === "simultaneous_lines"
                    ? "bg-slate-800 text-cyan-300 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Linhas Sobrepostas (0-100%)
              </button>
            </div>

            {/* Dominance summary ratio */}
            {(() => {
              const homeDomMins = chartData.filter((d) => d.diff > 5).length;
              const awayDomMins = chartData.filter((d) => d.diff < -5).length;
              const totalMins = chartData.length || 1;
              const homePct = Math.round((homeDomMins / totalMins) * 100);
              const awayPct = Math.round((awayDomMins / totalMins) * 100);
              return (
                <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-slate-400">
                  <span>Tempo Dominando:</span>
                  <span className="text-emerald-400 font-bold">{match.homeTeam.shortName} {homePct}%</span>
                  <span>vs</span>
                  <span className="text-cyan-400 font-bold">{match.awayTeam.shortName} {awayPct}%</span>
                </div>
              );
            })()}
          </div>

          <div className="h-72 w-full pt-1">
            <ResponsiveContainer width="100%" height="100%">
              {differentialViewType === "bipolar_area" ? (
                <AreaChart data={chartData} margin={{ top: 15, right: 15, left: -15, bottom: 0 }}>
                  <defs>
                    <linearGradient id="diffBipolarGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10B981" stopOpacity={0.85} />
                      <stop offset="47%" stopColor="#10B981" stopOpacity={0.15} />
                      <stop offset="50%" stopColor="#64748B" stopOpacity={0.0} />
                      <stop offset="53%" stopColor="#06B6D4" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#06B6D4" stopOpacity={0.85} />
                    </linearGradient>
                  </defs>

                  <XAxis
                    dataKey="minute"
                    stroke="#64748B"
                    fontSize={11}
                    tickFormatter={(v) => `${v}'`}
                  />
                  <YAxis
                    stroke="#64748B"
                    fontSize={11}
                    domain={[-100, 100]}
                    ticks={[-80, -40, 0, 40, 80]}
                    tickFormatter={(v) => (v > 0 ? `+${v}%` : v < 0 ? `${v}%` : "0%")}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        const isHomeDominant = data.diff > 0;
                        const isAwayDominant = data.diff < 0;
                        return (
                          <div className="bg-slate-950 border border-slate-700 p-3 rounded-xl shadow-xl text-xs space-y-1.5 min-w-[210px]">
                            <div className="font-bold text-white border-b border-slate-800 pb-1 flex justify-between">
                              <span>Minuto {data.minute}'</span>
                              {data.event && (
                                <span className="text-amber-400 font-extrabold uppercase">
                                  {data.event === "goal" ? "⚽ GOL" : data.event}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between text-emerald-400">
                              <span className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                                {match.homeTeam.name}:
                              </span>
                              <span className="font-bold">{data.homePressure}%</span>
                            </div>
                            <div className="flex items-center justify-between text-cyan-400">
                              <span className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-cyan-400" />
                                {match.awayTeam.name}:
                              </span>
                              <span className="font-bold">{data.awayPressure}%</span>
                            </div>
                            <div className="text-[11px] pt-1.5 border-t border-slate-800 text-slate-300 font-medium flex justify-between">
                              <span>Saldo Diferencial:</span>
                              <strong className={isHomeDominant ? "text-emerald-400 font-bold" : isAwayDominant ? "text-cyan-400 font-bold" : "text-slate-400"}>
                                {isHomeDominant
                                  ? `+${data.diff}% (${match.homeTeam.shortName})`
                                  : isAwayDominant
                                  ? `+${Math.abs(data.diff)}% (${match.awayTeam.shortName})`
                                  : "0% (Equilíbrio)"}
                              </strong>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  {/* Central Zero Baseline */}
                  <ReferenceLine y={0} stroke="#94A3B8" strokeWidth={1.5} />
                  {/* Reference Threshold Lines */}
                  <ReferenceLine y={40} stroke="#10B981" strokeDasharray="3 3" opacity={0.35} label={{ value: `+40% ${match.homeTeam.shortName}`, fill: "#10B981", fontSize: 10, position: "insideTopRight" }} />
                  <ReferenceLine y={-40} stroke="#06B6D4" strokeDasharray="3 3" opacity={0.35} label={{ value: `+40% ${match.awayTeam.shortName}`, fill: "#06B6D4", fontSize: 10, position: "insideBottomRight" }} />

                  {/* Unified Dynamic Bipolar Area (Fills from 0 upwards for Home and 0 downwards for Away) */}
                  <Area
                    type="monotone"
                    dataKey="diff"
                    baseValue={0}
                    name="Diferencial (+/-)"
                    stroke="#94A3B8"
                    strokeWidth={1.5}
                    fill="url(#diffBipolarGradient)"
                  />
                </AreaChart>
              ) : differentialViewType === "dominance_bars" ? (
                <ComposedChart data={chartData} margin={{ top: 15, right: 15, left: -15, bottom: 0 }}>
                  <XAxis
                    dataKey="minute"
                    stroke="#64748B"
                    fontSize={11}
                    tickFormatter={(v) => `${v}'`}
                  />
                  <YAxis
                    stroke="#64748B"
                    fontSize={11}
                    domain={[-100, 100]}
                    ticks={[-80, -40, 0, 40, 80]}
                    tickFormatter={(v) => (v > 0 ? `+${v}%` : v < 0 ? `${v}%` : "0%")}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        const isHomeDominant = data.diff > 0;
                        const isAwayDominant = data.diff < 0;
                        return (
                          <div className="bg-slate-950 border border-slate-700 p-3 rounded-xl shadow-xl text-xs space-y-1.5 min-w-[210px]">
                            <div className="font-bold text-white border-b border-slate-800 pb-1 flex justify-between">
                              <span>Minuto {data.minute}'</span>
                              {data.event && (
                                <span className="text-amber-400 font-extrabold uppercase">
                                  {data.event === "goal" ? "⚽ GOL" : data.event}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between text-emerald-400">
                              <span>{match.homeTeam.name}:</span>
                              <span className="font-bold">{data.homePressure}%</span>
                            </div>
                            <div className="flex items-center justify-between text-cyan-400">
                              <span>{match.awayTeam.name}:</span>
                              <span className="font-bold">{data.awayPressure}%</span>
                            </div>
                            <div className="text-[11px] pt-1.5 border-t border-slate-800 text-slate-300 font-medium flex justify-between">
                              <span>Dominância:</span>
                              <strong className={isHomeDominant ? "text-emerald-400 font-bold" : isAwayDominant ? "text-cyan-400 font-bold" : "text-slate-400"}>
                                {isHomeDominant
                                  ? `+${data.homeDiff}% (${match.homeTeam.shortName})`
                                  : isAwayDominant
                                  ? `+${data.awayDiffAbs}% (${match.awayTeam.shortName})`
                                  : "0% (Equilíbrio)"}
                              </strong>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine y={0} stroke="#94A3B8" strokeWidth={1.5} />
                  <ReferenceLine y={40} stroke="#10B981" strokeDasharray="3 3" opacity={0.35} />
                  <ReferenceLine y={-40} stroke="#06B6D4" strokeDasharray="3 3" opacity={0.35} />

                  {/* Home Dominance Bars (Above 0) */}
                  <Bar
                    dataKey="homeDiff"
                    name={`Vantagem ${match.homeTeam.shortName} (+)`}
                    fill="#10B981"
                    radius={[3, 3, 0, 0]}
                  />
                  {/* Away Dominance Bars (Below 0) */}
                  <Bar
                    dataKey="awayDiff"
                    name={`Vantagem ${match.awayTeam.shortName} (-)`}
                    fill="#06B6D4"
                    radius={[0, 0, 3, 3]}
                  />
                </ComposedChart>
              ) : (
                /* Simultaneous Overlay Lines */
                <ComposedChart data={chartData} margin={{ top: 15, right: 15, left: -15, bottom: 0 }}>
                  <defs>
                    <linearGradient id="homeLineGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10B981" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#10B981" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="awayLineGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="minute"
                    stroke="#64748B"
                    fontSize={11}
                    tickFormatter={(v) => `${v}'`}
                  />
                  <YAxis
                    stroke="#64748B"
                    fontSize={11}
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-slate-950 border border-slate-700 p-3 rounded-xl shadow-xl text-xs space-y-1.5 min-w-[200px]">
                            <div className="font-bold text-white border-b border-slate-800 pb-1 flex justify-between">
                              <span>Minuto {data.minute}'</span>
                              {data.event && (
                                <span className="text-amber-400 font-extrabold uppercase">
                                  {data.event === "goal" ? "⚽ GOL" : data.event}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between text-emerald-400">
                              <span>{match.homeTeam.name}:</span>
                              <span className="font-bold">{data.homePressure}%</span>
                            </div>
                            <div className="flex items-center justify-between text-cyan-400">
                              <span>{match.awayTeam.name}:</span>
                              <span className="font-bold">{data.awayPressure}%</span>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine y={50} stroke="#475569" strokeDasharray="3 3" opacity={0.5} />
                  <ReferenceLine y={75} stroke="#F59E0B" strokeDasharray="3 3" opacity={0.4} label={{ value: "Pressão Crítica", fill: "#F59E0B", fontSize: 10, position: "insideTopRight" }} />

                  <Area
                    type="monotone"
                    dataKey="homePressure"
                    name={match.homeTeam.name}
                    stroke="#10B981"
                    strokeWidth={2.5}
                    fill="url(#homeLineGrad)"
                    dot={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="awayPressure"
                    name={match.awayTeam.name}
                    stroke="#06B6D4"
                    strokeWidth={2.5}
                    fill="url(#awayLineGrad)"
                    dot={false}
                  />
                </ComposedChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        /* SEPARATED STACKED CHARTS (TOP: HOME, BOTTOM: AWAY) */
        <div className="space-y-3 pt-2">
          {/* Top Chart: Home Team */}
          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/90">
            <div className="flex items-center justify-between text-xs mb-1 px-1">
              <div className="flex items-center gap-2">
                <TeamShieldBadge team={match.homeTeam} isHome={true} size="sm" />
                <span className="font-bold text-emerald-400">{match.homeTeam.name}</span>
                <span className="text-[10px] text-slate-500 font-mono">(Mandante)</span>
              </div>
              <span className="text-[11px] font-mono text-emerald-300">
                Pressão Atual: <strong>{currentHomePressure}%</strong>
              </span>
            </div>

            <div className="h-36 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="homeMomGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10B981" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#10B981" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="minute" stroke="#64748B" fontSize={10} tickFormatter={(v) => `${v}'`} />
                  <YAxis stroke="#64748B" fontSize={10} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-slate-950 border border-emerald-500/40 p-2.5 rounded-xl shadow-xl text-xs space-y-1">
                            <div className="font-bold text-emerald-400 flex justify-between gap-2 border-b border-slate-800 pb-0.5">
                              <span>{match.homeTeam.name}</span>
                              <span className="font-mono">{data.minute}'</span>
                            </div>
                            <div className="text-slate-200">Pressão: <strong className="text-emerald-400">{data.homePressure}%</strong></div>
                            {data.homeDangerousBar > 0 && (
                              <div className="text-[10px] text-amber-300 font-bold">⚡ Ataque Perigoso Registrado</div>
                            )}
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine y={50} stroke="#334155" strokeDasharray="3 3" />
                  <ReferenceLine y={75} stroke="#10B981" strokeDasharray="2 2" opacity={0.5} />
                  <Area
                    type="monotone"
                    dataKey="homePressure"
                    name={match.homeTeam.name}
                    stroke="#10B981"
                    strokeWidth={2.2}
                    fillOpacity={1}
                    fill="url(#homeMomGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Bottom Chart: Away Team */}
          <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800/90">
            <div className="flex items-center justify-between text-xs mb-1 px-1">
              <div className="flex items-center gap-2">
                <TeamShieldBadge team={match.awayTeam} isHome={false} size="sm" />
                <span className="font-bold text-cyan-400">{match.awayTeam.name}</span>
                <span className="text-[10px] text-slate-500 font-mono">(Visitante)</span>
              </div>
              <span className="text-[11px] font-mono text-cyan-300">
                Pressão Atual: <strong>{currentAwayPressure}%</strong>
              </span>
            </div>

            <div className="h-36 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="awayMomGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="minute" stroke="#64748B" fontSize={10} tickFormatter={(v) => `${v}'`} />
                  <YAxis stroke="#64748B" fontSize={10} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-slate-950 border border-cyan-500/40 p-2.5 rounded-xl shadow-xl text-xs space-y-1">
                            <div className="font-bold text-cyan-400 flex justify-between gap-2 border-b border-slate-800 pb-0.5">
                              <span>{match.awayTeam.name}</span>
                              <span className="font-mono">{data.minute}'</span>
                            </div>
                            <div className="text-slate-200">Pressão: <strong className="text-cyan-400">{data.awayPressure}%</strong></div>
                            {data.awayDangerousBar > 0 && (
                              <div className="text-[10px] text-amber-300 font-bold">⚡ Ataque Perigoso Registrado</div>
                            )}
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <ReferenceLine y={50} stroke="#334155" strokeDasharray="3 3" />
                  <ReferenceLine y={75} stroke="#06B6D4" strokeDasharray="2 2" opacity={0.5} />
                  <Area
                    type="monotone"
                    dataKey="awayPressure"
                    name={match.awayTeam.name}
                    stroke="#06B6D4"
                    strokeWidth={2.2}
                    fillOpacity={1}
                    fill="url(#awayMomGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Statistical Summary Footer: Dangerous Attacks Ratio & Pressure Dominance */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-800 text-xs">
        <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-slate-400 block font-medium">Periculosidade Mandante</span>
            <span className="font-bold text-emerald-400">{homeDangerousRatio}% dos Ataques</span>
          </div>
          <span className="text-[11px] text-slate-500 font-mono">
            {match.stats.dangerousAttacks.home}/{match.stats.attacks.home}
          </span>
        </div>

        <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-slate-400 block font-medium">Ataques Últimos 10 min</span>
            <span className="font-bold text-amber-300">
              {match.stats.dangerousAttacksLast10.home} vs {match.stats.dangerousAttacksLast10.away}
            </span>
          </div>
          <Zap className="w-4 h-4 text-amber-400" />
        </div>

        <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-slate-400 block font-medium">Periculosidade Visitante</span>
            <span className="font-bold text-cyan-400">{awayDangerousRatio}% dos Ataques</span>
          </div>
          <span className="text-[11px] text-slate-500 font-mono">
            {match.stats.dangerousAttacks.away}/{match.stats.attacks.away}
          </span>
        </div>
      </div>
    </div>
  );
}
