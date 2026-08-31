import React, { useState, useMemo } from "react";
import { AlertRule, AlertLog, AlertMetric, AlertOperator, AlertSeverity, Match, OperationalRulesConfig } from "../types";
import {
  Bell,
  Plus,
  Trash2,
  CheckCircle,
  AlertTriangle,
  Flame,
  ShieldAlert,
  Volume2,
  Sparkles,
  Search,
  Filter,
  Check,
  Zap,
  Info,
  SlidersHorizontal,
  Target,
  TrendingUp,
  Sliders,
  Eye,
  EyeOff,
  Radio,
  RotateCcw,
  CheckSquare,
  Square,
  Layers,
  Key,
  Building2,
  ExternalLink,
} from "lucide-react";
import { soundEffects } from "./AudioAlertService";
import { getFlashscoreUrl } from "../utils/flashscore";

interface AlertsManagerProps {
  rules: AlertRule[];
  logs: AlertLog[];
  matches: Match[];
  rulesConfig?: OperationalRulesConfig | null;
  onUpdateRulesConfig?: (config: OperationalRulesConfig) => Promise<void>;
  onSaveRule: (rule: AlertRule) => Promise<void>;
  onDeleteRule: (id: string) => Promise<void>;
  onDeleteAlert?: (id: string) => Promise<void>;
  onMarkAsRead: () => Promise<void>;
  onClearLogs: () => Promise<void>;
  onTriggerTestAlert: (severity: AlertSeverity) => void;
  onSelectMatch?: (matchId: string) => void;
}

export type AlertTypeCategory =
  | "imminent_goal"
  | "back_dominant"
  | "triple_debt"
  | "goal_debt_over"
  | "pressao_blitz"
  | "corners"
  | "cards"
  | "btts_ambas"
  | "under_value"
  | "virada_turnaround"
  | "cashout";

interface CategoryMeta {
  id: AlertTypeCategory;
  name: string;
  shortDesc: string;
  icon: React.ReactNode;
  colorClass: string;
  badgeBg: string;
}

const ALERT_CATEGORIES: CategoryMeta[] = [
  {
    id: "imminent_goal",
    name: "Gol Iminente (Surto 5m)",
    shortDesc: "Variação brusca (+50% em 5') + Dívida ativa de gols",
    icon: <Zap className="w-4 h-4 text-emerald-400 animate-pulse" />,
    colorClass: "text-emerald-400 border-emerald-500/40",
    badgeBg: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  },
  {
    id: "back_dominant",
    name: "Back Dominante (3.1.2)",
    shortDesc: "Back Premium, Back Forte e Dominante Devendo",
    icon: <Target className="w-4 h-4 text-emerald-400" />,
    colorClass: "text-emerald-400 border-emerald-500/30",
    badgeBg: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  },
  {
    id: "triple_debt",
    name: "Trinca de Dívidas",
    shortDesc: "Convergência CC + xG + xGOT com atraso de gols",
    icon: <Sparkles className="w-4 h-4 text-purple-400" />,
    colorClass: "text-purple-400 border-purple-500/30",
    badgeBg: "bg-purple-500/10 text-purple-300 border-purple-500/20",
  },
  {
    id: "goal_debt_over",
    name: "Gol Devendo / Over",
    shortDesc: "Gol Muito Devendo, Over Premium e Bilateral",
    icon: <Flame className="w-4 h-4 text-amber-400" />,
    colorClass: "text-amber-400 border-amber-500/30",
    badgeBg: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  },
  {
    id: "corners",
    name: "Cantos & Funil Limite",
    shortDesc: "Funil de Cantos HT/FT e Race to Corners",
    icon: <TrendingUp className="w-4 h-4 text-cyan-400" />,
    colorClass: "text-cyan-400 border-cyan-500/30",
    badgeBg: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20",
  },
  {
    id: "cards",
    name: "Cartões & Expulsão",
    shortDesc: "Jogo Quente, Over Cartões e Risco de Vermelho",
    icon: <ShieldAlert className="w-4 h-4 text-rose-400" />,
    colorClass: "text-rose-400 border-rose-500/30",
    badgeBg: "bg-rose-500/10 text-rose-300 border-rose-500/20",
  },
  {
    id: "btts_ambas",
    name: "Ambas Marcam (BTTS)",
    shortDesc: "Volume bilateral alto e xG mútuo elevado",
    icon: <Target className="w-4 h-4 text-teal-400" />,
    colorClass: "text-teal-400 border-teal-500/30",
    badgeBg: "bg-teal-500/10 text-teal-300 border-teal-500/20",
  },
  {
    id: "under_value",
    name: "Under Value",
    shortDesc: "Ritmo travado e valor em Under Gols / Lay",
    icon: <ShieldAlert className="w-4 h-4 text-indigo-400" />,
    colorClass: "text-indigo-400 border-indigo-500/30",
    badgeBg: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20",
  },
  {
    id: "virada_turnaround",
    name: "Virada Improvável",
    shortDesc: "Favorito perdendo sob pressão absurda (DNB)",
    icon: <Zap className="w-4 h-4 text-orange-400" />,
    colorClass: "text-orange-400 border-orange-500/30",
    badgeBg: "bg-orange-500/10 text-orange-300 border-orange-500/20",
  },
  {
    id: "cashout",
    name: "Cashout Proativo",
    shortDesc: "Queda brusca de ritmo do time que lidera",
    icon: <AlertTriangle className="w-4 h-4 text-rose-400" />,
    colorClass: "text-rose-400 border-rose-500/30",
    badgeBg: "bg-rose-500/10 text-rose-300 border-rose-500/20",
  },
  {
    id: "pressao_blitz",
    name: "Pressão & Ineficiência",
    shortDesc: "Pressão Extrema (+80%) e Pressão Vendável",
    icon: <Zap className="w-4 h-4 text-yellow-400" />,
    colorClass: "text-yellow-400 border-yellow-500/30",
    badgeBg: "bg-yellow-500/10 text-yellow-300 border-yellow-500/20",
  },
];

