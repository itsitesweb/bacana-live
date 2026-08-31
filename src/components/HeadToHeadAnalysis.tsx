import React, { useState, useEffect } from "react";
import { Match, HeadToHeadMatch, HeadToHeadSummary } from "../types";
import {
  History,
  TrendingUp,
  Award,
  Flame,
  Target,
  Flag,
  Shield,
  Calendar,
  Sparkles,
  RefreshCw,
  Info,
  CheckCircle2,
} from "lucide-react";

interface HeadToHeadAnalysisProps {
  match: Match;
}

export function HeadToHeadAnalysis({ match }: HeadToHeadAnalysisProps) {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [h2hData, setH2hData] = useState<{
    summary: HeadToHeadSummary;
    matches: HeadToHeadMatch[];
  } | null>(match.h2h || null);

  // If match changes or h2h is updated, sync state
  useEffect(() => {
    if (match.h2h) {
      setH2hData(match.h2h);
    }
  }, [match.id, match.h2h]);

  const handleRefreshH2H = async () => {
    setIsLoading(true);
    try {
      // Simulate/fetch latest H2H data from backend
      const res = await fetch(`/api/matches/${match.id}`);
      if (res.ok) {
        const data = await res.json();
        const m = data.match || data;
        if (m && m.h2h) {
          setH2hData(m.h2h);
        }
      }
    } catch (err) {
      console.error("Erro ao buscar histórico H2H:", err);
    } finally {
      setTimeout(() => setIsLoading(false), 500);
    }
  };

  if (!h2hData) {
    return (
      <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 text-center text-slate-400 text-xs">
        <History className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        Carregando histórico de confrontos diretos entre {match.homeTeam.name} e {match.awayTeam.name}...
      </div>
    );
  }

  const { summary, matches: pastMatches } = h2hData;
  const homeWinPct = Math.round((summary.homeWins / summary.totalMatches) * 100);
  const drawPct = Math.round((summary.draws / summary.totalMatches) * 100);
  const awayWinPct = Math.round((summary.awayWins / summary.totalMatches) * 100);

  return (
    <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-5 shadow-xl space-y-5">
      {/* Header with Title and Refresh button */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <History className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              Histórico de Confrontos Diretos (H2H) & Tendências
            </h3>
            <p className="text-xs text-slate-400">
              Retrospecto recente entre {match.homeTeam.name} e {match.awayTeam.name} ({summary.totalMatches} jogos analisados)
            </p>
          </div>
        </div>

        <button
          onClick={handleRefreshH2H}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1.5 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-emerald-400" : ""}`} />
          <span>{isLoading ? "Buscando..." : "Atualizar"}</span>
        </button>
      </div>

      {/* Dominant Trend Insight Highlight Box */}
      <div className="bg-gradient-to-r from-amber-950/40 via-slate-950 to-slate-900 p-4 rounded-xl border border-amber-500/30 flex items-start gap-3">
        <Sparkles className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1 text-xs">
          <span className="font-extrabold text-amber-300 uppercase tracking-wide text-[11px] block">
            Tendência Principal de Confronto
          </span>
          <p className="text-slate-200 leading-relaxed font-medium">
            {summary.dominantTrendInsight}
          </p>
        </div>
      </div>

      {/* Win/Draw/Loss Balance Bar */}
      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            <span className="font-bold text-slate-200">{match.homeTeam.shortName}</span>
            <span className="text-emerald-400 font-extrabold">({summary.homeWins}V - {homeWinPct}%)</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500"></span>
            <span className="font-bold text-slate-400">Empates</span>
            <span className="text-slate-300 font-extrabold">({summary.draws}E - {drawPct}%)</span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-500"></span>
            <span className="font-bold text-slate-200">{match.awayTeam.shortName}</span>
            <span className="text-cyan-400 font-extrabold">({summary.awayWins}V - {awayWinPct}%)</span>
          </div>
        </div>

        {/* Triple Segmented Progress Bar */}
        <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden flex gap-0.5">
          <div
            className="h-full bg-emerald-500 transition-all duration-500 hover:opacity-90"
            style={{ width: `${homeWinPct}%` }}
            title={`Vitórias ${match.homeTeam.name}: ${homeWinPct}%`}
          />
          <div
            className="h-full bg-slate-600 transition-all duration-500 hover:opacity-90"
            style={{ width: `${drawPct}%` }}
            title={`Empates: ${drawPct}%`}
          />
          <div
            className="h-full bg-cyan-500 transition-all duration-500 hover:opacity-90"
            style={{ width: `${awayWinPct}%` }}
            title={`Vitórias ${match.awayTeam.name}: ${awayWinPct}%`}
          />
        </div>
      </div>

      {/* Trend Key Statistics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        {/* 1. Média de Gols */}
        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] uppercase font-bold tracking-wider">Média de Gols</span>
            <Target className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-white">{summary.avgGoalsPerGame}</span>
            <span className="text-[10px] text-slate-400">/jogo</span>
          </div>
        </div>

        {/* 2. Ambas Marcam (BTTS) */}
        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] uppercase font-bold tracking-wider">Ambas Marcam</span>
            <Flame className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-amber-300">{summary.bttsPercentage}%</span>
            <span className="text-[10px] text-slate-400">dos jogos</span>
          </div>
        </div>

        {/* 3. Over 2.5 Gols */}
        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] uppercase font-bold tracking-wider">Over 2.5 Gols</span>
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-black text-cyan-300">{summary.over25Percentage}%</span>
            <span className="text-[10px] text-slate-400">frequência</span>
          </div>
        </div>

        {/* 4. Média de Escanteios & Cartões */}
        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-[10px] uppercase font-bold tracking-wider">Cantos & Cartões</span>
            <Flag className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-xl font-black text-purple-300">{summary.avgCornersPerGame}</span>
            <span className="text-[10px] text-slate-400">cantos | {summary.avgCardsPerGame} cartões</span>
          </div>
        </div>
      </div>

      {/* List of Recent Direct Matchups */}
      <div className="space-y-2.5">
        <span className="text-xs font-extrabold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5 text-emerald-400" />
          Últimos Confrontos Diretos
        </span>

        <div className="space-y-2">
          {pastMatches.map((m) => {
            const isHomeWinner = m.winner === "home";
            const isAwayWinner = m.winner === "away";
            const isDraw = m.winner === "draw";

            return (
              <div
                key={m.id}
                className="bg-slate-950 hover:bg-slate-900/90 p-3 rounded-xl border border-slate-800/90 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs"
              >
                {/* Competition and Date */}
                <div className="flex items-center gap-2 sm:w-48 shrink-0">
                  <span className="text-[10px] font-mono text-slate-400">{m.date}</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 truncate max-w-[120px]">
                    {typeof m.competition === 'object' && m.competition !== null ? (m.competition as any).name || (m.competition as any).title || 'Copa' : String(m.competition || 'Copa')}
                  </span>
                </div>

                {/* Score & Teams */}
                <div className="flex items-center justify-center gap-3 flex-1">
                  <span
                    className={`font-bold truncate text-right flex-1 ${
                      m.homeScore > m.awayScore ? "text-emerald-400 font-black" : "text-slate-300"
                    }`}
                  >
                    {m.homeTeamName}
                  </span>

                  {/* Score Pill */}
                  <div className="bg-slate-900 px-3 py-1 rounded-lg border border-slate-700 font-mono font-black text-sm text-white shadow-inner">
                    {m.homeScore} - {m.awayScore}
                  </div>

                  <span
                    className={`font-bold truncate text-left flex-1 ${
                      m.awayScore > m.homeScore ? "text-cyan-400 font-black" : "text-slate-300"
                    }`}
                  >
                    {m.awayTeamName}
                  </span>
                </div>

                {/* Match Stats / Winner Badge */}
                <div className="flex items-center justify-end gap-2 text-[11px] sm:w-44 shrink-0 text-slate-400">
                  {m.totalCorners && (
                    <span className="text-[10px] text-slate-400" title="Escanteios">
                      🚩 {m.totalCorners} cantos
                    </span>
                  )}
                  <span
                    className={`px-2 py-0.5 rounded-full font-bold text-[10px] uppercase border ${
                      isDraw
                        ? "bg-slate-800 text-slate-300 border-slate-700"
                        : isHomeWinner
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : "bg-cyan-500/10 text-cyan-400 border-cyan-500/30"
                    }`}
                  >
                    {isDraw ? "Empate" : isHomeWinner ? `Vitória ${m.homeTeamName}` : `Vitória ${m.awayTeamName}`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
