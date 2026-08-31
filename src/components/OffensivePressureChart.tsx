import React, { useState, useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ReferenceDot,
} from "recharts";
import { Match } from "../types";
import { TrendingUp, TrendingDown, Minus, Zap, Target, Clock, Award, ShieldAlert, BarChart3, Filter, Activity, Flame, SplitSquareVertical } from "lucide-react";
import { SofascorePressureChart } from "./SofascorePressureChart";

interface OffensivePressureChartProps {
  match: Match;
}

export function OffensivePressureChart({ match }: OffensivePressureChartProps) {
  const [chartView, setChartView] = useState<"sofascore" | "lines">("sofascore");
  const [metricMode, setMetricMode] = useState<"pressure" | "chances" | "xg" | "combined">("pressure");
  const [timeFilter, setTimeFilter] = useState<"all" | "1h" | "2h" | "last15">("all");

  const timeline = match.momentumTimeline || [];
  const events = match.events || [];
  const stats = match.stats;

  // Process timeline data with cumulative chances, xG progression, and smoothed pressure
  const processedData = useMemo(() => {
    let homeAccChances = 0;
    let awayAccChances = 0;
    let homeAccXg = 0;
    let awayAccXg = 0;

    const totalHomeBc = stats.bigChances?.home ?? Math.max(0, Math.floor(stats.shotsOnTarget.home / 2));
    const totalAwayBc = stats.bigChances?.away ?? Math.max(0, Math.floor(stats.shotsOnTarget.away / 2));
    const totalHomeXg = stats.xG.home;
    const totalAwayXg = stats.xG.away;

    // Filter timeline based on time window
    let activeTimeline = [...timeline];
    if (activeTimeline.length === 0) {
      // Fallback if empty
      for (let m = 1; m <= Math.max(1, match.minute); m++) {
        activeTimeline.push({
          minute: m,
          homePressure: 50,
          awayPressure: 50,
          diff: 0,
        });
      }
    }

    const currentMaxMin = Math.max(1, match.minute);
    const homeBcInterval = totalHomeBc > 0 ? currentMaxMin / (totalHomeBc + 1) : 999;
    const awayBcInterval = totalAwayBc > 0 ? currentMaxMin / (totalAwayBc + 1) : 999;

    const dataPoints = activeTimeline.map((pt, index) => {
      const min = pt.minute;
      const eventAtMin = events.find((e) => e.minute === min);

      // Distribute chances created and xG proportionally to pressure spikes
      if (pt.homeShot || (totalHomeBc > 0 && Math.abs(min % Math.round(homeBcInterval)) === 0)) {
        if (homeAccChances < totalHomeBc) {
          homeAccChances += 1;
        }
      }
      if (pt.awayShot || (totalAwayBc > 0 && Math.abs(min % Math.round(awayBcInterval)) === 0)) {
        if (awayAccChances < totalAwayBc) {
          awayAccChances += 1;
        }
      }

      // xG step accumulation
      const homeXgStep = totalHomeXg > 0 ? (pt.homePressure / 100) * (totalHomeXg / Math.max(1, activeTimeline.length)) * 1.5 : 0;
      const awayXgStep = totalAwayXg > 0 ? (pt.awayPressure / 100) * (totalAwayXg / Math.max(1, activeTimeline.length)) * 1.5 : 0;
      homeAccXg = Math.min(totalHomeXg, homeAccXg + homeXgStep);
      awayAccXg = Math.min(totalAwayXg, awayAccXg + awayXgStep);

      // Pressure index with shot boost
      const homePress = Math.min(100, Math.max(0, pt.homePressure + (pt.homeDangerousAttack ? 15 : 0) + (pt.homeShot ? 10 : 0)));
      const awayPress = Math.min(100, Math.max(0, pt.awayPressure + (pt.awayDangerousAttack ? 15 : 0) + (pt.awayShot ? 10 : 0)));

      return {
        minute: min,
        homePressure: homePress,
        awayPressure: awayPress,
        homeChances: Math.min(totalHomeBc, homeAccChances),
        awayChances: Math.min(totalAwayBc, awayAccChances),
        homeXg: Number(homeAccXg.toFixed(2)),
        awayXg: Number(awayAccXg.toFixed(2)),
        diff: homePress - awayPress,
        isGoal: eventAtMin?.type === "goal",
        isRedCard: eventAtMin?.type === "red_card",
        eventDetail: eventAtMin ? `${eventAtMin.type.toUpperCase()} (${eventAtMin.team === 'home' ? match.homeTeam.shortName : match.awayTeam.shortName}): ${eventAtMin.player || ''}` : undefined,
      };
    });

    // Final point alignment with overall stats
    if (dataPoints.length > 0) {
      const last = dataPoints[dataPoints.length - 1];
      last.homeChances = totalHomeBc;
      last.awayChances = totalAwayBc;
      last.homeXg = Number(totalHomeXg.toFixed(2));
      last.awayXg = Number(totalAwayXg.toFixed(2));
    }

    // Apply time window filter
    if (timeFilter === "1h") {
      return dataPoints.filter((d) => d.minute <= 45);
    } else if (timeFilter === "2h") {
      return dataPoints.filter((d) => d.minute > 45);
    } else if (timeFilter === "last15") {
      const minMin = Math.max(1, match.minute - 15);
      return dataPoints.filter((d) => d.minute >= minMin);
    }

    return dataPoints;
  }, [timeline, events, stats, match.minute, timeFilter, match.homeTeam.shortName, match.awayTeam.shortName]);

  // Find peak pressure moments
  const peakHome = useMemo(() => {
    return processedData.reduce((prev, curr) => (curr.homePressure > prev.homePressure ? curr : prev), processedData[0] || { minute: 0, homePressure: 0 });
  }, [processedData]);

  const peakAway = useMemo(() => {
    return processedData.reduce((prev, curr) => (curr.awayPressure > prev.awayPressure ? curr : prev), processedData[0] || { minute: 0, awayPressure: 0 });
  }, [processedData]);

  // Goal events for markers
  const goalEvents = useMemo(() => {
    return processedData.filter((d) => d.isGoal);
  }, [processedData]);

  // 5-Minute Chances Created Variation Calculation
  const last5MinStats = useMemo(() => {
    const curMin = Math.max(1, match.minute);
    const windowStartLast5 = Math.max(1, curMin - 5);
    const windowStartPrev5 = Math.max(1, curMin - 10);

    const totalHomeBc = stats.bigChances?.home ?? Math.max(0, Math.floor(stats.shotsOnTarget.home / 2));
    const totalAwayBc = stats.bigChances?.away ?? Math.max(0, Math.floor(stats.shotsOnTarget.away / 2));
    const totalBc = totalHomeBc + totalAwayBc;

    // Timeline points in windows
    const last5Points = timeline.filter((pt) => pt.minute > windowStartLast5 && pt.minute <= curMin);
    const prev5Points = timeline.filter((pt) => pt.minute > windowStartPrev5 && pt.minute <= windowStartLast5);

    // Count chances (shots or dangerous attacks registered in timeline)
    let homeLast5 = last5Points.filter((pt) => pt.homeShot).length;
    let awayLast5 = last5Points.filter((pt) => pt.awayShot).length;
    let homePrev5 = prev5Points.filter((pt) => pt.homeShot).length;
    let awayPrev5 = prev5Points.filter((pt) => pt.awayShot).length;

    // If no direct shots flagged in timeline slice, check dangerous attacks or synthetic distribution
    if (homeLast5 === 0 && awayLast5 === 0) {
      homeLast5 = last5Points.filter((pt) => pt.homeDangerousAttack).length;
      awayLast5 = last5Points.filter((pt) => pt.awayDangerousAttack).length;
      homePrev5 = prev5Points.filter((pt) => pt.homeDangerousAttack).length;
      awayPrev5 = prev5Points.filter((pt) => pt.awayDangerousAttack).length;
    }

    // If still zero but overall match has big chances, compute weighted rolling average
    if (homeLast5 === 0 && awayLast5 === 0 && totalBc > 0) {
      const avg5Min = (totalBc / curMin) * 5;
      const recentPressure = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;
      const pressureMultiplier = recentPressure / 50;
      const estimatedLast5 = Math.max(0, +(avg5Min * pressureMultiplier).toFixed(1));
      const estimatedPrev5 = Math.max(0, +(avg5Min).toFixed(1));
      const diff = estimatedLast5 - estimatedPrev5;
      const pct = estimatedPrev5 > 0 ? Math.round((diff / estimatedPrev5) * 100) : estimatedLast5 > 0 ? 100 : 0;

      return {
        curMin,
        totalLast5: estimatedLast5,
        totalPrev5: estimatedPrev5,
        homeLast5: +(estimatedLast5 * (match.stats.pressureIndex.home / (match.stats.pressureIndex.home + match.stats.pressureIndex.away || 1))).toFixed(1),
        awayLast5: +(estimatedLast5 * (match.stats.pressureIndex.away / (match.stats.pressureIndex.home + match.stats.pressureIndex.away || 1))).toFixed(1),
        variationPct: pct,
        isSurge: pct >= 25,
        isDrop: pct <= -25,
      };
    }

    const totalLast5 = homeLast5 + awayLast5;
    const totalPrev5 = homePrev5 + awayPrev5;

    let variationPct = 0;
    if (totalPrev5 > 0) {
      variationPct = Math.round(((totalLast5 - totalPrev5) / totalPrev5) * 100);
    } else if (totalLast5 > 0) {
      variationPct = 100;
    } else {
      variationPct = 0;
    }

    return {
      curMin,
      totalLast5,
      totalPrev5,
      homeLast5,
      awayLast5,
      variationPct,
      isSurge: variationPct >= 25,
      isDrop: variationPct <= -25,
    };
  }, [match.minute, stats, timeline, match.stats.pressureIndex]);

  return (
    <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
      {/* Header section */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              <TrendingUp className="w-5 h-5" />
            </span>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Evolução da Pressão Ofensiva & Chances Criadas
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                  Recharts
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Curvas temporais da intensidade ofensiva, chances claras acumuladas e xG ao longo do tempo de jogo.
              </p>
            </div>
          </div>
        </div>

        {/* Right side: Numerical Indicator of 5-Minute Chances Variation + Live Stats */}
        <div className="flex flex-wrap items-center gap-3">
          {/* 5-Min Chances Variation Numeric Indicator */}
          <div
            className={`flex items-center gap-3 px-3.5 py-2 rounded-xl border transition-all shadow-md ${
              last5MinStats.variationPct > 0
                ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-300"
                : last5MinStats.variationPct < 0
                ? "bg-rose-950/40 border-rose-500/50 text-rose-300"
                : "bg-slate-950 border-slate-800 text-slate-300"
            }`}
            title={`Variação de chances criadas nos últimos 5 minutos (${Math.max(1, match.minute - 5)}'-${match.minute}') em relação aos 5 minutos anteriores.`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`p-1.5 rounded-lg border ${
                  last5MinStats.variationPct > 0
                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 animate-pulse"
                    : last5MinStats.variationPct < 0
                    ? "bg-rose-500/20 text-rose-400 border-rose-500/30"
                    : "bg-slate-800 text-slate-400 border-slate-700"
                }`}
              >
                {last5MinStats.variationPct > 0 ? (
                  <TrendingUp className="w-4 h-4" />
                ) : last5MinStats.variationPct < 0 ? (
                  <TrendingDown className="w-4 h-4" />
                ) : (
                  <Minus className="w-4 h-4" />
                )}
              </span>
              <div>
                <span className="text-[10px] text-slate-400 block uppercase font-bold tracking-tight">
                  Δ Chances (Últimos 5')
                </span>
                <div className="flex items-baseline gap-1.5">
                  <span
                    className={`text-base font-black font-mono tracking-tight ${
                      last5MinStats.variationPct > 0
                        ? "text-emerald-300"
                        : last5MinStats.variationPct < 0
                        ? "text-rose-300"
                        : "text-slate-200"
                    }`}
                  >
                    {last5MinStats.variationPct > 0 ? `+${last5MinStats.variationPct}%` : `${last5MinStats.variationPct}%`}
                  </span>
                  <span className="text-[10px] text-slate-400 font-medium">
                    ({last5MinStats.totalLast5} vs {last5MinStats.totalPrev5})
                  </span>
                </div>
              </div>
            </div>

            <div className="hidden sm:block h-7 w-px bg-slate-800" />

            {/* Micro team contribution */}
            <div className="hidden sm:flex flex-col text-[10px] font-mono">
              <span className="text-emerald-400 font-bold">
                {match.homeTeam.shortName}: {last5MinStats.homeLast5}
              </span>
              <span className="text-cyan-400 font-bold">
                {match.awayTeam.shortName}: {last5MinStats.awayLast5}
              </span>
            </div>
          </div>

          {/* Live Teams Big Chances / xG Ticker */}
          <div className="flex items-center gap-3 bg-slate-950 px-3.5 py-2 rounded-xl border border-slate-800 shrink-0">
            <div className="text-right">
              <span className="text-[11px] font-semibold text-emerald-400 block">{match.homeTeam.shortName}</span>
              <span className="text-xs text-slate-400 font-mono">
                CC: {stats.bigChances?.home ?? Math.max(0, Math.floor(stats.shotsOnTarget.home / 2))} | xG: {stats.xG.home.toFixed(2)}
              </span>
            </div>
            <div className="h-7 w-px bg-slate-800" />
            <div className="text-left">
              <span className="text-[11px] font-semibold text-cyan-400 block">{match.awayTeam.shortName}</span>
              <span className="text-xs text-slate-400 font-mono">
                CC: {stats.bigChances?.away ?? Math.max(0, Math.floor(stats.shotsOnTarget.away / 2))} | xG: {stats.xG.away.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Control Buttons: Chart Type, Metric Mode & Time Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
        {/* Chart View Switcher */}
        <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setChartView("sofascore")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
              chartView === "sofascore"
                ? "bg-blue-600 text-white shadow-sm border border-blue-400/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            Visual Sofascore (1T & 2T)
          </button>
          <button
            onClick={() => setChartView("lines")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
              chartView === "lines"
                ? "bg-slate-800 text-emerald-400 shadow-sm border border-emerald-500/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <SplitSquareVertical className="w-3.5 h-3.5" />
            Curvas Separadas
          </button>
        </div>

        {/* Time Window Filter (for lines view) */}
        {chartView === "lines" && (
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <span className="text-[11px] font-medium text-slate-500 px-2 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" /> Janela:
            </span>
            <button
              onClick={() => setTimeFilter("all")}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                timeFilter === "all" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Completo
            </button>
            <button
              onClick={() => setTimeFilter("1h")}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                timeFilter === "1h" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              1º Tempo
            </button>
            <button
              onClick={() => setTimeFilter("2h")}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                timeFilter === "2h" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              2º Tempo
            </button>
            <button
              onClick={() => setTimeFilter("last15")}
              className={`px-2.5 py-1 rounded-lg font-bold transition ${
                timeFilter === "last15" ? "bg-slate-800 text-amber-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Últimos 15'
            </button>
          </div>
        )}
      </div>

      {/* RENDER PRIMARY SOFASCORE CHART OR SEPARATED LINES */}
      {chartView === "sofascore" ? (
        <SofascorePressureChart match={match} showControls={true} />
      ) : (
        /* SEPARATED CHARTS (1 TOP: MANDANTE, 1 BOTTOM: VISITANTE) */
        <div className="space-y-4 pt-1">
          {/* CHART 1: MANDANTE (HOME TEAM) */}
          <div className="bg-slate-950/80 rounded-2xl border border-slate-800/90 p-4 shadow-inner">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2 px-1">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 ring-4 ring-emerald-500/20 animate-pulse" />
                <span className="text-xs font-black uppercase tracking-wider text-emerald-400">
                  {match.homeTeam.name}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 font-bold uppercase">
                  Mandante
                </span>
              </div>

              <div className="flex items-center gap-3 text-[11px] font-mono">
                <span className="text-slate-400">
                  Pressão Atual: <strong className="text-emerald-400">{match.stats.pressureIndex.home}%</strong>
                </span>
                <span className="text-slate-400">
                  CC: <strong className="text-amber-300">{stats.bigChances?.home ?? Math.max(0, Math.floor(stats.shotsOnTarget.home / 2))}</strong>
                </span>
                <span className="text-slate-400">
                  xG: <strong className="text-purple-300">{stats.xG.home.toFixed(2)}</strong>
                </span>
                <span className="text-slate-500 hidden sm:inline">
                  Pico: <strong className="text-emerald-300">{peakHome.homePressure}%</strong> ({peakHome.minute}')
                </span>
              </div>
            </div>

            <div className="h-48 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={processedData}
                  margin={{ top: 10, right: 15, left: -10, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="homePressureGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10B981" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#10B981" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="minute"
                    stroke="#64748b"
                    fontSize={10}
                    tickFormatter={(v) => `${v}'`}
                  />
                  <YAxis
                    stroke="#64748b"
                    fontSize={10}
                    domain={metricMode === "xg" ? [0, "auto"] : [0, 100]}
                    tickFormatter={(v) => metricMode === "xg" ? v.toFixed(1) : `${v}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        const homeGoal = events.find((e) => e.minute === data.minute && e.type === "goal" && e.team === "home");
                        return (
                          <div className="bg-slate-950/95 border border-emerald-500/40 p-2.5 rounded-xl shadow-2xl text-xs space-y-1 backdrop-blur-md">
                            <div className="font-bold text-white flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                              <span className="text-emerald-400 font-semibold">{match.homeTeam.name}</span>
                              <span className="font-mono text-slate-300">{data.minute}'</span>
                            </div>
                            <div className="text-slate-200 space-y-0.5 pt-0.5">
                              <div>Pressão Ofensiva: <strong className="text-emerald-400">{data.homePressure}%</strong></div>
                              <div>Chances Claras: <strong className="text-amber-300">{data.homeChances}</strong></div>
                              <div>xG Acumulado: <strong className="text-purple-300">{data.homeXg}</strong></div>
                            </div>
                            {homeGoal && (
                              <div className="text-[10px] text-emerald-300 bg-emerald-950/60 p-1 rounded font-bold border border-emerald-500/30">
                                ⚽ GOL de {homeGoal.player || match.homeTeam.name}!
                              </div>
                            )}
                          </div>
                        );
                      }
                      return null;
                    }}
                  />

                  {metricMode === "pressure" || metricMode === "combined" ? (
                    <>
                      <ReferenceLine y={50} stroke="#334155" strokeDasharray="3 3" />
                      <ReferenceLine
                        y={75}
                        stroke="#10b981"
                        strokeDasharray="2 2"
                        opacity={0.5}
                        label={{ value: "Crítica (75%)", fill: "#10b981", fontSize: 9, position: "insideTopLeft" }}
                      />
                    </>
                  ) : null}

                  {metricMode === "pressure" && (
                    <Line
                      type="monotone"
                      dataKey="homePressure"
                      name={`${match.homeTeam.shortName} Pressão`}
                      stroke="#10b981"
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 5, fill: "#10b981" }}
                    />
                  )}

                  {metricMode === "chances" && (
                    <Line
                      type="stepAfter"
                      dataKey="homeChances"
                      name={`${match.homeTeam.shortName} Chances Claras`}
                      stroke="#10b981"
                      strokeWidth={3}
                      dot={{ r: 3, fill: "#10b981" }}
                      activeDot={{ r: 6 }}
                    />
                  )}

                  {metricMode === "xg" && (
                    <Line
                      type="monotone"
                      dataKey="homeXg"
                      name={`${match.homeTeam.shortName} xG`}
                      stroke="#10b981"
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 5 }}
                    />
                  )}

                  {metricMode === "combined" && (
                    <>
                      <Line
                        type="monotone"
                        dataKey="homePressure"
                        name={`${match.homeTeam.shortName} Pressão`}
                        stroke="#10b981"
                        strokeWidth={2.2}
                        dot={false}
                      />
                      <Line
                        type="stepAfter"
                        dataKey="homeChances"
                        name={`${match.homeTeam.shortName} CC`}
                        stroke="#34d399"
                        strokeWidth={1.8}
                        strokeDasharray="3 3"
                        dot={{ r: 2 }}
                      />
                    </>
                  )}

                  {/* Goals reference markers for home */}
                  {events.filter((e) => e.type === "goal" && e.team === "home").map((g, idx) => (
                    <ReferenceDot
                      key={idx}
                      x={g.minute}
                      y={metricMode === "xg" ? Math.max(0.2, stats.xG.home * 0.7) : 80}
                      r={6}
                      fill="#10b981"
                      stroke="#ffffff"
                      strokeWidth={1.5}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* CHART 2: VISITANTE (AWAY TEAM) */}
          <div className="bg-slate-950/80 rounded-2xl border border-slate-800/90 p-4 shadow-inner">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2 px-1">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 ring-4 ring-cyan-500/20 animate-pulse" />
                <span className="text-xs font-black uppercase tracking-wider text-cyan-400">
                  {match.awayTeam.name}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 font-bold uppercase">
                  Visitante
                </span>
              </div>

              <div className="flex items-center gap-3 text-[11px] font-mono">
                <span className="text-slate-400">
                  Pressão Atual: <strong className="text-cyan-400">{match.stats.pressureIndex.away}%</strong>
                </span>
                <span className="text-slate-400">
                  CC: <strong className="text-amber-300">{stats.bigChances?.away ?? Math.max(0, Math.floor(stats.shotsOnTarget.away / 2))}</strong>
                </span>
                <span className="text-slate-400">
                  xG: <strong className="text-purple-300">{stats.xG.away.toFixed(2)}</strong>
                </span>
                <span className="text-slate-500 hidden sm:inline">
                  Pico: <strong className="text-cyan-300">{peakAway.awayPressure}%</strong> ({peakAway.minute}')
                </span>
              </div>
            </div>

            <div className="h-48 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={processedData}
                  margin={{ top: 10, right: 15, left: -10, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="awayPressureGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="minute"
                    stroke="#64748b"
                    fontSize={10}
                    tickFormatter={(v) => `${v}'`}
                  />
                  <YAxis
                    stroke="#64748b"
                    fontSize={10}
                    domain={metricMode === "xg" ? [0, "auto"] : [0, 100]}
                    tickFormatter={(v) => metricMode === "xg" ? v.toFixed(1) : `${v}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        const awayGoal = events.find((e) => e.minute === data.minute && e.type === "goal" && e.team === "away");
                        return (
                          <div className="bg-slate-950/95 border border-cyan-500/40 p-2.5 rounded-xl shadow-2xl text-xs space-y-1 backdrop-blur-md">
                            <div className="font-bold text-white flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                              <span className="text-cyan-400 font-semibold">{match.awayTeam.name}</span>
                              <span className="font-mono text-slate-300">{data.minute}'</span>
                            </div>
                            <div className="text-slate-200 space-y-0.5 pt-0.5">
                              <div>Pressão Ofensiva: <strong className="text-cyan-400">{data.awayPressure}%</strong></div>
                              <div>Chances Claras: <strong className="text-amber-300">{data.awayChances}</strong></div>
                              <div>xG Acumulado: <strong className="text-purple-300">{data.awayXg}</strong></div>
                            </div>
                            {awayGoal && (
                              <div className="text-[10px] text-cyan-300 bg-cyan-950/60 p-1 rounded font-bold border border-cyan-500/30">
                                ⚽ GOL de {awayGoal.player || match.awayTeam.name}!
                              </div>
                            )}
                          </div>
                        );
                      }
                      return null;
                    }}
                  />

                  {metricMode === "pressure" || metricMode === "combined" ? (
                    <>
                      <ReferenceLine y={50} stroke="#334155" strokeDasharray="3 3" />
                      <ReferenceLine
                        y={75}
                        stroke="#06b6d4"
                        strokeDasharray="2 2"
                        opacity={0.5}
                        label={{ value: "Crítica (75%)", fill: "#06b6d4", fontSize: 9, position: "insideTopLeft" }}
                      />
                    </>
                  ) : null}

                  {metricMode === "pressure" && (
                    <Line
                      type="monotone"
                      dataKey="awayPressure"
                      name={`${match.awayTeam.shortName} Pressão`}
                      stroke="#06b6d4"
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 5, fill: "#06b6d4" }}
                    />
                  )}

                  {metricMode === "chances" && (
                    <Line
                      type="stepAfter"
                      dataKey="awayChances"
                      name={`${match.awayTeam.shortName} Chances Claras`}
                      stroke="#06b6d4"
                      strokeWidth={3}
                      dot={{ r: 3, fill: "#06b6d4" }}
                      activeDot={{ r: 6 }}
                    />
                  )}

                  {metricMode === "xg" && (
                    <Line
                      type="monotone"
                      dataKey="awayXg"
                      name={`${match.awayTeam.shortName} xG`}
                      stroke="#06b6d4"
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 5 }}
                    />
                  )}

                  {metricMode === "combined" && (
                    <>
                      <Line
                        type="monotone"
                        dataKey="awayPressure"
                        name={`${match.awayTeam.shortName} Pressão`}
                        stroke="#06b6d4"
                        strokeWidth={2.2}
                        dot={false}
                      />
                      <Line
                        type="stepAfter"
                        dataKey="awayChances"
                        name={`${match.awayTeam.shortName} CC`}
                        stroke="#38bdf8"
                        strokeWidth={1.8}
                        strokeDasharray="3 3"
                        dot={{ r: 2 }}
                      />
                    </>
                  )}

                  {/* Goals reference markers for away */}
                  {events.filter((e) => e.type === "goal" && e.team === "away").map((g, idx) => (
                    <ReferenceDot
                      key={idx}
                      x={g.minute}
                      y={metricMode === "xg" ? Math.max(0.2, stats.xG.away * 0.7) : 80}
                      r={6}
                      fill="#06b6d4"
                      stroke="#ffffff"
                      strokeWidth={1.5}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Analytical KPI Cards footer */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 pt-2 text-xs">
        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-medium">Pico de Pressão Mandante</span>
          <span className="text-sm font-bold text-emerald-400">
            {peakHome.homePressure}% <span className="text-xs text-slate-500 font-normal">aos {peakHome.minute}'</span>
          </span>
        </div>

        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-medium">Pico de Pressão Visitante</span>
          <span className="text-sm font-bold text-cyan-400">
            {peakAway.awayPressure}% <span className="text-xs text-slate-500 font-normal">aos {peakAway.minute}'</span>
          </span>
        </div>

        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-medium">Chances Claras Totais</span>
          <span className="text-sm font-bold text-amber-300">
            {stats.bigChances?.home ?? Math.max(0, Math.floor(stats.shotsOnTarget.home / 2))} x{" "}
            {stats.bigChances?.away ?? Math.max(0, Math.floor(stats.shotsOnTarget.away / 2))}
          </span>
        </div>

        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <span className="text-[10px] text-slate-400 block font-medium">Ataques Perigosos / Minuto</span>
          <span className="text-sm font-bold text-slate-200">
            {((stats.dangerousAttacks.home + stats.dangerousAttacks.away) / Math.max(1, match.minute)).toFixed(2)} apm
          </span>
        </div>

        <div className={`p-3 rounded-xl border col-span-2 sm:col-span-1 ${
          last5MinStats.variationPct > 0
            ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
            : last5MinStats.variationPct < 0
            ? "bg-rose-950/30 border-rose-500/40 text-rose-300"
            : "bg-slate-950 border-slate-800 text-slate-300"
        }`}>
          <span className="text-[10px] text-slate-400 block font-medium">Δ Chances (Últimos 5')</span>
          <span className={`text-sm font-black font-mono flex items-center gap-1 ${
            last5MinStats.variationPct > 0 ? "text-emerald-400" : last5MinStats.variationPct < 0 ? "text-rose-400" : "text-slate-300"
          }`}>
            {last5MinStats.variationPct > 0 ? `+${last5MinStats.variationPct}%` : `${last5MinStats.variationPct}%`}
            {last5MinStats.variationPct > 0 ? (
              <TrendingUp className="w-3.5 h-3.5" />
            ) : last5MinStats.variationPct < 0 ? (
              <TrendingDown className="w-3.5 h-3.5" />
            ) : null}
          </span>
        </div>
      </div>
    </div>
  );
}