const METRIC_LABELS: Record<AlertMetric, string> = {
  minute: "Minuto da Partida",
  pressureHome: "Pressão Mandante (0-100%)",
  pressureAway: "Pressão Visitante (0-100%)",
  pressureDiff: "Diferença de Pressão (|Home - Away|)",
  xgDiff: "Diferença de xG (|Home - Away|)",
  totalXg: "xG Total Combinado",
  dangerousAttacksLast10Home: "Ataques Perigosos Mandante (Últimos 10m)",
  dangerousAttacksLast10Away: "Ataques Perigosos Visitante (Últimos 10m)",
  chancesVariation5m: "Variação de Chances nos Últimos 5m (Δ%)",
  cornersCombined: "Total de Escanteios Combinados",
  cornersHome: "Escanteios Mandante",
  cornersAway: "Escanteios Visitante",
  shotsOnTargetHome: "Chutes no Gol Mandante",
  shotsOnTargetAway: "Chutes no Gol Visitante",
  shotsOnTargetDiff: "Diferença de Chutes no Gol",
  goalLeadDiff: "Diferença no Placar (|Gols Casa - Fora|)",
  possessionHome: "Posse de Bola Mandante (%)",
  possessionAway: "Posse de Bola Visitante (%)",
  redCardHome: "Cartão Vermelho Mandante",
  redCardAway: "Cartão Vermelho Visitante",
};

function categorizeAlert(log: AlertLog): AlertTypeCategory {
  const text = `${log.ruleId} ${log.ruleName} ${log.message}`.toLowerCase();
  if (text.includes("cashout") || text.includes("tip-cashout")) {
    return "cashout";
  }
  if (text.includes("virada") || text.includes("tip-virada")) {
    return "virada_turnaround";
  }
  if (text.includes("under value") || text.includes("tip-under-value")) {
    return "under_value";
  }
  if (text.includes("ambas") || text.includes("btts") || text.includes("tip-ambas")) {
    return "btts_ambas";
  }
  if (text.includes("cartão") || text.includes("vermelho") || text.includes("expulsão") || text.includes("jogo quente") || text.includes("tip-jogo-quente") || text.includes("tip-re-") || text.includes("tip-risco-expulsao")) {
    return "cards";
  }
  if (text.includes("canto") || text.includes("escanteio") || text.includes("corner") || text.includes("funil") || text.includes("race") || text.includes("tip-fc-") || text.includes("tip-rc-")) {
    return "corners";
  }
  if (text.includes("iminente") || text.includes("imminent-goal") || text.includes("surto")) {
    return "imminent_goal";
  }
  if (text.includes("trinca") || text.includes("triple-debt")) {
    return "triple_debt";
  }
  if (text.includes("back") || text.includes("dominante")) {
    return "back_dominant";
  }
  if (text.includes("pressão vendável") || text.includes("blitz")) {
    return "pressao_blitz";
  }
  if (text.includes("over") || text.includes("devendo") || text.includes("gols em atraso") || text.includes("dívida")) {
    return "goal_debt_over";
  }
  return "goal_debt_over";
}

