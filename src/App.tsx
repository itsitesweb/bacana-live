import React, { useState, useEffect, useRef, useMemo } from "react";
import { safeFetchJson } from "./api";
import {
  Match,
  AlertRule,
  AlertLog,
  CrawlerStatus,
  TacticalAnalysis,
  AlertSeverity,
  OperationalRulesConfig,
  MatchRulesAnalysis,
} from "./types";
import { Header } from "./components/Header";
import { MatchCard } from "./components/MatchCard";
import { CompactMatchTicker } from "./components/CompactMatchTicker";
import { MatchDetail } from "./components/MatchDetail";
import { AlertsManager } from "./components/AlertsManager";
import { LocalConfigModal, TabType } from "./components/LocalConfigModal";
import { GoalAlertPopup, GoalEventData } from "./components/GoalAlertPopup";
import { useAuth } from "./context/AuthContext";
import { soundEffects } from "./components/AudioAlertService";
import {
  Activity,
  Flame,
  Radio,
  Search,
  Filter,
  Plus,
  RefreshCw,
  X,
  Bell,
  Sparkles,
  ExternalLink,
  Info,
  LayoutGrid,
  List,
  Sliders,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Move,
  Grid3X3,
  Columns3,
  Trash2,
  ArrowUpDown,
} from "lucide-react";

export type MatchSortOption =
  | "debt_desc"
  | "minute_desc"
  | "minute_asc"
  | "pressure_desc"
  | "goals_desc"
  | "corners_desc"
  | "league_asc"
  | "team_asc"
  | "custom";

