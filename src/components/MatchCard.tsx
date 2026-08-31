import React from "react";
import { Match, MatchRulesAnalysis } from "../types";
import { Zap, Flame, ShieldAlert, Sparkles, GripVertical, ChevronLeft, ChevronRight, Trash2, ExternalLink } from "lucide-react";
import { getFlashscoreUrl } from "../utils/flashscore";
import { getLivePressure5Min } from "../utils/pressure";

interface MatchCardProps {
  key?: React.Key;
  match: Match;
  isSelected: boolean;
  onSelect: () => void;
  rulesAnalysis?: MatchRulesAnalysis;
  ratioConfigured?: number;
  onMoveLeft?: (e: React.MouseEvent) => void;
  onMoveRight?: (e: React.MouseEvent) => void;
  onDeleteMatch?: (e: React.MouseEvent) => void;
  canMoveLeft?: boolean;
  canMoveRight?: boolean;
  isDraggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  onDragEnd?: (e: React.DragEvent) => void;
  isBeingDragged?: boolean;
  isFlashingGoal?: boolean;
}

export function MatchCard({
  match,
  isSelected,
  onSelect,
  ratioConfigured = 3.0,
  onMoveLeft,
  onMoveRight,
  onDeleteMatch,
  canMoveLeft = false,
  canMoveRight = false,
  isDraggable = true,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isBeingDragged = false,
  isFlashingGoal = false,
}: MatchCardProps) {
  const isLive = match.status === "1H" || match.status === "2H" || match.status === "LIVE";
  const { home: homePressure, away: awayPressure, dominanceText } = getLivePressure5Min(
    match.stats,
    match.minute,
    match.momentumTimeline
  );

  const homeCc = match.stats.bigChances?.home ?? Math.max(0, Math.floor(match.stats.shotsOnTarget.home / 2));
  const awayCc = match.stats.bigChances?.away ?? Math.max(0, Math.floor(match.stats.shotsOnTarget.away / 2));
  const totalCc = homeCc + awayCc;

  // Standard clean border & background styling or intense flash on Goal
  const cardBorderClasses = isFlashingGoal
    ? "bg-emerald-950/70 border-emerald-400 ring-4 ring-emerald-400 shadow-[0_0_40px_rgba(16,185,129,0.9)] animate-pulse"
    : isSelected
    ? "bg-slate-800/95 border-emerald-500/80 shadow-lg shadow-emerald-950/40 ring-1 ring-emerald-500/50"
    : "bg-slate-900/80 border-slate-800 hover:border-slate-700 hover:bg-slate-850";

  return (
    <div
      draggable={isDraggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      className={`p-3.5 sm:p-4 rounded-2xl cursor-pointer transition-all duration-200 border relative overflow-hidden flex flex-col justify-between select-none ${
        isBeingDragged ? "opacity-40 scale-95 border-dashed border-emerald-400" : ""
      } ${cardBorderClasses}`}
    >
      {/* Flashing Goal Banner if active */}
      {isFlashingGoal && (
        <div className="mb-2 py-1 px-2.5 rounded-lg bg-emerald-500 text-slate-950 font-black text-xs flex items-center justify-between shadow-lg shadow-emerald-950/60 animate-bounce">
          <span className="flex items-center gap-1.5">
            <span className="text-sm">⚽</span>
            <span className="tracking-wide">GOL CONFIRMADO!</span>
          </span>
          <span className="font-mono text-[11px] bg-slate-950 text-emerald-300 px-2 py-0.5 rounded font-black border border-emerald-400/40">
            {match.score.home} - {match.score.away}
          </span>
        </div>
      )}

      {/* Card Header: Toolbar buttons on top bar, followed by 100% width Country, League, and Start Time */}
      <div>
        {/* Top Control Bar: Action Buttons & Live Status */}
        <div className="flex items-center justify-between gap-1.5 mb-2 relative z-10">
          <div className="flex items-center gap-1 min-w-0">
            <span
              title="Arraste para reposicionar o card"
              className="cursor-grab active:cursor-grabbing text-slate-600 hover:text-slate-300 p-0.5"
            >
              <GripVertical className="w-3.5 h-3.5" />
            </span>

            {/* Quick Reorder Controls (Move Left / Move Right) */}
            {onMoveLeft && canMoveLeft && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onMoveLeft(e);
                }}
                title="Mover card para esquerda"
                className="p-1 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition"
              >
                <ChevronLeft className="w-3 h-3" />
              </button>
            )}
            {onMoveRight && canMoveRight && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onMoveRight(e);
                }}
                title="Mover card para direita"
                className="p-1 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition"
              >
                <ChevronRight className="w-3 h-3" />
              </button>
            )}

            {onDeleteMatch && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteMatch(e);
                }}
                title="Apagar jogo (ocultar informações e alertas nesta sessão do crawler)"
                className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-500/30 transition"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}

            {/* FlashScore Link */}
            <a
              href={getFlashscoreUrl(match)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="Abrir partida no FlashScore"
              className="p-1 rounded text-cyan-400 hover:text-cyan-200 hover:bg-cyan-950/40 border border-cyan-500/20 hover:border-cyan-500/50 transition"
            >
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* Status Badge */}
          <div className="shrink-0">
            {(() => {
              const statusUpper = (match.status || "").toUpperCase();
              if (statusUpper === "HT" || statusUpper === "INTERVALO") {
                return (
                  <span className="flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    INT (45')
                  </span>
                );
              }
              if (statusUpper === "FT" || statusUpper === "FINISHED" || statusUpper === "ENCERRADO") {
                return (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700">
                    FT
                  </span>
                );
              }
              if (isLive) {
                const minDisplay = match.minute ? `${match.minute}'` : "AO VIVO";
                return (
                  <span className="flex items-center gap-1 text-[11px] font-extrabold px-2 py-0.5 rounded-md bg-rose-500/15 text-rose-400 border border-rose-500/30">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping"></span>
                    {minDisplay}
                  </span>
                );
              }
              return (
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300">
                  {match.status || "AGENDADO"}
                </span>
              );
            })()}
          </div>
        </div>

        {/* 100% Width Country, League & Time Header */}
        <div className="w-full min-w-0 flex flex-col gap-0.5 mb-2.5 pb-2 border-b border-slate-800/80">
          {/* Linha 1: País */}
          {match.country && (
            <span className="text-[10px] font-black text-emerald-400 uppercase tracking-wide truncate w-full block">
              {typeof match.country === 'object' && match.country !== null ? (match.country as any).name || 'País' : String(match.country)}
            </span>
          )}
          {/* Linha 2: Liga */}
          <span className="text-[11px] font-bold text-slate-100 uppercase tracking-tight truncate w-full block">
            {typeof match.league === 'object' && match.league !== null ? (match.league as any).name || 'Liga' : String(match.league || '')}
          </span>
          {/* Linha 3: Horário oficial de início da partida */}
          {(() => {
            let timeStr = match.startTime || "";
            if (!timeStr && match.startDate) {
              try {
                const d = new Date(match.startDate);
                if (!isNaN(d.getTime())) {
                  timeStr = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
                }
              } catch {
                timeStr = "";
              }
            }
            return timeStr ? (
              <span className="text-[9.5px] text-slate-400 font-mono leading-tight truncate w-full block">
                Início: {timeStr}
              </span>
            ) : null;
          })()}
        </div>

        {/* Teams and Score Grid */}
        <div className="space-y-1.5 mb-2.5">
          {/* Home Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-sm">{match.homeTeam.logo}</span>
              <span className="text-xs sm:text-sm font-bold text-white truncate">
                {match.homeTeam.name}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {homePressure >= 75 && (
                <span title="Pressão Alta Mandante" className="text-[9px] text-amber-400">
                  🔥
                </span>
              )}
              <span className="text-base font-black text-white w-5 text-right font-mono">
                {match.score?.home ?? (match.homeTeam as any)?.score ?? 0}
              </span>
            </div>
          </div>

          {/* Away Team */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-sm">{match.awayTeam.logo}</span>
              <span className="text-xs sm:text-sm font-bold text-white truncate">
                {match.awayTeam.name}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {awayPressure >= 75 && (
                <span title="Pressão Alta Visitante" className="text-[9px] text-cyan-400">
                  🔥
                </span>
              )}
              <span className="text-base font-black text-white w-5 text-right font-mono">
                {match.score?.away ?? (match.awayTeam as any)?.score ?? 0}
              </span>
            </div>
          </div>
        </div>

        {/* Pressure Mini-Meter (Últimos 5 Minutos) */}
        <div className="mb-2.5 p-1.5 rounded-xl bg-slate-950/80 border border-slate-800/90 shadow-inner" title={`Pressão Últimos 5 Min: Mandante ${homePressure}% vs Visitante ${awayPressure}% - ${dominanceText}`}>
          <div className="flex items-center justify-between text-[9.5px] mb-1 font-semibold">
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span className="text-emerald-300 font-black font-mono">{homePressure}%</span>
            </div>
            <span className="text-[8px] uppercase tracking-wider text-amber-300 font-extrabold px-1.5 py-0.2 rounded bg-slate-900 border border-slate-700/80 shadow-sm">
              Pressão 5'
            </span>
            <div className="flex items-center gap-1">
              <span className="text-orange-300 font-black font-mono">{awayPressure}%</span>
              <span className="w-1.5 h-1.5 rounded-full bg-orange-400"></span>
            </div>
          </div>
          <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden flex border border-slate-800 shadow-inner">
            <div
              className="bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-300 shadow-[0_0_6px_rgba(16,185,129,0.5)]"
              style={{ width: `${(homePressure / (homePressure + awayPressure || 1)) * 100}%` }}
            />
            <div
              className="bg-gradient-to-r from-orange-400 to-orange-500 transition-all duration-300 shadow-[0_0_6px_rgba(249,115,22,0.5)]"
              style={{ width: `${(awayPressure / (homePressure + awayPressure || 1)) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Quick stats footer with CC (Chances Claras) */}
      <div className="grid grid-cols-4 gap-1 text-center pt-2 border-t border-slate-800/80 text-[9px] text-slate-400 relative z-10">
        <div
          className="p-0.5 rounded"
          title={`Total: ${totalCc} Chances Claras (Índice: ${ratioConfigured} CC/Gol)`}
        >
          <span className="block text-slate-400">
            CC
          </span>
          <span className="font-black text-amber-400">
            {homeCc}-{awayCc}
          </span>
        </div>
        <div className="p-0.5">
          <span className="text-slate-400 block">xG</span>
          <span className="font-semibold text-slate-200">
            {match.stats.xG.home.toFixed(1)}-{match.stats.xG.away.toFixed(1)}
          </span>
        </div>
        <div className="p-0.5">
          <span className="text-slate-400 block">Chutes</span>
          <span className="font-semibold text-slate-200">
            {match.stats.shotsOnTarget.home}-{match.stats.shotsOnTarget.away}
          </span>
        </div>
        <div className="p-0.5">
          <span className="text-slate-400 block">Cantos</span>
          <span className="font-semibold text-slate-200">
            {match.stats.corners.home}-{match.stats.corners.away}
          </span>
        </div>
      </div>
    </div>
  );
}