export function AlertsManager({
  rules,
  logs,
  matches,
  rulesConfig,
  onUpdateRulesConfig,
  onSaveRule,
  onDeleteRule,
  onDeleteAlert,
  onMarkAsRead,
  onClearLogs,
  onTriggerTestAlert,
  onSelectMatch,
}: AlertsManagerProps) {
  const [logFilter, setLogFilter] = useState<"all" | AlertSeverity>("all");
  const [searchLog, setSearchLog] = useState("");

  // Helper to check if a match has bookmaker odds coverage
  const checkOddsCoverage = (matchId?: string, rawOdds?: any) => {
    if (matchId) {
      const found = matches.find((m) => m.id === matchId);
      if (found?.odds) {
        const o = found.odds;
        if (
          (o.homeWin && o.homeWin > 1.05) ||
          (o.draw && o.draw > 1.05) ||
          (o.awayWin && o.awayWin > 1.05) ||
          (o.over25 && o.over25 > 1.05)
        ) {
          return true;
        }
      }
    }
    if (Array.isArray(rawOdds) && rawOdds.some((b: any) => Number(b.odd) > 1.05)) {
      return true;
    }
    return false;
  };

  // Helper to filter bookmakers in betting tip by active operational rules config
  const getActiveBookmakerOdds = (odds: (typeof logs)[0]["bettingTip"] extends undefined ? any : any) => {
    if (!odds || !Array.isArray(odds)) return [];
    if (!rulesConfig) return odds;

    let allowedIds: Set<string> | null = null;
    if (rulesConfig.bookmakerCredentials) {
      const active = Object.entries(rulesConfig.bookmakerCredentials)
        .filter(([_, cred]) => cred && cred.enabled !== false)
        .map(([id]) => id);
      allowedIds = new Set(active);
    } else if (Array.isArray(rulesConfig.enabledBookmakers)) {
      allowedIds = new Set(rulesConfig.enabledBookmakers);
    }

    if (!allowedIds) return odds;
    return odds.filter((bk: any) => allowedIds!.has(bk.bookmakerId));
  };

  // Helper to get total number of active bookmakers configured
  const activeBookmakersCount = useMemo(() => {
    if (!rulesConfig) return 8;
    if (rulesConfig.bookmakerCredentials) {
      return Object.values(rulesConfig.bookmakerCredentials).filter((c) => c?.enabled !== false).length;
    }
    if (Array.isArray(rulesConfig.enabledBookmakers)) {
      return rulesConfig.enabledBookmakers.length;
    }
    return 8;
  }, [rulesConfig]);
  const [isQuickConfigOpen, setIsQuickConfigOpen] = useState(false);
  const [selectedMatchFilter, setSelectedMatchFilter] = useState<string>("all");
  const [hideFinishedMatches, setHideFinishedMatches] = useState<boolean>(() => {
    try {
      const saved = sessionStorage.getItem("radar_alerts_hide_finished");
      return saved !== null ? JSON.parse(saved) : true;
    } catch {
      return true;
    }
  });
  const [mutedMatchIds, setMutedMatchIds] = useState<Record<string, boolean>>(() => {
    try {
      const saved = sessionStorage.getItem("radar_alerts_muted_matches");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });
  const [enabledCategories, setEnabledCategories] = useState<Record<AlertTypeCategory, boolean>>(() => {
    const defaultCategories: Record<AlertTypeCategory, boolean> = {
      imminent_goal: true,
      back_dominant: true,
      triple_debt: true,
      goal_debt_over: true,
      corners: true,
      cards: true,
      btts_ambas: true,
      under_value: true,
      virada_turnaround: true,
      cashout: true,
      pressao_blitz: true,
    };
    try {
      const saved = sessionStorage.getItem("radar_alerts_enabled_categories");
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...defaultCategories, ...parsed };
      }
    } catch {
      // fallback to defaults
    }
    return defaultCategories;
  });

  // Salva no sessionStorage sempre que os filtros de categoria mudarem
  React.useEffect(() => {
    try {
      sessionStorage.setItem("radar_alerts_enabled_categories", JSON.stringify(enabledCategories));
    } catch {
      // ignore quota errors
    }
  }, [enabledCategories]);

  // Salva no sessionStorage sempre que os filtros de partidas mutadas ou finalizadas mudarem
  React.useEffect(() => {
    try {
      sessionStorage.setItem("radar_alerts_muted_matches", JSON.stringify(mutedMatchIds));
    } catch {
      // ignore
    }
  }, [mutedMatchIds]);

  React.useEffect(() => {
    try {
      sessionStorage.setItem("radar_alerts_hide_finished", JSON.stringify(hideFinishedMatches));
    } catch {
      // ignore
    }
  }, [hideFinishedMatches]);

  const handleToggleCategory = (cat: AlertTypeCategory) => {
    setEnabledCategories((prev) => {
      const next = { ...prev, [cat]: !prev[cat] };
      // Sync with operational rules if available
      if (onUpdateRulesConfig && rulesConfig) {
        if (cat === "imminent_goal") {
          onUpdateRulesConfig({ ...rulesConfig, enableImminentGoal: next[cat] });
        } else if (cat === "triple_debt") {
          onUpdateRulesConfig({ ...rulesConfig, enableTripleDebt: next[cat] });
        } else if (cat === "pressao_blitz") {
          onUpdateRulesConfig({ ...rulesConfig, enablePressaoVendavel: next[cat] });
        } else if (cat === "back_dominant") {
          onUpdateRulesConfig({ ...rulesConfig, enableDominantTrailing: next[cat] });
        } else if (cat === "corners") {
          onUpdateRulesConfig({ ...rulesConfig, enableFunilCantos: next[cat], enableRaceToCorners: next[cat] });
        } else if (cat === "cards") {
          onUpdateRulesConfig({ ...rulesConfig, enableJogoQuenteCards: next[cat], enableRiscoExpulsao: next[cat] });
        } else if (cat === "btts_ambas") {
          onUpdateRulesConfig({ ...rulesConfig, enableAmbasMarcamBTTS: next[cat] });
        } else if (cat === "under_value") {
          onUpdateRulesConfig({ ...rulesConfig, enableUnderValue: next[cat] });
        } else if (cat === "virada_turnaround") {
          onUpdateRulesConfig({ ...rulesConfig, enableViradaImprovavel: next[cat] });
        } else if (cat === "cashout") {
          onUpdateRulesConfig({ ...rulesConfig, enableCashoutProativo: next[cat] });
        }
      }
      return next;
    });
  };

  const handleToggleMatchMute = (matchId: string) => {
    setMutedMatchIds((prev) => ({
      ...prev,
      [matchId]: !prev[matchId],
    }));
  };

  const handleSetAllCategories = (enabled: boolean) => {
    setEnabledCategories({
      imminent_goal: enabled,
      back_dominant: enabled,
      triple_debt: enabled,
      goal_debt_over: enabled,
      corners: enabled,
      cards: enabled,
      btts_ambas: enabled,
      under_value: enabled,
      virada_turnaround: enabled,
      cashout: enabled,
      pressao_blitz: enabled,
    });
    if (onUpdateRulesConfig && rulesConfig) {
      onUpdateRulesConfig({
        ...rulesConfig,
        enableImminentGoal: enabled,
        enableTripleDebt: enabled,
        enablePressaoVendavel: enabled,
        enableDominantTrailing: enabled,
        enableFunilCantos: enabled,
        enableRaceToCorners: enabled,
        enableJogoQuenteCards: enabled,
        enableRiscoExpulsao: enabled,
        enableAmbasMarcamBTTS: enabled,
        enableUnderValue: enabled,
        enableViradaImprovavel: enabled,
        enableCashoutProativo: enabled,
      });
    }
  };

  const handleApplyPreset = (preset: "all" | "debts_only" | "critical_only") => {
    if (preset === "all") {
      handleSetAllCategories(true);
    } else if (preset === "debts_only") {
      setEnabledCategories({
        imminent_goal: true,
        back_dominant: true,
        triple_debt: true,
        goal_debt_over: true,
        corners: false,
        cards: false,
        btts_ambas: true,
        under_value: false,
        virada_turnaround: true,
        cashout: false,
        pressao_blitz: false,
      });
    } else if (preset === "critical_only") {
      setEnabledCategories({
        imminent_goal: true,
        back_dominant: false,
        triple_debt: true,
        goal_debt_over: true,
        corners: false,
        cards: true,
        btts_ambas: false,
        under_value: false,
        virada_turnaround: true,
        cashout: true,
        pressao_blitz: false,
      });
    }
  };

  // Count logs per category
  const categoryCounts = useMemo(() => {
    const counts: Record<AlertTypeCategory, number> = {
      imminent_goal: 0,
      back_dominant: 0,
      triple_debt: 0,
      goal_debt_over: 0,
      corners: 0,
      cards: 0,
      btts_ambas: 0,
      under_value: 0,
      virada_turnaround: 0,
      cashout: 0,
      pressao_blitz: 0,
    };
    logs.forEach((l) => {
      const cat = categorizeAlert(l);
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return counts;
  }, [logs]);

  // Filter logs based on quick config, match filters, match status, and text search
  const filteredLogs = useMemo(() => {
    // Map of active/live match IDs and their statuses
    const matchMap = new Map<string, Match>();
    matches.forEach((m) => {
      matchMap.set(m.id, m);
    });

    return logs.filter((l) => {
      // 0. Finished matches filter (excludes FT / Ended matches or matches no longer active)
      if (hideFinishedMatches && l.matchId) {
        const associatedMatch = matchMap.get(l.matchId);
        if (associatedMatch && associatedMatch.status === "FT") {
          return false;
        }
      }

      // 1. Severity filter
      if (logFilter !== "all" && l.severity !== logFilter) return false;

      // 2. Target match filter
      if (selectedMatchFilter !== "all" && l.matchId !== selectedMatchFilter) {
        return false;
      }

      // 3. Muted matches filter
      if (l.matchId && mutedMatchIds[l.matchId]) {
        return false;
      }

      // 4. Alert Category toggle filter
      const cat = categorizeAlert(l);
      if (!enabledCategories[cat]) {
        return false;
      }

      // 5. Search keyword
      if (searchLog) {
        const q = searchLog.toLowerCase();
        return (
          l.message.toLowerCase().includes(q) ||
          l.matchTitle.toLowerCase().includes(q) ||
          l.ruleName.toLowerCase().includes(q)
        );
      }
      return true;
    }).sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }, [logs, matches, hideFinishedMatches, logFilter, selectedMatchFilter, mutedMatchIds, enabledCategories, searchLog]);

  const activeCategoryCount = Object.values(enabledCategories).filter(Boolean).length;
  const mutedMatchCount = Object.values(mutedMatchIds).filter(Boolean).length;
  const totalHiddenLogs = logs.length - filteredLogs.length;

  const getSeverityBadge = (sev: AlertSeverity) => {
    switch (sev) {
      case "critical":
        return (
          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold uppercase flex items-center gap-1">
            <ShieldAlert className="w-3 h-3" /> Crítico
          </span>
        );
      case "opportunity":
        return (
          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold uppercase flex items-center gap-1">
            <Flame className="w-3 h-3" /> Oportunidade
          </span>
        );
      case "warning":
        return (
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold uppercase flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> Aviso
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-[10px] font-bold uppercase flex items-center gap-1">
            <Info className="w-3 h-3" /> Info
          </span>
        );
    }
  };

  const renderBettingTip = (tip: any, matchId?: string) => {
    const isCovered = checkOddsCoverage(matchId, tip.bookmakerOdds);
    const activeOdds = getActiveBookmakerOdds(tip.bookmakerOdds || []);
    const maxActiveOdd = activeOdds.length > 0
      ? Math.max(...activeOdds.map((b: any) => b.odd))
      : tip.fairOdd;
    const bestOddItem = activeOdds.find((b: any) => b.odd === maxActiveOdd) || activeOdds[0];

    return (
      <div className="my-2.5 p-3.5 rounded-xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-amber-500/30 shadow-lg space-y-3">
        {/* Tip Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center font-black text-xs">
              🎯
            </div>
            <div>
              <span className="text-xs font-black text-white tracking-wide">
                DICA DE TRADE: {tip.marketName.toUpperCase()}
              </span>
              <span className="text-[11px] text-amber-400 font-bold ml-2">
                • Seleção: {tip.targetSelection}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase ${
              tip.confidence === "extrema"
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                : tip.confidence === "alta"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
            }`}>
              Confiança {tip.confidence}
            </span>
            {isCovered && tip.edgePct > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                +{tip.edgePct}% EV
              </span>
            )}
          </div>
        </div>

        {/* Probability Progress Bar & Metrics */}
        <div className="space-y-1.5">
          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 font-medium flex items-center gap-1">
              Probabilidade do Mercado Acontecer:
            </span>
            <span className="text-emerald-400 font-black text-sm">
              {tip.probabilityPct}%
            </span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                tip.probabilityPct >= 80
                  ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                  : tip.probabilityPct >= 65
                  ? "bg-gradient-to-r from-amber-500 to-emerald-400"
                  : "bg-gradient-to-r from-amber-600 to-yellow-500"
              }`}
              style={{ width: `${Math.min(100, tip.probabilityPct)}%` }}
            />
          </div>
        </div>

        {/* Fair Odd & Best Odd Grid (Only when odds covered) */}
        {isCovered && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
            <div className="p-2 rounded-lg bg-slate-950/80 border border-slate-800 flex flex-col">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Odd Justa (+EV)</span>
              <span className="text-slate-200 font-mono font-bold text-sm">
                @ {tip.fairOdd.toFixed(2)}
              </span>
            </div>

            <div className="p-2 rounded-lg bg-slate-950/80 border border-slate-800 flex flex-col">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Melhor Cotação</span>
              <span className="text-emerald-400 font-mono font-bold text-sm">
                @ {bestOddItem ? bestOddItem.odd.toFixed(2) : tip.fairOdd.toFixed(2)}
              </span>
            </div>

            <div className="p-2 rounded-lg bg-slate-950/80 border border-slate-800 col-span-2 sm:col-span-1 flex flex-col justify-center">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Melhor Casa</span>
              <span className="text-amber-300 font-bold truncate">
                {bestOddItem ? bestOddItem.name : "Betano"}
              </span>
            </div>
          </div>
        )}

        {/* Live Bookmaker Odds Comparison (Only when odds covered) */}
        {isCovered && activeOdds.length > 0 && (
          <div className="space-y-1.5 pt-1 border-t border-slate-800/80">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 block">
                Odds ao Vivo nas Casas de Apostas:
              </span>
              <span className="text-[9px] text-amber-400/80 font-mono">
                {activeOdds.length} casa(s) ativa(s)
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
              {activeOdds.map((bk: any, bkIdx: number) => {
                const isCurrentBest = bk.odd === maxActiveOdd;
                return (
                  <div
                    key={`${bk.bookmakerId}-${bkIdx}`}
                    className={`p-2 rounded-lg border text-left flex items-center justify-between gap-1 transition ${
                      isCurrentBest
                        ? "bg-amber-500/10 border-amber-500/50 shadow-sm"
                        : bk.odd > tip.fairOdd
                        ? "bg-emerald-500/10 border-emerald-500/40"
                        : "bg-slate-950/70 border-slate-800"
                    }`}
                  >
                    <div className="min-w-0">
                      <span className="text-[11px] font-bold text-slate-200 block truncate">
                        {bk.name}
                      </span>
                      <span className="text-[9px] text-slate-400 uppercase font-mono">
                        {bk.shortName}
                      </span>
                    </div>

                    <div className="text-right shrink-0">
                      <span className={`text-xs font-mono font-black ${
                        isCurrentBest
                          ? "text-amber-400"
                          : bk.odd > tip.fairOdd
                          ? "text-emerald-400"
                          : "text-slate-300"
                      }`}>
                        @{bk.odd.toFixed(2)}
                      </span>
                      {bk.odd > tip.fairOdd && (
                        <span className="block text-[8px] font-bold text-emerald-400 leading-none">
                          +EV
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Recommended Action */}
        <div className="p-2 rounded-lg bg-emerald-950/20 border border-emerald-500/30 flex items-center gap-2 text-xs text-emerald-300 font-medium">
          <span className="font-bold shrink-0">👉 Conduta de Entrada:</span>
          <span>{tip.actionText}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Top Header Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
        <div>
          <div className="flex items-center gap-2">
            <Bell className="w-6 h-6 text-amber-400" />
            <h2 className="text-xl font-bold text-white tracking-tight">
              Central de Notificações & Alertas em Tempo Real
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Histórico ao vivo de oportunidades disparadas pelo motor de regras e algoritmos estatísticos.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Alertas Ativos: {filteredLogs.length}</span>
          </div>
        </div>
      </div>

      {/* PAINEL DE CONFIGURAÇÃO RÁPIDA DE ALERTAS & FILTRO DE RUÍDO */}
      <div className="bg-slate-900/95 rounded-2xl border border-slate-800 p-5 shadow-xl space-y-4">
        {/* Quick Config Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <SlidersHorizontal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-tight">
                  Painel de Configuração Rápida & Redução de Ruído
                </h3>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {activeCategoryCount}/7 Ativos
                </span>
                {mutedMatchCount > 0 && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30 font-medium">
                    {mutedMatchCount} Jogo(s) Silenciado(s)
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400">
                Ative ou silencie categorias de alerta específicas e selecione partidas para focar apenas nas oportunidades de alto valor.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Quick Preset Buttons */}
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
              <button
                onClick={() => handleApplyPreset("all")}
                className="px-2.5 py-1 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition font-medium"
                title="Ativa todas as categorias"
              >
                Todos
              </button>
              <button
                onClick={() => handleApplyPreset("debts_only")}
                className="px-2.5 py-1 rounded-lg text-amber-300 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 transition font-bold"
                title="Apenas Dívidas (Gol Devendo, Back Dominante e Trinca)"
              >
                Apenas Dívidas
              </button>
              <button
                onClick={() => handleApplyPreset("critical_only")}
                className="px-2.5 py-1 rounded-lg text-rose-300 hover:text-white hover:bg-slate-800 transition font-medium"
                title="Apenas Trinca e Críticos"
              >
                Críticos
              </button>
            </div>

            <button
              onClick={() => setIsQuickConfigOpen(!isQuickConfigOpen)}
              className="p-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 transition"
              title={isQuickConfigOpen ? "Recolher painel" : "Expandir painel"}
            >
              {isQuickConfigOpen ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {isQuickConfigOpen && (
          <div className="space-y-4 pt-1 animate-in fade-in">
            {/* Target Match Selector & Mute Controls */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-950 p-3 rounded-xl border border-slate-800/90">
              <div className="flex items-center gap-2 flex-1">
                <Radio className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-xs font-semibold text-slate-300 shrink-0">
                  Filtrar por Partida:
                </span>
                <select
                  value={selectedMatchFilter}
                  onChange={(e) => setSelectedMatchFilter(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1 text-xs text-white focus:outline-none focus:border-emerald-500 flex-1 max-w-sm"
                >
                  <option value="all">Todas as Partidas Ativas ({matches.length})</option>
                  {matches.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.homeTeam.name} {m.score.home}-{m.score.away} {m.awayTeam.name} ({m.minute}')
                    </option>
                  ))}
                </select>
              </div>

              {/* Match Mute Action */}
              {selectedMatchFilter !== "all" && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggleMatchMute(selectedMatchFilter)}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                      mutedMatchIds[selectedMatchFilter]
                        ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                        : "bg-slate-800 text-slate-300 hover:text-white border border-slate-700"
                    }`}
                  >
                    {mutedMatchIds[selectedMatchFilter] ? (
                      <>
                        <ShieldAlert className="w-3.5 h-3.5" /> Jogo Silenciado (Clique para Ativar)
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-3.5 h-3.5" /> Silenciar Alertas Deste Jogo
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>

            {/* Alert Categories Toggle Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {ALERT_CATEGORIES.map((cat) => {
                const isEnabled = enabledCategories[cat.id];
                const count = categoryCounts[cat.id] || 0;
                return (
                  <div
                    key={cat.id}
                    onClick={() => handleToggleCategory(cat.id)}
                    className={`cursor-pointer p-3 rounded-xl border transition-all flex items-center justify-between gap-3 select-none ${
                      isEnabled
                        ? "bg-slate-950 border-slate-700/90 shadow-sm hover:border-slate-600"
                        : "bg-slate-950/40 border-slate-800/60 opacity-60 hover:opacity-80"
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div
                        className={`p-2 rounded-lg border shrink-0 ${
                          isEnabled ? cat.badgeBg : "bg-slate-900 text-slate-500 border-slate-800"
                        }`}
                      >
                        {cat.icon}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-xs font-bold truncate ${
                              isEnabled ? "text-white" : "text-slate-400 line-through"
                            }`}
                          >
                            {cat.name}
                          </span>
                          {count > 0 && (
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 shrink-0">
                              {count}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 truncate mt-0.5">
                          {cat.shortDesc}
                        </p>
                      </div>
                    </div>

                    {/* Interactive Switch Pill */}
                    <div
                      className={`w-9 h-5 rounded-full transition-colors relative shrink-0 ${
                        isEnabled ? "bg-emerald-500" : "bg-slate-800"
                      }`}
                    >
                      <div
                        className={`w-3.5 h-3.5 rounded-full bg-white transition-transform absolute top-0.5 ${
                          isEnabled ? "translate-x-4" : "translate-x-1"
                        }`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Noise Reduction Notice Bar if any filter is active */}
            {totalHiddenLogs > 0 && (
              <div className="flex items-center justify-between text-xs bg-slate-950/80 px-3.5 py-2 rounded-xl border border-slate-800 text-slate-400">
                <span>
                  🛡️ Filtro de ruído ativo: <strong className="text-amber-300 font-bold">{totalHiddenLogs}</strong> alerta(s) ocultados pelas regras de foco selecionadas.
                </span>
                <button
                  onClick={() => {
                    handleSetAllCategories(true);
                    setSelectedMatchFilter("all");
                    setMutedMatchIds({});
                  }}
                  className="text-emerald-400 hover:text-emerald-300 font-semibold underline text-[11px]"
                >
                  Restaurar Visualização Completa
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* HISTÓRICO DE ALERTAS (LOGS) */}
      <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-4">
          {/* Filter & Actions Bar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filtrar por time, jogo ou mensagem..."
                  value={searchLog}
                  onChange={(e) => setSearchLog(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <select
                value={logFilter}
                onChange={(e) => setLogFilter(e.target.value as any)}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-emerald-500 shrink-0"
              >
                <option value="all">Todas Severidades</option>
                <option value="opportunity">Oportunidade</option>
                <option value="warning">Aviso</option>
                <option value="critical">Crítico</option>
                <option value="info">Informação</option>
              </select>

              <button
                type="button"
                onClick={() => setHideFinishedMatches(!hideFinishedMatches)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition shrink-0 flex items-center gap-1.5 ${
                  hideFinishedMatches
                    ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300"
                    : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
                }`}
                title={hideFinishedMatches ? "Ocultando alertas de jogos terminados (FT)" : "Exibindo alertas de todos os jogos"}
              >
                <Radio className={`w-3.5 h-3.5 ${hideFinishedMatches ? "text-emerald-400 animate-pulse" : "text-slate-500"}`} />
                <span>{hideFinishedMatches ? "Ocultar Terminados" : "Mostrar Terminados"}</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => onTriggerTestAlert("opportunity")}
                className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1"
                title="Testa o alerta sonoro e visual"
              >
                <Volume2 className="w-3.5 h-3.5 text-amber-400" />
                Testar Som
              </button>

              {logs.length > 0 && (
                <>
                  <button
                    onClick={onMarkAsRead}
                    className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1"
                  >
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    Marcar Lidos
                  </button>
                  <button
                    onClick={onClearLogs}
                    className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-rose-900/30 text-rose-300 text-xs font-semibold border border-slate-700 flex items-center gap-1"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Limpar
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Logs List */}
          {filteredLogs.length === 0 ? (
            <div className="text-center py-12 text-slate-500 space-y-2">
              <Bell className="w-8 h-8 mx-auto text-slate-600" />
              <p className="text-sm font-semibold text-slate-400">
                Nenhum alerta correspondente aos filtros ativos.
              </p>
              <p className="text-xs text-slate-600">
                Ajuste os filtros do Painel de Configuração Rápida acima ou aguarde os próximos eventos ao vivo.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredLogs.map((log, logIdx) => (
                <div
                  key={`${log.id || 'log'}-${logIdx}`}
                  className={`p-4 rounded-xl border transition-all ${
                    log.read
                      ? "bg-slate-950/60 border-slate-800/80"
                      : "bg-slate-950 border-slate-700 shadow-md ring-1 ring-emerald-500/20"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      {getSeverityBadge(log.severity)}
                      {log.country && (
                        <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[10px] font-extrabold uppercase flex items-center gap-1">
                          🌍 {typeof log.country === 'object' && log.country !== null ? (log.country as any).name || 'País' : String(log.country)}
                        </span>
                      )}
                      {log.league && (
                        <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700 text-[10px] font-bold uppercase truncate max-w-[220px]">
                          🏆 {typeof log.league === 'object' && log.league !== null ? (log.league as any).name || 'Liga' : String(log.league)}
                        </span>
                      )}
                      <span className="text-xs font-bold text-white">{log.matchTitle}</span>
                      <span className="text-xs font-semibold text-emerald-400">({log.score})</span>
                      <span className="text-[11px] font-bold text-slate-400">• Minuto {log.minute}'</span>

                      {/* Ver Partida Button */}
                      {log.matchId && onSelectMatch && (
                        <button
                          type="button"
                          onClick={() => onSelectMatch(log.matchId!)}
                          title="Abrir partida no Dashboard"
                          className="px-2.5 py-1 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black text-[10.5px] flex items-center gap-1.5 transition shadow-sm active:scale-95 cursor-pointer"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Ver Partida</span>
                        </button>
                      )}

                      {/* FlashScore Link */}
                      {getFlashscoreUrl(log.url, log.matchId) && (
                        <a
                          href={getFlashscoreUrl(log.url, log.matchId)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="Abrir partida no FlashScore"
                          className="px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-800 text-cyan-300 hover:text-cyan-200 border border-cyan-500/30 text-[10px] font-semibold flex items-center gap-1 transition"
                        >
                          <span>FlashScore</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-500 font-medium">
                        {new Date(log.timestamp).toLocaleTimeString("pt-BR")}
                      </span>
                      {onDeleteAlert && (
                        <button
                          type="button"
                          onClick={() => onDeleteAlert(log.id)}
                          title="Apagar este alerta"
                          className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/15 border border-transparent hover:border-rose-500/30 transition flex items-center gap-1 text-[11px]"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span className="hidden sm:inline">Apagar</span>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="bg-slate-900/70 p-3 rounded-lg border border-slate-800/80 my-2">
                    <p className="text-xs font-mono text-slate-200 whitespace-pre-line leading-relaxed">
                      {log.message}
                    </p>
                  </div>

                  {/* Betting Tip & Bookmaker Odds Card */}
                  {log.bettingTip && renderBettingTip(log.bettingTip, log.matchId)}

                  <div className="mt-2 pt-2 border-t border-slate-800/60 flex justify-between items-center text-[10px] text-slate-500">
                    <span>Regra: {log.ruleName}</span>
                    {!log.read && (
                      <span className="text-emerald-400 font-bold">• Novo Alerta</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}