export default function App() {
  const { userProfile, saveUserSettings, getUserSettings } = useAuth();
  const [isLocalConfigModalOpen, setIsLocalConfigModalOpen] = useState<boolean>(false);
  const [localConfigInitialTab, setLocalConfigInitialTab] = useState<TabType>("rules_engine");

  const [activeTab, setActiveTab] = useState<"dashboard" | "alerts">("dashboard");
  const [matches, setMatches] = useState<Match[]>([]);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [dismissedMatchIds, setDismissedMatchIds] = useState<string[]>([]);
  const dismissedMatchIdsRef = useRef<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<"grid" | "carousel" | "compact">("carousel");
  const [sortOption, setSortOption] = useState<MatchSortOption>("debt_desc");
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertLogs, setAlertLogs] = useState<AlertLog[]>([]);
  const [crawlerStatus, setCrawlerStatus] = useState<CrawlerStatus | null>(null);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);
  const [countryFilter, setCountryFilter] = useState<string>("all");
  const [leagueFilter, setLeagueFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [aiAnalysisMap, setAiAnalysisMap] = useState<Record<string, TacticalAnalysis>>({});
  const [isAiLoading, setIsAiLoading] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // Goal Alerts & Card Flash State
  const [goalAlerts, setGoalAlerts] = useState<GoalEventData[]>([]);
  const [flashingGoalMatchIds, setFlashingGoalMatchIds] = useState<Record<string, number>>({});
  const prevScoresRef = useRef<Map<string, { home: number; away: number }>>(new Map());

  // Custom Match Card Ordering
  const [customMatchOrder, setCustomMatchOrder] = useState<string[]>([]);
  const [hasLoadedUserSettings, setHasLoadedUserSettings] = useState<boolean>(false);

  const [draggedMatchId, setDraggedMatchId] = useState<string | null>(null);
  const carouselContainerRef = useRef<HTMLDivElement | null>(null);

  // Helper to sort list by saved order
  const sortMatchesByCustomOrder = (list: Match[], order: string[]) => {
    if (!order || order.length === 0) return list;
    const orderMap = new Map<string, number>();
    order.forEach((id, idx) => orderMap.set(id, idx));
    return [...list].sort((a, b) => {
      const indexA = orderMap.has(a.id) ? orderMap.get(a.id)! : 9999;
      const indexB = orderMap.has(b.id) ? orderMap.get(b.id)! : 9999;
      return indexA - indexB;
    });
  };

  // Load User Preferences from Local Storage / Config
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const savedSettings = await getUserSettings("preferences");
        if (savedSettings) {
          if (savedSettings.viewMode) setViewMode(savedSettings.viewMode);
          if (savedSettings.sortOption) setSortOption(savedSettings.sortOption);
          if (savedSettings.soundEnabled !== undefined) setSoundEnabled(savedSettings.soundEnabled);
          if (Array.isArray(savedSettings.customMatchOrder)) setCustomMatchOrder(savedSettings.customMatchOrder);
        } else {
          // Fallback to local storage if existing
          const localOrder = localStorage.getItem("footstats_match_order");
          if (localOrder) {
            try {
              setCustomMatchOrder(JSON.parse(localOrder));
            } catch {}
          }
        }
      } catch (e) {
        console.error("Erro ao carregar configurações do usuário local:", e);
      } finally {
        setHasLoadedUserSettings(true);
      }
    };

    loadSettings();
  }, []);

  // Sync user preferences to local config
  const updateUserSettingsDebounced = (key: string, value: any) => {
    saveUserSettings("preferences", {
      viewMode,
      sortOption,
      soundEnabled,
      customMatchOrder,
      [key]: value,
    });
  };

  const handleSetViewMode = (mode: "grid" | "carousel" | "compact") => {
    setViewMode(mode);
    updateUserSettingsDebounced("viewMode", mode);
  };

  const handleSetSortOption = (opt: MatchSortOption) => {
    setSortOption(opt);
    updateUserSettingsDebounced("sortOption", opt);
  };

  const handleSetSoundEnabled = (enabled: boolean) => {
    setSoundEnabled(enabled);
    updateUserSettingsDebounced("soundEnabled", enabled);
  };

  // Operational Rules (Diagnóstico & Python port) state
  const [rulesConfig, setRulesConfig] = useState<OperationalRulesConfig | null>(null);
  const [rulesAnalysisMap, setRulesAnalysisMap] = useState<Record<string, MatchRulesAnalysis>>({});

  const handleSelectAndScrollToMatch = (matchId: string) => {
    setSelectedMatchId(matchId);
    setActiveTab("dashboard");
    setCountryFilter("all");
    setLeagueFilter("all");
    setSearchQuery("");
    
    // Wait for the Dashboard tab to render the MatchDetail component, then scroll smoothly into view
    setTimeout(() => {
      const el = document.getElementById("match-detail-section");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        window.scrollTo({ top: 450, behavior: "smooth" });
      }
    }, 150);
  };
  const prevLogCountRef = useRef<number>(0);

  // Save match order helper
  const saveMatchOrder = (newOrder: string[]) => {
    setCustomMatchOrder(newOrder);
    try {
      localStorage.setItem("footstats_match_order", JSON.stringify(newOrder));
    } catch (e) {
      console.error("Erro ao salvar ordem das partidas:", e);
    }
    saveUserSettings("preferences", {
      viewMode,
      sortOption,
      soundEnabled,
      customMatchOrder: newOrder,
    });
  };

  // Move match left/right in order
  const handleMoveMatch = (matchId: string, direction: "left" | "right") => {
    setSortOption("custom");
    const currentList = sortMatchesByCustomOrder(matches, customMatchOrder);
    const currentIndex = currentList.findIndex((m) => m.id === matchId);
    if (currentIndex === -1) return;

    const targetIndex = direction === "left" ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= currentList.length) return;

    const newList = [...currentList];
    const [moved] = newList.splice(currentIndex, 1);
    newList.splice(targetIndex, 0, moved);

    const newOrderIds = newList.map((m) => m.id);
    saveMatchOrder(newOrderIds);
  };

  // Drag and drop reordering
  const handleDragStart = (matchId: string) => {
    setDraggedMatchId(matchId);
  };

  const handleDropOnMatch = (targetMatchId: string) => {
    if (!draggedMatchId || draggedMatchId === targetMatchId) {
      setDraggedMatchId(null);
      return;
    }

    setSortOption("custom");
    const currentList = sortMatchesByCustomOrder(matches, customMatchOrder);
    const draggedIndex = currentList.findIndex((m) => m.id === draggedMatchId);
    const targetIndex = currentList.findIndex((m) => m.id === targetMatchId);

    if (draggedIndex !== -1 && targetIndex !== -1) {
      const newList = [...currentList];
      const [moved] = newList.splice(draggedIndex, 1);
      newList.splice(targetIndex, 0, moved);

      const newOrderIds = newList.map((m) => m.id);
      saveMatchOrder(newOrderIds);
    }
    setDraggedMatchId(null);
  };

  const handleResetOrder = () => {
    setCustomMatchOrder([]);
    try {
      localStorage.removeItem("footstats_match_order");
    } catch (e) {
      console.error(e);
    }
  };

  // Scroll carousel left/right
  const handleScrollCarousel = (direction: "left" | "right") => {
    if (carouselContainerRef.current) {
      const scrollAmount = direction === "left" ? -350 : 350;
      carouselContainerRef.current.scrollBy({ left: scrollAmount, behavior: "smooth" });
    }
  };

  // Fetch operational rules config and analysis
  const fetchRulesConfig = async () => {
    const data = await safeFetchJson<{ config: OperationalRulesConfig }>("/api/rules/config");
    if (data?.config) {
      setRulesConfig(data.config);
    }
  };

  const fetchRulesAnalysis = async () => {
    const data = await safeFetchJson<{ analysis: MatchRulesAnalysis[] | Record<string, MatchRulesAnalysis> }>("/api/rules/analysis");
    if (data?.analysis) {
      if (Array.isArray(data.analysis)) {
        const map: Record<string, MatchRulesAnalysis> = {};
        data.analysis.forEach((a: MatchRulesAnalysis) => {
          if (a && a.matchId) {
            map[a.matchId] = a;
          }
        });
        setRulesAnalysisMap(map);
      } else if (typeof data.analysis === "object") {
        setRulesAnalysisMap(data.analysis as Record<string, MatchRulesAnalysis>);
      }
    }
  };

  // Sync ref with state
  useEffect(() => {
    dismissedMatchIdsRef.current = new Set(dismissedMatchIds);
  }, [dismissedMatchIds]);

  // Fetch all matches (filtering finished matches from live display and dismissed ones)
  const fetchMatches = async () => {
    const data = await safeFetchJson<{ matches: Match[] }>("/api/matches");
    if (data?.matches) {
      const liveMatches = data.matches.filter(
        (m) =>
          !dismissedMatchIdsRef.current.has(m.id) &&
          m.status !== "FT" &&
          m.status !== "FINISHED" &&
          m.status !== "ENCERRADO"
      );

      // Detect Goals between consecutive scans
      liveMatches.forEach((m) => {
        if (prevScoresRef.current.has(m.id)) {
          const prev = prevScoresRef.current.get(m.id)!;
          if (m.score.home > prev.home || m.score.away > prev.away) {
            const isHomeGoal = m.score.home > prev.home;
            const scoringTeam = isHomeGoal
              ? (typeof m.homeTeam?.name === "object" ? (m.homeTeam.name as any)?.name : m.homeTeam?.name) || "Mandante"
              : (typeof m.awayTeam?.name === "object" ? (m.awayTeam.name as any)?.name : m.awayTeam?.name) || "Visitante";
            const homeName = (typeof m.homeTeam?.name === "object" ? (m.homeTeam.name as any)?.name : m.homeTeam?.name) || "Mandante";
            const awayName = (typeof m.awayTeam?.name === "object" ? (m.awayTeam.name as any)?.name : m.awayTeam?.name) || "Visitante";
            const leagueStr = typeof m.league === "object" ? (m.league as any)?.name : String(m.league || "");
            const countryStr = typeof m.country === "object" ? (m.country as any)?.name : String(m.country || "");

            const goalItem: GoalEventData = {
              id: `goal-${Date.now()}-${m.id}`,
              matchId: m.id,
              homeTeam: homeName,
              awayTeam: awayName,
              scoringTeam,
              minute: m.minute,
              newScore: `${m.score.home} - ${m.score.away}`,
              league: leagueStr,
              country: countryStr,
              timestamp: Date.now(),
            };

            setGoalAlerts((prevList) => [goalItem, ...prevList.slice(0, 3)]);
            setFlashingGoalMatchIds((prevMap) => ({ ...prevMap, [m.id]: Date.now() }));
            if (soundEnabled) {
              soundEffects.playGoalSound();
            }

            setTimeout(() => {
              setFlashingGoalMatchIds((prevMap) => {
                const next = { ...prevMap };
                delete next[m.id];
                return next;
              });
            }, 7500);
          }
        }
        prevScoresRef.current.set(m.id, { home: m.score.home, away: m.score.away });
      });

      setMatches(liveMatches);
      setSelectedMatchId((prev) => {
        // Se já tiver uma partida selecionada e ela ainda existir, não mude o foco para novas partidas
        if (prev && data.matches.some((m) => m.id === prev)) return prev;
        return prev || (liveMatches.length > 0 ? liveMatches[0].id : null);
      });
    }
  };

  // Delete / Dismiss match for current crawler session
  const handleDeleteMatch = async (matchId: string) => {
    // 1. Update local state immediately
    dismissedMatchIdsRef.current.add(matchId);
    setDismissedMatchIds((prev) => (prev.includes(matchId) ? prev : [...prev, matchId]));
    setMatches((prev) => prev.filter((m) => m.id !== matchId));
    setAlertLogs((prev) => prev.filter((l) => l.matchId !== matchId));

    // 2. Adjust selected match if the deleted one was selected
    setSelectedMatchId((prev) => {
      if (prev === matchId) {
        const remaining = matches.filter((m) => m.id !== matchId);
        return remaining.length > 0 ? remaining[0].id : null;
      }
      return prev;
    });

    // 3. Send dismissal to server
    try {
      await safeFetchJson(`/api/matches/${matchId}/dismiss`, { method: "POST" });
    } catch {
      // Ignora erro de rede eventual
    }
  };

  // Manual refresh that clears finished matches and re-syncs state
  const handleRefreshMatches = async () => {
    setIsRefreshing(true);
    try {
      const refreshData = await safeFetchJson<{ success: boolean; matches?: Match[] }>("/api/matches/refresh", {
        method: "POST",
      });
      if (refreshData?.matches) {
        const liveMatches = refreshData.matches.filter(
          (m) =>
            !dismissedMatchIdsRef.current.has(m.id) &&
            m.status !== "FT" &&
            m.status !== "FINISHED" &&
            m.status !== "ENCERRADO"
        );
        setMatches(liveMatches);
        setSelectedMatchId((prev) => {
          if (prev && refreshData.matches?.some((m) => m.id === prev)) return prev;
          return prev || (liveMatches.length > 0 ? liveMatches[0].id : null);
        });
      } else {
        await fetchMatches();
      }
      await Promise.all([
        fetchAlerts(),
        fetchCrawlerStatus(),
        fetchRulesAnalysis(),
      ]);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Delete individual alert log
  const handleDeleteSingleAlert = async (id: string) => {
    await safeFetchJson(`/api/alerts/logs/${id}`, { method: "DELETE" });
    setAlertLogs((prev) => prev.filter((l) => l.id !== id));
  };

  // Fetch alert rules and logs
  const fetchAlerts = async () => {
    const [rulesData, logsData] = await Promise.all([
      safeFetchJson<{ rules: AlertRule[] }>("/api/alerts/rules"),
      safeFetchJson<{ logs: AlertLog[] }>("/api/alerts/logs"),
    ]);

    if (rulesData?.rules) {
      setAlertRules(rulesData.rules);
    }

    if (logsData?.logs) {
      // Filter out dismissed matches and keep in chronological order (oldest first, new at the end)
      const newLogs: AlertLog[] = (logsData.logs || [])
        .filter((l) => !l.matchId || !dismissedMatchIdsRef.current.has(l.matchId))
        .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
      
      // Detect if a new unread alert arrived at the end of the log list
      if (newLogs.length > prevLogCountRef.current && prevLogCountRef.current > 0) {
        const newest = newLogs[newLogs.length - 1];
        if (newest && !newest.read) {
          if (soundEnabled) {
            soundEffects.play(newest.severity);
          }
        }
      }
      prevLogCountRef.current = newLogs.length;
      setAlertLogs(newLogs);
    }
  };

  // Fetch crawler telemetry
  const fetchCrawlerStatus = async () => {
    const data = await safeFetchJson<CrawlerStatus>("/api/crawler/status");
    if (data) {
      // If crawler was disconnected and reconnected, or has been reset, clear dismissed matches
      if (crawlerStatus && crawlerStatus.connected && !data.connected) {
        dismissedMatchIdsRef.current.clear();
        setDismissedMatchIds([]);
      }
      setCrawlerStatus(data);
    }
  };

  // Initial and periodic sync interval
  useEffect(() => {
    fetchMatches();
    fetchAlerts();
    fetchCrawlerStatus();
    fetchRulesConfig();
    fetchRulesAnalysis();

    const interval = setInterval(() => {
      fetchMatches();
      fetchAlerts();
      fetchCrawlerStatus();
      fetchRulesConfig();
      fetchRulesAnalysis();
    }, 2500);

    // Forced full refresh on all displayed live matches every 180 seconds (3 minutes)
    const forceRefreshInterval = setInterval(() => {
      handleRefreshMatches();
    }, 180000);

    return () => {
      clearInterval(interval);
      clearInterval(forceRefreshInterval);
    };
  }, [selectedMatchId, soundEnabled]);

  // Save rule
  const handleSaveRule = async (rule: AlertRule) => {
    await safeFetchJson("/api/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    });
    await fetchAlerts();
  };

  // Delete rule
  const handleDeleteRule = async (id: string) => {
    await safeFetchJson(`/api/alerts/rules/${id}`, { method: "DELETE" });
    await fetchAlerts();
  };

  // Mark alerts as read
  const handleMarkAlertsAsRead = async () => {
    await safeFetchJson("/api/alerts/read", { method: "POST" });
    await fetchAlerts();
  };

  // Clear alerts
  const handleClearAlerts = async () => {
    await safeFetchJson("/api/alerts/clear", { method: "POST" });
    await fetchAlerts();
  };

  // Trigger test alert
  const handleTriggerTestAlert = (severity: AlertSeverity = "opportunity") => {
    soundEffects.play(severity);
    const testLog: AlertLog = {
      id: "test-" + Date.now(),
      ruleId: "test",
      ruleName: "Teste de Alerta Sonoro",
      matchId: selectedMatchId || "all",
      matchTitle: selectedMatch ? `${selectedMatch.homeTeam.name} x ${selectedMatch.awayTeam.name}` : "Alerta de Demonstração",
      minute: selectedMatch ? selectedMatch.minute : 75,
      score: selectedMatch ? `${selectedMatch.score.home} - ${selectedMatch.score.away}` : "1 - 1",
      severity,
      message: "🔥 TESTE DE ALERTA: Condição de pressão ofensiva extrema simulada com sucesso!",
      timestamp: new Date().toISOString(),
      read: false,
    };
    setAlertLogs((prev) => [...prev, testLog]);
  };

  // Send crawler test packet
  const handleSendCrawlerPacket = async (customPayload?: any): Promise<boolean> => {
    const data = await safeFetchJson<{ success: boolean; matchId?: string }>("/api/crawler/match-update", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-crawler-token": crawlerStatus?.apiKey || "footstats-crawler-live-key-99",
      },
      body: JSON.stringify(customPayload),
    });
    if (data?.success) {
      await fetchMatches();
      await fetchCrawlerStatus();
      return true;
    }
    return false;
  };

  // Gemini AI Tactical Analysis
  const handleAnalyzeWithAi = async (matchId: string): Promise<TacticalAnalysis | null> => {
    setIsAiLoading(true);
    try {
      const data = await safeFetchJson<{ analysis?: TacticalAnalysis }>("/api/gemini/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matchId }),
      });
      if (data?.analysis) {
        setAiAnalysisMap((prev) => ({ ...prev, [matchId]: data.analysis! }));
        return data.analysis;
      }
      return null;
    } finally {
      setIsAiLoading(false);
    }
  };

  // Calculate Countries and Leagues with live match counts
  const countriesWithCounts = useMemo(() => {
    const map = new Map<string, number>();
    matches.forEach((m) => {
      const c =
        typeof m.country === "object" && m.country !== null
          ? (m.country as any).name || ""
          : String(m.country || "");
      if (c) {
        map.set(c, (map.get(c) || 0) + 1);
      }
    });
    return Array.from(map.entries())
      .map(([country, count]) => ({ country, count }))
      .sort((a, b) => a.country.localeCompare(b.country));
  }, [matches]);

  const leaguesWithCounts = useMemo(() => {
    const map = new Map<string, number>();
    matches.forEach((m) => {
      const c =
        typeof m.country === "object" && m.country !== null
          ? (m.country as any).name || ""
          : String(m.country || "");
      if (countryFilter !== "all" && c !== countryFilter) return;

      const l =
        typeof m.league === "object" && m.league !== null
          ? (m.league as any).name || "Liga"
          : String(m.league || "");
      if (l) {
        map.set(l, (map.get(l) || 0) + 1);
      }
    });
    return Array.from(map.entries())
      .map(([league, count]) => ({ league, count }))
      .sort((a, b) => a.league.localeCompare(b.league));
  }, [matches, countryFilter]);

  const filteredMatches = matches.filter((m) => {
    const countryStr =
      typeof m.country === "object" && m.country !== null
        ? (m.country as any).name || ""
        : String(m.country || "");
    if (countryFilter !== "all" && countryStr !== countryFilter) return false;

    const leagueStr =
      typeof m.league === "object" && m.league !== null
        ? (m.league as any).name || "Liga"
        : String(m.league || "");
    if (leagueFilter !== "all" && leagueStr !== leagueFilter) return false;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const homeStr =
        typeof m.homeTeam?.name === "object"
          ? (m.homeTeam.name as any).name || ""
          : String(m.homeTeam?.name || "");
      const awayStr =
        typeof m.awayTeam?.name === "object"
          ? (m.awayTeam.name as any).name || ""
          : String(m.awayTeam?.name || "");

      return (
        homeStr.toLowerCase().includes(q) ||
        awayStr.toLowerCase().includes(q) ||
        leagueStr.toLowerCase().includes(q) ||
        countryStr.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const ratio = rulesConfig?.chancesPerGoalRatio ?? 3.0;

  const orderedMatches = useMemo(() => {
    if (sortOption === "custom") {
      return sortMatchesByCustomOrder(filteredMatches, customMatchOrder);
    }

    const list = [...filteredMatches];
    switch (sortOption) {
      case "debt_desc":
        return list.sort((a, b) => {
          const debtA = rulesAnalysisMap[a.id]?.codigo31?.saldoGolsDevidos ?? (
            ((a.stats.bigChances?.home || Math.floor(a.stats.shotsOnTarget.home / 2)) +
             (a.stats.bigChances?.away || Math.floor(a.stats.shotsOnTarget.away / 2))) / ratio -
            (a.score.home + a.score.away)
          );
          const debtB = rulesAnalysisMap[b.id]?.codigo31?.saldoGolsDevidos ?? (
            ((b.stats.bigChances?.home || Math.floor(b.stats.shotsOnTarget.home / 2)) +
             (b.stats.bigChances?.away || Math.floor(b.stats.shotsOnTarget.away / 2))) / ratio -
            (b.score.home + b.score.away)
          );
          return debtB - debtA;
        });
      case "minute_desc":
        return list.sort((a, b) => b.minute - a.minute);
      case "minute_asc":
        return list.sort((a, b) => a.minute - b.minute);
      case "pressure_desc":
        return list.sort((a, b) => {
          const pA = a.stats.pressureIndex.home + a.stats.pressureIndex.away;
          const pB = b.stats.pressureIndex.home + b.stats.pressureIndex.away;
          return pB - pA;
        });
      case "goals_desc":
        return list.sort((a, b) => (b.score.home + b.score.away) - (a.score.home + a.score.away));
      case "corners_desc":
        return list.sort((a, b) => (b.stats.corners.home + b.stats.corners.away) - (a.stats.corners.home + a.stats.corners.away));
      case "league_asc":
        return list.sort((a, b) => {
          const strA = `${typeof a.country === 'object' ? (a.country as any)?.name : (a.country || "")} ${typeof a.league === 'object' ? (a.league as any)?.name : (a.league || "")}`.trim();
          const strB = `${typeof b.country === 'object' ? (b.country as any)?.name : (b.country || "")} ${typeof b.league === 'object' ? (b.league as any)?.name : (b.league || "")}`.trim();
          return strA.localeCompare(strB);
        });
      case "team_asc":
        return list.sort((a, b) => {
          const nameA = typeof a.homeTeam?.name === 'object' ? (a.homeTeam.name as any)?.name || '' : String(a.homeTeam?.name || '');
          const nameB = typeof b.homeTeam?.name === 'object' ? (b.homeTeam.name as any)?.name || '' : String(b.homeTeam?.name || '');
          return nameA.localeCompare(nameB);
        });
      default:
        return list;
    }
  }, [filteredMatches, sortOption, customMatchOrder, rulesAnalysisMap, ratio]);

  // Initialize selectedMatchId only once on load if not set
  useEffect(() => {
    if (!selectedMatchId && matches.length > 0) {
      setSelectedMatchId(matches[0].id);
    }
  }, [matches, selectedMatchId]);

  const selectedMatch = useMemo(() => {
    if (selectedMatchId) {
      const match = matches.find((m) => m.id === selectedMatchId);
      if (match) return match;
    }
    return orderedMatches[0] || matches[0] || null;
  }, [matches, selectedMatchId, orderedMatches]);

  const unreadAlertsCount = alertLogs.filter((l) => !l.read).length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500 selection:text-slate-950 flex flex-col">
      {/* Top Main Navigation Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        crawlerStatus={crawlerStatus}
        unreadAlertsCount={unreadAlertsCount}
        soundEnabled={soundEnabled}
        setSoundEnabled={handleSetSoundEnabled}
        liveMatchesCount={matches.filter((m) => m.status === "1H" || m.status === "2H" || m.status === "LIVE").length}
        onOpenLocalConfig={(tab) => {
          setLocalConfigInitialTab(tab || "rules_engine");
          setIsLocalConfigModalOpen(true);
        }}
        ratioConfigured={rulesConfig?.chancesPerGoalRatio ?? 3.0}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* TAB 1: LIVE MATCHES DASHBOARD */}
        {activeTab === "dashboard" && (
          <div className="space-y-6">
            {/* Crawler & Live Ingestion Status Banner */}
            <div className="bg-gradient-to-r from-slate-900/90 via-slate-900/60 to-slate-900/90 border border-slate-800 rounded-2xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-inner">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${crawlerStatus?.connected || (crawlerStatus?.totalPacketsReceived && crawlerStatus.totalPacketsReceived > 0) ? "bg-emerald-400 animate-ping" : "bg-amber-400"}`} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-black text-slate-200 uppercase tracking-wide flex items-center gap-1.5">
                      <Radio className="w-3.5 h-3.5 text-emerald-400" />
                      Status Ingestão do Crawler
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${crawlerStatus?.totalPacketsReceived && crawlerStatus.totalPacketsReceived > 0 ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "bg-slate-800 text-slate-400 border border-slate-700"}`}>
                      {crawlerStatus?.totalPacketsReceived ? `${crawlerStatus.totalPacketsReceived} pacotes recebidos` : "Aguardando primeiro pacote"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {crawlerStatus?.lastHeartbeat ? (
                      <span>Último pacote recebido: <strong className="text-slate-300">{new Date(crawlerStatus.lastHeartbeat).toLocaleTimeString()}</strong> • Partidas ativas: <strong className="text-emerald-400">{matches.length}</strong></span>
                    ) : (
                      <span>Execute <code className="text-emerald-400 bg-slate-950 px-1 py-0.5 rounded font-mono text-[10px]">python bridge_web.py</code> para transmitir partidas em tempo real</span>
                    )}
                  </p>
                </div>
              </div>
            </div>

            {/* Filter Bars (Países & Ligas) & Search Bar */}
            <div className="space-y-2.5 bg-slate-900/70 p-3.5 rounded-2xl border border-slate-800/80 shadow-sm">
              {/* Row 1: Country Horizontal Filter Bar + Search Bar */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none flex-1 min-w-0">
                  <span className="text-[11px] font-black uppercase text-emerald-400 shrink-0 mr-1 flex items-center gap-1">
                    🌍 Países:
                  </span>
                  <button
                    onClick={() => {
                      setCountryFilter("all");
                    }}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap shrink-0 ${
                      countryFilter === "all"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent"
                    }`}
                  >
                    Todos os Países ({matches.length})
                  </button>
                  {countriesWithCounts.map(({ country, count }) => (
                    <button
                      key={country}
                      onClick={() => {
                        setCountryFilter(country === countryFilter ? "all" : country);
                        setLeagueFilter("all");
                      }}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap shrink-0 flex items-center gap-1.5 ${
                        countryFilter === country
                          ? "bg-emerald-500/25 text-emerald-200 border border-emerald-500/50 shadow-sm"
                          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-slate-800/60"
                      }`}
                    >
                      <span>{country}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${countryFilter === country ? "bg-emerald-500/30 text-emerald-200" : "bg-slate-800 text-slate-400"}`}>
                        {count}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Search match */}
                <div className="relative w-full sm:w-64 shrink-0">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Buscar time, país ou liga..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Row 2: League Horizontal Filter Bar */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none pt-1 border-t border-slate-800/60">
                <span className="text-[11px] font-black uppercase text-amber-400 shrink-0 mr-1 flex items-center gap-1">
                  🏆 Ligas:
                </span>
                <button
                  onClick={() => setLeagueFilter("all")}
                  className={`px-3 py-1.2 rounded-xl text-xs font-bold transition-all whitespace-nowrap shrink-0 ${
                    leagueFilter === "all"
                      ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent"
                  }`}
                >
                  Todas as Ligas ({countryFilter === "all" ? matches.length : filteredMatches.length})
                </button>
                {leaguesWithCounts.map(({ league, count }) => (
                  <button
                    key={league}
                    onClick={() => setLeagueFilter(league === leagueFilter ? "all" : league)}
                    className={`px-3 py-1.2 rounded-xl text-xs font-bold transition-all whitespace-nowrap shrink-0 flex items-center gap-1.5 ${
                      leagueFilter === league
                        ? "bg-amber-500/25 text-amber-200 border border-amber-500/50 shadow-sm"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-slate-800/60"
                    }`}
                  >
                    <span>{league}</span>
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${leagueFilter === league ? "bg-amber-500/30 text-amber-200" : "bg-slate-800 text-slate-400"}`}>
                      {count}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* TOP SECTION: Matches Side-by-Side (Horizontal Deck / Grid below League Filters) */}
            <div className="space-y-3 bg-slate-900/40 p-4 rounded-3xl border border-slate-800/80 shadow-md">
              {/* Header: Title, Controls & Carousel Arrows */}
              <div className="flex flex-wrap items-center justify-between gap-3 px-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
                    Partidas ({orderedMatches.length})
                  </span>
                  <span className="text-[10px] text-slate-500 hidden sm:inline">
                    • Clique para carregar os dados abaixo ou arraste para reordenar
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {/* Custom Order Indicator / Reset Button */}
                  {customMatchOrder.length > 0 && (
                    <button
                      onClick={handleResetOrder}
                      className="text-[10px] font-semibold text-slate-400 hover:text-amber-400 flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 border border-slate-800 hover:border-amber-500/40 transition"
                      title="Restaurar ordem original das partidas"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Restaurar Ordem</span>
                    </button>
                  )}

                  {/* Carousel Scroll Navigation Buttons (visible when in carousel mode) */}
                  {viewMode === "carousel" && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleScrollCarousel("left")}
                        className="p-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition"
                        title="Rolar para esquerda"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleScrollCarousel("right")}
                        className="p-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition"
                        title="Rolar para direita"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Sorting Selector */}
                  <div className="flex items-center gap-1.5 bg-slate-950 px-2 py-1 rounded-xl border border-slate-800 shadow-inner">
                    <ArrowUpDown className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <select
                      id="match-sort-selector"
                      value={sortOption}
                      onChange={(e) => handleSetSortOption(e.target.value as MatchSortOption)}
                      className="bg-transparent text-xs text-slate-300 font-semibold focus:outline-none cursor-pointer pr-1"
                      title="Opções de ordenação da grade"
                    >
                      <option value="debt_desc" className="bg-slate-900 text-white">🔥 Dívida de Gol (Diagnóstico)</option>
                      <option value="minute_desc" className="bg-slate-900 text-white">⏱️ Minuto (Mais avançados)</option>
                      <option value="minute_asc" className="bg-slate-900 text-white">⏱️ Minuto (Mais recentes)</option>
                      <option value="pressure_desc" className="bg-slate-900 text-white">⚡ Maior Pressão Ofensiva</option>
                      <option value="goals_desc" className="bg-slate-900 text-white">⚽ Mais Gols (Placar)</option>
                      <option value="corners_desc" className="bg-slate-900 text-white">🚩 Mais Escanteios</option>
                      <option value="league_asc" className="bg-slate-900 text-white">🌍 País & Liga (A-Z)</option>
                      <option value="team_asc" className="bg-slate-900 text-white">🛡️ Nome dos Times (A-Z)</option>
                      <option value="custom" className="bg-slate-900 text-white">✋ Ordem Personalizada (Manual)</option>
                    </select>
                  </div>

                  {/* View Mode Toggle */}
                  <div className="flex bg-slate-950 p-0.5 rounded-xl border border-slate-800">
                    <button
                      onClick={() => handleSetViewMode("carousel")}
                      className={`px-2 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
                        viewMode === "carousel"
                          ? "bg-slate-800 text-emerald-400 font-bold shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                      title="Carrossel Horizontal Lado a Lado"
                    >
                      <Columns3 className="w-3.5 h-3.5" />
                      <span className="text-[10px] hidden sm:inline">Lado a Lado</span>
                    </button>
                    <button
                      onClick={() => handleSetViewMode("grid")}
                      className={`px-2 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
                        viewMode === "grid"
                          ? "bg-slate-800 text-emerald-400 font-bold shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                      title="Grade Superior de Cards"
                    >
                      <Grid3X3 className="w-3.5 h-3.5" />
                      <span className="text-[10px] hidden sm:inline">Grade</span>
                    </button>
                    <button
                      onClick={() => handleSetViewMode("compact")}
                      className={`px-2 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
                        viewMode === "compact"
                          ? "bg-slate-800 text-emerald-400 font-bold shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                      title="Modo Compacto / Ticker Tape"
                    >
                      <List className="w-3.5 h-3.5" />
                      <span className="text-[10px] hidden sm:inline">Ticker</span>
                    </button>
                  </div>

                  <button
                    onClick={handleRefreshMatches}
                    disabled={isRefreshing}
                    className="px-2.5 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 hover:border-slate-700 transition flex items-center gap-1.5 text-xs font-semibold disabled:opacity-50 shadow-sm"
                    title="Atualizar partidas e limpar partidas terminadas"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isRefreshing ? "animate-spin" : ""}`} />
                    <span>Atualizar Partidas</span>
                  </button>
                </div>
              </div>

              {/* Cards Container Side-by-Side */}
              {orderedMatches.length === 0 ? (
                <div className="bg-slate-950/60 rounded-2xl border border-slate-800/80 p-8 text-center text-slate-400 space-y-3">
                  <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-emerald-400">
                    <Radio className="w-6 h-6 animate-pulse" />
                  </div>
                  <h3 className="text-sm font-bold text-white">Nenhuma partida ao vivo no momento</h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    As partidas transmitidas pelo crawler Python aparecerão aqui em tempo real. Partidas terminadas (FT) são removidas automaticamente da grade.
                  </p>
                  <div className="pt-2 flex items-center justify-center gap-2">
                    <button
                      onClick={handleRefreshMatches}
                      disabled={isRefreshing}
                      className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-emerald-950/40"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
                      Atualizar Lista de Partidas
                    </button>
                  </div>
                </div>
              ) : viewMode === "compact" ? (
                <CompactMatchTicker
                  matches={orderedMatches}
                  selectedMatchId={selectedMatch?.id || null}
                  onSelectMatch={setSelectedMatchId}
                  onDeleteMatch={(id) => handleDeleteMatch(id)}
                  rulesAnalysisMap={rulesAnalysisMap}
                  ratioConfigured={rulesConfig?.chancesPerGoalRatio ?? 3.0}
                  flashingMatchIds={flashingGoalMatchIds}
                />
              ) : viewMode === "carousel" ? (
                <div
                  ref={carouselContainerRef}
                  className="flex items-stretch gap-3.5 overflow-x-auto pb-2 pt-1 scroll-smooth"
                >
                  {orderedMatches.map((m, idx) => (
                    <div
                      key={m.id}
                      className="min-w-[280px] sm:min-w-[320px] max-w-[340px] shrink-0"
                    >
                      <MatchCard
                        match={m}
                        isSelected={selectedMatch?.id === m.id}
                        onSelect={() => setSelectedMatchId(m.id)}
                        onDeleteMatch={() => handleDeleteMatch(m.id)}
                        rulesAnalysis={rulesAnalysisMap[m.id]}
                        ratioConfigured={rulesConfig?.chancesPerGoalRatio ?? 3.0}
                        onMoveLeft={() => handleMoveMatch(m.id, "left")}
                        onMoveRight={() => handleMoveMatch(m.id, "right")}
                        canMoveLeft={idx > 0}
                        canMoveRight={idx < orderedMatches.length - 1}
                        onDragStart={() => handleDragStart(m.id)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={() => handleDropOnMatch(m.id)}
                        onDragEnd={() => setDraggedMatchId(null)}
                        isBeingDragged={draggedMatchId === m.id}
                        isFlashingGoal={Boolean(flashingGoalMatchIds[m.id])}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3.5 pt-1">
                  {orderedMatches.map((m, idx) => (
                    <MatchCard
                      key={m.id}
                      match={m}
                      isSelected={selectedMatch?.id === m.id}
                      onSelect={() => setSelectedMatchId(m.id)}
                      onDeleteMatch={() => handleDeleteMatch(m.id)}
                      rulesAnalysis={rulesAnalysisMap[m.id]}
                      ratioConfigured={rulesConfig?.chancesPerGoalRatio ?? 3.0}
                      onMoveLeft={() => handleMoveMatch(m.id, "left")}
                      onMoveRight={() => handleMoveMatch(m.id, "right")}
                      canMoveLeft={idx > 0}
                      canMoveRight={idx < orderedMatches.length - 1}
                      onDragStart={() => handleDragStart(m.id)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => handleDropOnMatch(m.id)}
                      onDragEnd={() => setDraggedMatchId(null)}
                      isBeingDragged={draggedMatchId === m.id}
                      isFlashingGoal={Boolean(flashingGoalMatchIds[m.id])}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* BOTTOM SECTION: Deep Match Analytics (Full Width below the side-by-side matches) */}
            <div id="match-detail-section" className="w-full scroll-mt-6">
              {selectedMatch ? (
                <MatchDetail
                  match={selectedMatch}
                  onAnalyzeWithAi={handleAnalyzeWithAi}
                  aiAnalysis={aiAnalysisMap[selectedMatch.id] || null}
                  isAiLoading={isAiLoading}
                  rulesAnalysis={rulesAnalysisMap[selectedMatch.id]}
                  ratioConfigured={rulesConfig?.chancesPerGoalRatio ?? 3.0}
                  onOpenRulesModal={() => {
                    setLocalConfigInitialTab("rules_engine");
                    setIsLocalConfigModalOpen(true);
                  }}
                />
              ) : (
                <div className="bg-slate-900 rounded-2xl border border-slate-800 p-12 text-center text-slate-400">
                  Selecione uma partida acima para visualizar os dados completos e gráficos.
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: ALERTS & RULES ENGINE */}
        {activeTab === "alerts" && (
          <AlertsManager
            rules={alertRules}
            logs={alertLogs}
            matches={matches}
            rulesConfig={rulesConfig}
            onUpdateRulesConfig={async (newCfg) => {
              try {
                const res = await fetch("/api/rules/config", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(newCfg),
                });
                if (res.ok) {
                  const data = await res.json();
                  setRulesConfig(data.config);
                  fetchRulesAnalysis();
                }
              } catch (err) {
                console.error("Erro ao sincronizar regras operacionais:", err);
              }
            }}
            onSaveRule={handleSaveRule}
            onDeleteRule={handleDeleteRule}
            onDeleteAlert={handleDeleteSingleAlert}
            onMarkAsRead={handleMarkAlertsAsRead}
            onClearLogs={handleClearAlerts}
            onTriggerTestAlert={handleTriggerTestAlert}
            onSelectMatch={handleSelectAndScrollToMatch}
          />
        )}
      </main>

      {/* Local File-Based Storage & Configuration Modal */}
      <LocalConfigModal
        isOpen={isLocalConfigModalOpen}
        onClose={() => setIsLocalConfigModalOpen(false)}
        initialTab={localConfigInitialTab}
        onConfigReloaded={() => {
          fetchRulesConfig();
          fetchRulesAnalysis();
          fetchAlerts();
        }}
      />

      {/* Goal Alert Toast Popup System */}
      <GoalAlertPopup
        goals={goalAlerts}
        onDismiss={(id) => setGoalAlerts((prev) => prev.filter((g) => g.id !== id))}
        onSelectMatch={handleSelectAndScrollToMatch}
      />
    </div>
  );
}
