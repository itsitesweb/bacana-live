import React, { useEffect, useState } from "react";
import { X, ExternalLink, Activity, Sparkles, Trophy } from "lucide-react";

export interface GoalEventData {
  id: string;
  matchId: string;
  homeTeam: string;
  awayTeam: string;
  scoringTeam: string;
  minute: number;
  newScore: string;
  league: string;
  country?: string;
  timestamp: number;
}

interface GoalAlertPopupProps {
  goals: GoalEventData[];
  onDismiss: (id: string) => void;
  onSelectMatch: (matchId: string) => void;
}

export function GoalAlertPopup({ goals, onDismiss, onSelectMatch }: GoalAlertPopupProps) {
  if (!goals || goals.length === 0) return null;

  return (
    <div
      id="goal-alert-popup-container"
      className="fixed top-20 right-4 z-50 flex flex-col gap-3 max-w-sm sm:max-w-md w-full pointer-events-none"
    >
      {goals.map((goal) => (
        <SingleGoalToast
          key={goal.id}
          goal={goal}
          onDismiss={() => onDismiss(goal.id)}
          onSelectMatch={() => {
            onSelectMatch(goal.matchId);
            onDismiss(goal.id);
          }}
        />
      ))}
    </div>
  );
}

interface SingleGoalToastProps {
  key?: string;
  goal: GoalEventData;
  onDismiss: () => void;
  onSelectMatch: () => void;
}

function SingleGoalToast({
  goal,
  onDismiss,
  onSelectMatch,
}: SingleGoalToastProps) {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    const duration = 8000; // 8 seconds
    const interval = 100;
    const step = (interval / duration) * 100;

    const timer = setInterval(() => {
      setProgress((prev) => {
        if (prev <= step) {
          clearInterval(timer);
          onDismiss();
          return 0;
        }
        return prev - step;
      });
    }, interval);

    return () => clearInterval(timer);
  }, [onDismiss]);

  return (
    <div
      id={`goal-toast-${goal.id}`}
      className="pointer-events-auto bg-gradient-to-br from-slate-900 via-emerald-950/90 to-slate-900 border-2 border-emerald-400/90 rounded-2xl p-4 shadow-[0_0_40px_rgba(16,185,129,0.5)] text-white relative overflow-hidden backdrop-blur-md animate-in fade-in slide-in-from-top-4 duration-300 transform transition-all hover:scale-[1.02]"
    >
      {/* Top flashing glowing line */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-400 via-emerald-400 to-amber-400 animate-pulse" />

      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 rounded-full bg-emerald-500/20 border border-emerald-400 items-center justify-center text-lg shadow-[0_0_15px_rgba(16,185,129,0.8)] animate-bounce">
            ⚽
          </span>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-black tracking-widest uppercase text-emerald-300">
                GOL CONFIRMADO!
              </span>
              <span className="text-[10px] font-extrabold bg-emerald-500 text-slate-950 px-1.5 py-0.5 rounded font-mono">
                {goal.minute > 0 ? `${goal.minute}'` : "AO VIVO"}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 truncate max-w-[200px]">
              {goal.country ? `${goal.country} • ` : ""}{goal.league}
            </p>
          </div>
        </div>

        <button
          id={`btn-close-goal-toast-${goal.id}`}
          onClick={onDismiss}
          className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          title="Fechar alerta de gol"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Main Goal Details */}
      <div className="bg-slate-950/70 border border-emerald-500/30 rounded-xl p-2.5 mb-3">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-xs font-extrabold text-white truncate">
            {goal.scoringTeam}
          </span>
          <span className="text-sm font-black font-mono text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-500/50">
            {goal.newScore}
          </span>
        </div>
        <p className="text-[11px] text-slate-300 truncate">
          {goal.homeTeam} x {goal.awayTeam}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between gap-2">
        <button
          id={`btn-view-goal-match-${goal.id}`}
          onClick={onSelectMatch}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black text-xs rounded-xl shadow-md shadow-emerald-950/40 transition active:scale-95"
        >
          <span>Ver Partida</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Progress Bar (Auto-dismiss) */}
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-800">
        <div
          className="h-full bg-emerald-400 transition-all duration-100 ease-linear"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
