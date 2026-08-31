import React, { useState, useEffect, useRef } from "react";
import {
  FolderArchive,
  Download,
  Upload,
  Save,
  FileJson,
  HardDrive,
  CheckCircle2,
  AlertCircle,
  X,
  KeyRound,
  Copy,
  Check,
  RefreshCw,
  Sliders,
  ShieldCheck,
  User,
  Zap,
  Bell,
  Building2,
  Terminal,
  Activity,
  SlidersHorizontal,
  Flame,
  Target,
  Sparkles,
  ShieldAlert,
  TrendingUp,
  Volume2,
  VolumeX,
  Plus,
  Trash2,
  Filter,
  Layers,
  HelpCircle,
  Clock,
  Radio,
  CheckSquare,
  Square,
  Play,
  RotateCcw,
  ListOrdered,
  ListFilter,
  Compass,
  Cpu,
  Gauge,
  Pencil,
} from "lucide-react";
import { safeFetchJson } from "../api";
import { useAuth } from "../context/AuthContext";
import {
  OperationalRulesConfig,
  AlertRule,
  CustomWebhookEndpoint,
  AVAILABLE_BOOKMAKERS,
  BookmakerId,
  BookmakerApiCredential,
  BookmakerApiMap,
  DEFAULT_BOOKMAKER_CREDENTIALS,
  AlertMetric,
  AlertOperator,
  AlertSeverity,
  DEFAULT_MODAL_CONFIG,
} from "../types";

type TabType = "rules_engine" | "alerts_noise" | "bookmakers" | "crawler" | "backup_profile";

interface LocalConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfigReloaded?: () => void;
  initialTab?: TabType;
}

export type { TabType };

const METRIC_OPTIONS: { value: AlertMetric; label: string }[] = [
  { value: "minute", label: "Minuto da Partida" },
  { value: "pressureHome", label: "Pressão Mandante (%)" },
  { value: "pressureAway", label: "Pressão Visitante (%)" },
  { value: "pressureDiff", label: "Diferença de Pressão" },
  { value: "xgDiff", label: "Diferença de xG" },
  { value: "totalXg", label: "xG Total Combinado" },
  { value: "dangerousAttacksLast10Home", label: "Ataques Perigosos Mandante (10m)" },
  { value: "dangerousAttacksLast10Away", label: "Ataques Perigosos Visitante (10m)" },
  { value: "chancesVariation5m", label: "Variação de Chances 5m (Δ%)" },
  { value: "cornersCombined", label: "Escanteios Combinados" },
  { value: "cornersHome", label: "Escanteios Mandante" },
  { value: "cornersAway", label: "Escanteios Visitante" },
  { value: "shotsOnTargetHome", label: "Chutes no Gol Mandante" },
  { value: "shotsOnTargetAway", label: "Chutes no Gol Visitante" },
  { value: "shotsOnTargetDiff", label: "Diferença de Chutes no Gol" },
  { value: "goalLeadDiff", label: "Diferença no Placar" },
  { value: "possessionHome", label: "Posse de Bola Mandante (%)" },
  { value: "possessionAway", label: "Posse de Bola Visitante (%)" },
  { value: "redCardHome", label: "Cartão Vermelho Mandante" },
  { value: "redCardAway", label: "Cartão Vermelho Visitante" },
];

export function LocalConfigModal({ isOpen, onClose, onConfigReloaded, initialTab }: LocalConfigModalProps) {
  const { userProfile, regenerateCrawlerToken, refreshLocalProfile } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>(initialTab || "rules_engine");

  useEffect(() => {
    if (initialTab && isOpen) {
      setActiveTab(initialTab);
    }
  }, [initialTab, isOpen]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [filePath, setFilePath] = useState<string>("data/bacanalive_config.json");
  const [copiedToken, setCopiedToken] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Core Config States
  const [displayNameInput, setDisplayNameInput] = useState<string>("Trader Local Pro");
  const [rulesConfig, setRulesConfig] = useState<OperationalRulesConfig>({ ...DEFAULT_MODAL_CONFIG });
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [customWebhooks, setCustomWebhooks] = useState<CustomWebhookEndpoint[]>([]);
  const [bookmakerCreds, setBookmakerCreds] = useState<BookmakerApiMap>({ ...DEFAULT_BOOKMAKER_CREDENTIALS });
  const [noiseReduction, setNoiseReduction] = useState({
    hideFinishedMatches: true,
    mutedMatchIds: {} as Record<string, boolean>,
    enabledCategories: {
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
    } as Record<string, boolean>,
    selectedMatchFilter: "all",
  });
  const [testingBookmakerId, setTestingBookmakerId] = useState<string | null>(null);
  const [testResultMsg, setTestResultMsg] = useState<{ id: string; success: boolean; msg: string } | null>(null);

  // New Alert Rule Form
  const [isAddingRule, setIsAddingRule] = useState<boolean>(false);
  const [newRuleName, setNewRuleName] = useState<string>("");
  const [newRuleDesc, setNewRuleDesc] = useState<string>("");
  const [newRuleSeverity, setNewRuleSeverity] = useState<AlertSeverity>("opportunity");
  const [newRuleLogic, setNewRuleLogic] = useState<"AND" | "OR">("AND");
  const [newRuleSound, setNewRuleSound] = useState<boolean>(true);
  const [newRuleConditions, setNewRuleConditions] = useState<
    Array<{ metric: AlertMetric; operator: AlertOperator; value: number }>
  >([{ metric: "pressureHome", operator: ">=", value: 75 }]);

  // Edit Alert Rule Form
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [editRuleName, setEditRuleName] = useState<string>("");
  const [editRuleDesc, setEditRuleDesc] = useState<string>("");
  const [editRuleSeverity, setEditRuleSeverity] = useState<AlertSeverity>("opportunity");
  const [editRuleLogic, setEditRuleLogic] = useState<"AND" | "OR">("AND");
  const [editRuleSound, setEditRuleSound] = useState<boolean>(true);
  const [editRuleConditions, setEditRuleConditions] = useState<
    Array<{ metric: AlertMetric; operator: AlertOperator; value: number }>
  >([]);

  // New Custom Webhook Form
  const [isAddingWebhook, setIsAddingWebhook] = useState<boolean>(false);
  const [newWebhookName, setNewWebhookName] = useState<string>("");
  const [newWebhookSlug, setNewWebhookSlug] = useState<string>("");

  // Faxina State
  const [isExecutingFaxina, setIsExecutingFaxina] = useState<boolean>(false);
  const [faxinaStatus, setFaxinaStatus] = useState<string | null>(null);

  const handleExecuteFaxina = async () => {
    setIsExecutingFaxina(true);
    setFaxinaStatus(null);
    try {
      const data = await safeFetchJson<{ success: boolean; removedFinishedCount: number; message: string }>("/api/matches/faxina", {
        method: "POST"
      });
      if (data?.success) {
        setFaxinaStatus(data.message || `Faxina concluída! ${data.removedFinishedCount} jogos encerrados removidos.`);
        if (onConfigReloaded) onConfigReloaded();
      }
    } catch (err: any) {
      setFaxinaStatus(`Erro na faxina: ${err.message || "Erro desconhecido"}`);
    } finally {
      setIsExecutingFaxina(false);
      setTimeout(() => setFaxinaStatus(null), 5000);
    }
  };

  const fetchFullConfig = async () => {
    setLoading(true);
    try {
      const data = await safeFetchJson<{ config: any; filePath?: string }>("/api/config");
      if (data?.config) {
        const c = data.config;
        if (c.userProfile?.displayName) setDisplayNameInput(c.userProfile.displayName);
        if (c.operationalConfig) {
          setRulesConfig({
            ...DEFAULT_MODAL_CONFIG,
            ...c.operationalConfig,
            bookmakerCredentials: {
              ...DEFAULT_BOOKMAKER_CREDENTIALS,
              ...(c.operationalConfig.bookmakerCredentials || {}),
            },
          });
          if (c.operationalConfig.bookmakerCredentials) {
            setBookmakerCreds({
              ...DEFAULT_BOOKMAKER_CREDENTIALS,
              ...c.operationalConfig.bookmakerCredentials,
            });
          }
        }
        if (Array.isArray(c.alertRules)) setAlertRules(c.alertRules);
        if (Array.isArray(c.customWebhooks)) setCustomWebhooks(c.customWebhooks);
        if (c.noiseReduction) {
          setNoiseReduction((prev) => ({
            ...prev,
            ...c.noiseReduction,
            enabledCategories: {
              ...prev.enabledCategories,
              ...(c.noiseReduction.enabledCategories || {}),
            },
          }));
        }
      }
      if (data?.filePath) setFilePath(data.filePath);
    } catch (err) {
      console.error("Erro ao carregar configurações locais:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchFullConfig();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Master Save Handler
  const handleSaveToDisk = async (customPayload?: any, successMessage?: string) => {
    try {
      setLoading(true);
      const payload = customPayload || {
        userProfile: {
          ...userProfile,
          displayName: displayNameInput.trim() || "Trader Local Pro",
          role: "admin",
          status: "approved",
          crawlerToken: userProfile?.crawlerToken || "footstats-crawler-live-key-99",
          mode: "local_standalone",
        },
        operationalConfig: {
          ...rulesConfig,
          bookmakerCredentials: bookmakerCreds,
        },
        alertRules,
        customWebhooks,
        noiseReduction,
      };

      const res = await safeFetchJson<{ success: boolean; config: any }>("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res?.success) {
        setSaveStatus(successMessage || "Configurações salvas e gravadas no disco com sucesso!");
        if (onConfigReloaded) onConfigReloaded();
        setTimeout(() => setSaveStatus(null), 3500);
      }
    } catch (err: any) {
      setSaveStatus(`Erro ao salvar no disco: ${err.message || "Erro desconhecido"}`);
    } finally {
      setLoading(false);
    }
  };

  // Preset Ratio Buttons
  const applyRatioPreset = (val: number) => {
    const updated = { ...rulesConfig, chancesPerGoalRatio: val };
    setRulesConfig(updated);
    handleSaveToDisk(
      {
        operationalConfig: {
          ...updated,
          bookmakerCredentials: bookmakerCreds,
        },
      },
      `Índice ${val.toFixed(1)}:1 aplicado e gravado no disco!`
    );
  };

  // Bookmakers Toggles
  const handleToggleBookmaker = (id: BookmakerId) => {
    const currentList = rulesConfig.enabledBookmakers || [];
    const isCurrentlyEnabled = currentList.includes(id);
    const updatedList = isCurrentlyEnabled
      ? currentList.filter((b) => b !== id)
      : [...currentList, id];

    const updatedCreds: BookmakerApiMap = {
      ...bookmakerCreds,
      [id]: {
        ...bookmakerCreds[id],
        enabled: !isCurrentlyEnabled,
      },
    };

    const updatedConfig = {
      ...rulesConfig,
      enabledBookmakers: updatedList,
      bookmakerCredentials: updatedCreds,
    };

    setRulesConfig(updatedConfig);
    setBookmakerCreds(updatedCreds);

    handleSaveToDisk(
      {
        operationalConfig: updatedConfig,
      },
      `Casa ${AVAILABLE_BOOKMAKERS.find((b) => b.id === id)?.name || id} ${!isCurrentlyEnabled ? "ativada" : "desativada"}!`
    );
  };

  const handleSelectAllBookmakers = (enabled: boolean) => {
    const updatedList = enabled ? AVAILABLE_BOOKMAKERS.map((b) => b.id) : [];
    const updatedCreds: BookmakerApiMap = { ...bookmakerCreds };
    for (const b of AVAILABLE_BOOKMAKERS) {
      if (updatedCreds[b.id]) {
        updatedCreds[b.id] = { ...updatedCreds[b.id], enabled };
      }
    }

    const updatedConfig = {
      ...rulesConfig,
      enabledBookmakers: updatedList,
      bookmakerCredentials: updatedCreds,
    };

    setRulesConfig(updatedConfig);
    setBookmakerCreds(updatedCreds);

    handleSaveToDisk(
      { operationalConfig: updatedConfig },
      enabled ? "Todas as 9 casas de apostas ativadas!" : "Todas as casas desativadas."
    );
  };

  const handleSelectExchangesOnly = () => {
    const exchanges: BookmakerId[] = ["betfair", "pinnacle"];
    const updatedCreds: BookmakerApiMap = { ...bookmakerCreds };
    for (const b of AVAILABLE_BOOKMAKERS) {
      if (updatedCreds[b.id]) {
        updatedCreds[b.id] = { ...updatedCreds[b.id], enabled: exchanges.includes(b.id) };
      }
    }

    const updatedConfig = {
      ...rulesConfig,
      enabledBookmakers: exchanges,
      bookmakerCredentials: updatedCreds,
    };

    setRulesConfig(updatedConfig);
    setBookmakerCreds(updatedCreds);

    handleSaveToDisk(
      { operationalConfig: updatedConfig },
      "Modo Exchange & Sharp (Betfair / Pinnacle) ativado!"
    );
  };

  const handleUpdateBookmakerKey = (id: BookmakerId, key: string) => {
    const updatedCreds: BookmakerApiMap = {
      ...bookmakerCreds,
      [id]: {
        ...bookmakerCreds[id],
        apiKey: key,
        connectionStatus: key.trim().length > 3 ? "connected" : "unconfigured",
      },
    };
    setBookmakerCreds(updatedCreds);
  };

  const handleTestBookmakerApi = async (id: BookmakerId) => {
    setTestingBookmakerId(id);
    setTestResultMsg(null);
    try {
      const res = await safeFetchJson<{
        success: boolean;
        latencyMs: number;
        message: string;
      }>(`/api/bookmakers/${id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bookmakerCreds[id] || {}),
      });

      if (res?.success) {
        setTestResultMsg({
          id,
          success: true,
          msg: `Conectado! Latência: ${res.latencyMs}ms`,
        });
      } else {
        setTestResultMsg({
          id,
          success: false,
          msg: res?.message || "Chave não configurada.",
        });
      }
    } catch (err: any) {
      setTestResultMsg({
        id,
        success: false,
        msg: `Erro de teste: ${err.message}`,
      });
    } finally {
      setTestingBookmakerId(null);
    }
  };

  // Toggle Alert Rule in Server List
  const handleToggleAlertRule = (ruleId: string) => {
    const updated = alertRules.map((r) => (r.id === ruleId ? { ...r, enabled: !r.enabled } : r));
    setAlertRules(updated);
    handleSaveToDisk({ alertRules: updated }, "Regra de alerta atualizada e salva no disco!");
  };

  const handleDeleteAlertRule = (ruleId: string) => {
    if (window.confirm("Deseja excluir permanentemente esta regra de alerta do disco?")) {
      const updated = alertRules.filter((r) => r.id !== ruleId);
      setAlertRules(updated);
      handleSaveToDisk({ alertRules: updated }, "Regra de alerta excluída do disco!");
    }
  };

  const handleCreateNewAlertRule = () => {
    if (!newRuleName.trim()) return;
    const newRule: AlertRule = {
      id: `rule-${Date.now()}`,
      name: newRuleName.trim(),
      description: newRuleDesc.trim() || undefined,
      matchId: "all",
      enabled: true,
      logic: newRuleLogic,
      severity: newRuleSeverity,
      soundEnabled: newRuleSound,
      browserNotification: true,
      messageTemplate: `🔥 ALERTA: {teamHome} x {teamAway} atingiu condição no minuto {minute}'!`,
      conditions: newRuleConditions,
      triggerCount: 0,
    };

    const updated = [newRule, ...alertRules];
    setAlertRules(updated);
    setIsAddingRule(false);
    setNewRuleName("");
    setNewRuleDesc("");
    handleSaveToDisk({ alertRules: updated }, "Nova regra de alerta salva no disco com sucesso!");
  };

  const handleStartEditRule = (rule: AlertRule) => {
    setEditingRuleId(rule.id);
    setEditRuleName(rule.name);
    setEditRuleDesc(rule.description || "");
    setEditRuleSeverity(rule.severity);
    setEditRuleLogic(rule.logic || "AND");
    setEditRuleSound(rule.soundEnabled ?? true);
    setEditRuleConditions(
      rule.conditions && rule.conditions.length > 0
        ? rule.conditions.map((c) => ({ ...c }))
        : [{ metric: "pressureHome", operator: ">=", value: 75 }]
    );
    setIsAddingRule(false);
  };

  const handleCancelEditRule = () => {
    setEditingRuleId(null);
  };

  const handleSaveEditRule = () => {
    if (!editingRuleId || !editRuleName.trim()) return;
    const updated = alertRules.map((r) => {
      if (r.id === editingRuleId) {
        return {
          ...r,
          name: editRuleName.trim(),
          description: editRuleDesc.trim() || undefined,
          severity: editRuleSeverity,
          logic: editRuleLogic,
          soundEnabled: editRuleSound,
          conditions: editRuleConditions,
        };
      }
      return r;
    });
    setAlertRules(updated);
    setEditingRuleId(null);
    handleSaveToDisk({ alertRules: updated }, "Regra de alerta atualizada e salva no disco!");
  };

  const handleAddConditionToEdit = () => {
    setEditRuleConditions([
      ...editRuleConditions,
      { metric: "cornersCombined", operator: ">=", value: 8 },
    ]);
  };

  const handleRemoveConditionFromEdit = (idx: number) => {
    if (editRuleConditions.length > 1) {
      setEditRuleConditions(editRuleConditions.filter((_, i) => i !== idx));
    }
  };

  const handleAddConditionToNew = () => {
    setNewRuleConditions([
      ...newRuleConditions,
      { metric: "minute", operator: ">=", value: 60 },
    ]);
  };

  const handleRemoveConditionFromNew = (idx: number) => {
    if (newRuleConditions.length > 1) {
      setNewRuleConditions(newRuleConditions.filter((_, i) => i !== idx));
    }
  };

  // Noise Reduction Toggles
  const handleToggleNoiseCategory = (cat: string) => {
    const nextCats = {
      ...noiseReduction.enabledCategories,
      [cat]: !noiseReduction.enabledCategories[cat],
    };
    const nextNoise = { ...noiseReduction, enabledCategories: nextCats };
    setNoiseReduction(nextNoise);
    handleSaveToDisk({ noiseReduction: nextNoise }, "Filtro de redução de ruído salvo!");
  };

  // Custom Webhook Management
  const handleToggleWebhook = (whId: string) => {
    const updated = customWebhooks.map((w) => (w.id === whId ? { ...w, active: !w.active } : w));
    setCustomWebhooks(updated);
    handleSaveToDisk({ customWebhooks: updated }, "Webhook atualizado no disco!");
  };

  const handleDeleteWebhook = (whId: string) => {
    if (window.confirm("Deseja excluir este endpoint de webhook?")) {
      const updated = customWebhooks.filter((w) => w.id !== whId);
      setCustomWebhooks(updated);
      handleSaveToDisk({ customWebhooks: updated }, "Webhook excluído do disco!");
    }
  };

  const handleCreateWebhook = () => {
    if (!newWebhookName.trim()) return;
    const cleanSlug = (newWebhookSlug || newWebhookName)
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9_-]+/g, "-");

    const newWh: CustomWebhookEndpoint = {
      id: `wh-${Date.now()}`,
      name: newWebhookName.trim(),
      slug: cleanSlug || `wh-${Date.now()}`,
      secretToken: `sec_${Math.random().toString(36).substring(2, 12)}`,
      description: "Endpoint webhook customizado para ingestão em tempo real.",
      active: true,
      asyncMode: true,
      autoTriggerAlerts: true,
      autoComputeMomentum: true,
      targetLeague: "Todas as Ligas",
      createdAt: new Date().toISOString(),
      totalCalls: 0,
      lastStatus: "ok",
    };

    const updated = [newWh, ...customWebhooks];
    setCustomWebhooks(updated);
    setIsAddingWebhook(false);
    setNewWebhookName("");
    setNewWebhookSlug("");
    handleSaveToDisk({ customWebhooks: updated }, "Novo endpoint Webhook gravado no disco!");
  };

  // Export / Import
  const handleExportDownload = () => {
    try {
      const full = {
        version: "2.5.0-standalone-local",
        savedAt: new Date().toISOString(),
        userProfile: {
          displayName: displayNameInput.trim() || "Trader Local Pro",
          role: "admin",
          status: "approved",
          crawlerToken: userProfile?.crawlerToken || "footstats-crawler-live-key-99",
          mode: "local_standalone",
        },
        operationalConfig: {
          ...rulesConfig,
          bookmakerCredentials: bookmakerCreds,
        },
        alertRules,
        customWebhooks,
        noiseReduction,
      };

      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(full, null, 2));
      const downloadAnchor = document.createElement("a");
      downloadAnchor.setAttribute("href", dataStr);
      downloadAnchor.setAttribute("download", `bacanalive_config_${new Date().toISOString().slice(0, 10)}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      setSaveStatus("Arquivo bacanalive_config.json exportado com sucesso!");
      setTimeout(() => setSaveStatus(null), 3500);
    } catch (e: any) {
      setSaveStatus(`Erro ao exportar: ${e.message}`);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileReader = new FileReader();
    if (e.target.files && e.target.files[0]) {
      fileReader.readAsText(e.target.files[0], "UTF-8");
      fileReader.onload = async (event) => {
        try {
          const parsed = JSON.parse(event.target?.result as string);
          const res = await safeFetchJson<{ success: boolean; message?: string; config?: any }>("/api/config/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(parsed),
          });
          if (res?.success) {
            setSaveStatus("Configurações importadas e salvas com sucesso no disco!");
            await fetchFullConfig();
            await refreshLocalProfile();
            if (onConfigReloaded) onConfigReloaded();
          } else {
            setSaveStatus(`Falha na importação: ${res?.message || "Erro desconhecido"}`);
          }
        } catch (err: any) {
          setSaveStatus(`Arquivo JSON inválido: ${err.message}`);
        }
        setTimeout(() => setSaveStatus(null), 4000);
      };
    }
  };

  const handleResetToDefaults = async () => {
    if (window.confirm("Atenção: Deseja restaurar todas as configurações para o padrão de fábrica?")) {
      try {
        const res = await safeFetchJson<{ success: boolean }>("/api/config/reset", { method: "POST" });
        if (res?.success) {
          setSaveStatus("Configurações restauradas para o padrão com sucesso!");
          await fetchFullConfig();
          if (onConfigReloaded) onConfigReloaded();
          setTimeout(() => setSaveStatus(null), 3500);
        }
      } catch (err: any) {
        setSaveStatus(`Erro ao resetar: ${err.message}`);
      }
    }
  };

  const copyToken = () => {
    const token = userProfile?.crawlerToken || "footstats-crawler-live-key-99";
    navigator.clipboard.writeText(token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const handleRegenerateToken = async () => {
    if (window.confirm("Gerar um novo Token Local para seus Crawlers? Você precisará atualizar seus scripts Python.")) {
      const newToken = await regenerateCrawlerToken();
      await fetchFullConfig();
      setSaveStatus("Novo token gerado e salvo no arquivo de configuração!");
      setTimeout(() => setSaveStatus(null), 3000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/85 backdrop-blur-md">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-150">
        {/* Top Header */}
        <div className="p-4 sm:p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/70">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-gradient-to-tr from-emerald-500/20 to-teal-500/20 border border-emerald-500/40 rounded-xl text-emerald-400 shadow-sm">
              <HardDrive className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-black text-white text-base tracking-tight">Central de Configuração Local & Motor</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> Standalone Local
                </span>
                <span className="text-[10px] text-slate-400 font-mono hidden md:inline">
                  data/bacanalive_config.json
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                Controle unificado de regras de Diagnóstico, casas de apostas, alertas, ruído e ingestão Python.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleSaveToDisk()}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-md shadow-emerald-900/30 transition active:scale-95 disabled:opacity-50"
            >
              <Save className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Salvar Tudo no Disco</span>
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 px-4 py-2 bg-slate-950/90 border-b border-slate-800 overflow-x-auto scrollbar-none">
          <button
            onClick={() => setActiveTab("rules_engine")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              activeTab === "rules_engine"
                ? "bg-slate-800 text-amber-300 border border-amber-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Motor de Regras & 3:1</span>
          </button>

          <button
            onClick={() => setActiveTab("alerts_noise")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              activeTab === "alerts_noise"
                ? "bg-slate-800 text-emerald-300 border border-emerald-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Bell className="w-3.5 h-3.5 text-emerald-400" />
            <span>Alertas & Redução de Ruído</span>
            {alertRules.length > 0 && (
              <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-900 text-emerald-300 font-mono">
                {alertRules.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("bookmakers")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              activeTab === "bookmakers"
                ? "bg-slate-800 text-cyan-300 border border-cyan-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Building2 className="w-3.5 h-3.5 text-cyan-400" />
            <span>Casas & Exchange</span>
            <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-900 text-cyan-300 font-mono">
              {rulesConfig.enabledBookmakers?.length ?? 8}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("crawler")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              activeTab === "crawler"
                ? "bg-slate-800 text-purple-300 border border-purple-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Terminal className="w-3.5 h-3.5 text-purple-400" />
            <span>Crawler Python & Webhooks</span>
          </button>

          <button
            onClick={() => setActiveTab("backup_profile")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              activeTab === "backup_profile"
                ? "bg-slate-800 text-slate-200 border border-slate-700 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <FolderArchive className="w-3.5 h-3.5 text-slate-400" />
            <span>Backup & Perfil</span>
          </button>
        </div>

        {/* Tab Body */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-6 text-sm flex-1">
          {saveStatus && (
            <div className="p-3 bg-emerald-500/15 border border-emerald-500/40 rounded-xl text-emerald-300 flex items-center gap-2 text-xs animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{saveStatus}</span>
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 1: MOTOR DE REGRAS & PARÂMETROS 3:1                   */}
          {/* ======================================================== */}
          {activeTab === "rules_engine" && (
            <div className="space-y-6">
              {/* Parâmetro Central do Radar */}
              <div className="p-4 bg-slate-950/70 border border-amber-500/30 rounded-2xl space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-amber-500/10 rounded-lg text-amber-400">
                      <Zap className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Parâmetro Central do Radar (Diagnóstico)</h4>
                      <p className="text-xs text-slate-400">
                        Proporção de Chances Claras (CC) necessárias para justificar 1 gol na dívida.
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-2xl font-black text-amber-400 font-mono">
                      {(rulesConfig.chancesPerGoalRatio || 3.0).toFixed(1)}:1
                    </span>
                  </div>
                </div>

                {/* Ratio Presets */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                  {[
                    { ratio: 2.5, label: "2.5:1 (Ultra Agressivo)", desc: "1 gol a cada 2.5 CC" },
                    { ratio: 3.0, label: "3.0:1 (Oficial / Padrão)", desc: "1 gol a cada 3.0 CC" },
                    { ratio: 3.5, label: "3.5:1 (Conservador)", desc: "1 gol a cada 3.5 CC" },
                    { ratio: 4.0, label: "4.0:1 (Ultra Seguro)", desc: "1 gol a cada 4.0 CC" },
                  ].map((p) => {
                    const isSelected = Math.abs(rulesConfig.chancesPerGoalRatio - p.ratio) < 0.05;
                    return (
                      <button
                        key={p.ratio}
                        onClick={() => applyRatioPreset(p.ratio)}
                        className={`p-2.5 rounded-xl text-left border transition-all ${
                          isSelected
                            ? "bg-amber-500/20 border-amber-500 text-amber-300 shadow-md shadow-amber-950/40"
                            : "bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700"
                        }`}
                      >
                        <div className="font-bold text-xs">{p.label}</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">{p.desc}</div>
                      </button>
                    );
                  })}
                </div>

                {/* Manual Ratio Slider */}
                <div>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>Ajuste Fino Manual do Ratio:</span>
                    <span className="font-mono text-amber-300 font-bold">{rulesConfig.chancesPerGoalRatio.toFixed(1)}:1</span>
                  </div>
                  <input
                    type="range"
                    min="1.0"
                    max="6.0"
                    step="0.1"
                    value={rulesConfig.chancesPerGoalRatio}
                    onChange={(e) => setRulesConfig({ ...rulesConfig, chancesPerGoalRatio: parseFloat(e.target.value) })}
                    className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-400"
                  />
                  <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                    <span>1.0:1 (Mínimo)</span>
                    <span>3.0:1 (Padrão)</span>
                    <span>6.0:1 (Máximo)</span>
                  </div>
                </div>
              </div>

              {/* Taxas de Ritmo e Janelas de Minutos */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
                  <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-cyan-400" />
                    Taxas Máximas de Ritmo (min/CC)
                  </h5>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">
                      Taxa Máxima Geral de Ritmo (min/CC)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.5"
                        min="5"
                        max="30"
                        value={rulesConfig.ccRateMaxMinutes}
                        onChange={(e) => setRulesConfig({ ...rulesConfig, ccRateMaxMinutes: parseFloat(e.target.value) || 15.0 })}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                      />
                      <span className="text-xs text-slate-400 whitespace-nowrap">min/CC</span>
                    </div>
                    <span className="text-[10px] text-slate-500">Padrão: 15.0 min/CC para qualificar como jogo ativo</span>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 block mb-1">
                      Taxa Máxima Forte / Premium (min/CC)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.5"
                        min="3"
                        max="20"
                        value={rulesConfig.ccRateForteMaxMinutes}
                        onChange={(e) => setRulesConfig({ ...rulesConfig, ccRateForteMaxMinutes: parseFloat(e.target.value) || 12.0 })}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                      />
                      <span className="text-xs text-slate-400 whitespace-nowrap">min/CC</span>
                    </div>
                    <span className="text-[10px] text-slate-500">Padrão: 12.0 min/CC para disparar alertas Over/Back Premium</span>
                  </div>
                </div>

                <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
                  <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Filter className="w-3.5 h-3.5 text-emerald-400" />
                    Janela de Minutos para Alertas
                  </h5>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Minuto Inicial</label>
                      <input
                        type="number"
                        min="1"
                        max="80"
                        value={rulesConfig.minMinuteAlert}
                        onChange={(e) => setRulesConfig({ ...rulesConfig, minMinuteAlert: parseInt(e.target.value) || 10 })}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Minuto Final</label>
                      <input
                        type="number"
                        min="50"
                        max="95"
                        value={rulesConfig.maxMinuteAlert}
                        onChange={(e) => setRulesConfig({ ...rulesConfig, maxMinuteAlert: parseInt(e.target.value) || 88 })}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Margem de Dívida xG</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0.2"
                      max="3.0"
                      value={rulesConfig.debtMarginXG}
                      onChange={(e) => setRulesConfig({ ...rulesConfig, debtMarginXG: parseFloat(e.target.value) || 1.0 })}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Módulos de Regras Operacionais do Terminal Python */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-amber-400" />
                    Módulos de Regras Operacionais do Terminal Python
                  </h5>
                  <span className="text-[11px] text-slate-400">Ative ou desative cada estratégia</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {[
                    { key: "enableCodigo31", title: "Diagnóstico Clássico", desc: "Alerta de Dívida de Gols e Over Geral", icon: <Flame className="w-4 h-4 text-amber-400" /> },
                    { key: "enableTripleDebt", title: "Trinca de Dívidas (CC + xG + xGOT)", desc: "Convergência de 3 métricas de gols atrasados", icon: <Sparkles className="w-4 h-4 text-purple-400" /> },
                    { key: "enablePressaoVendavel", title: "Pressão Vendável & Ineficiência", desc: "Super pressão sem gols convertidos", icon: <Zap className="w-4 h-4 text-yellow-400" /> },
                    { key: "enableDominantTrailing", title: "Back Dominante em Desvantagem", desc: "Favorito perdendo ou empatando com domínio total", icon: <Target className="w-4 h-4 text-emerald-400" /> },
                    { key: "enableV12OverBack", title: "V12 Over & Back Alavancado", desc: "Alta probabilidade estatística de vitória ou +1.5 Gols", icon: <TrendingUp className="w-4 h-4 text-cyan-400" /> },
                    { key: "enableImminentGoal", title: "Gol Iminente / Surto 5m", desc: "Dispara com variação repentina de +50% no ritmo recente", icon: <Zap className="w-4 h-4 text-rose-400" /> },
                    { key: "enableFunilCantos", title: "Funil de Cantos HT & FT", desc: "Cantos Limite no 1T (+35') e 2T (+80')", icon: <TrendingUp className="w-4 h-4 text-teal-400" /> },
                    { key: "enableRaceToCorners", title: "Race to Corners (3, 5, 7, 9)", desc: "Dominância na corrida de escanteios", icon: <Target className="w-4 h-4 text-blue-400" /> },
                    { key: "enableJogoQuenteCards", title: "Jogo Quente / Cartões", desc: "Mais de 18 faltas ou clima tenso em clássicos", icon: <ShieldAlert className="w-4 h-4 text-amber-400" /> },
                    { key: "enableRiscoExpulsao", title: "Risco de Expulsão / Vermelho", desc: "Detecção de entradas duras e risco de 2º amarelo", icon: <ShieldAlert className="w-4 h-4 text-rose-500" /> },
                    { key: "enableAmbasMarcamBTTS", title: "Ambas Marcam (BTTS Sim)", desc: "Jogo aberto com xG e perigo bilateral", icon: <Target className="w-4 h-4 text-emerald-400" /> },
                    { key: "enableUnderValue", title: "Under Value / Desaceleração", desc: "Oportunidade em Under Gols / Lay quando ritmo trava", icon: <ShieldCheck className="w-4 h-4 text-indigo-400" /> },
                    { key: "enableViradaImprovavel", title: "Virada Improvável (Lay Zebra)", desc: "Favorito massacrando mas perdendo no placar", icon: <Zap className="w-4 h-4 text-orange-400" /> },
                    { key: "enableCashoutProativo", title: "Cashout Proativo / Fechamento", desc: "Aviso de saída de posição com queda de ritmo", icon: <AlertCircle className="w-4 h-4 text-rose-400" /> },
                  ].map((m) => {
                    const isEnabled = Boolean((rulesConfig as any)[m.key]);
                    return (
                      <div
                        key={m.key}
                        onClick={() => {
                          const updated = { ...rulesConfig, [m.key]: !isEnabled };
                          setRulesConfig(updated);
                        }}
                        className={`p-3 rounded-xl border cursor-pointer transition flex items-start justify-between gap-3 select-none ${
                          isEnabled
                            ? "bg-slate-900/90 border-emerald-500/40 text-slate-200"
                            : "bg-slate-950/40 border-slate-800/80 text-slate-500 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          <div className="mt-0.5">{m.icon}</div>
                          <div>
                            <div className="font-bold text-xs text-white">{m.title}</div>
                            <div className="text-[11px] text-slate-400">{m.desc}</div>
                          </div>
                        </div>
                        <div
                          className={`w-9 h-5 rounded-full transition-colors relative shrink-0 mt-0.5 ${
                            isEnabled ? "bg-emerald-500" : "bg-slate-800"
                          }`}
                        >
                          <div
                            className={`w-3.5 h-3.5 rounded-full bg-white transition-transform absolute top-0.5 left-0.5 ${
                              isEnabled ? "translate-x-4" : ""
                            }`}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 2: ALERTAS & REDUÇÃO DE RUÍDO                         */}
          {/* ======================================================== */}
          {activeTab === "alerts_noise" && (
            <div className="space-y-6">
              {/* Painel de Redução de Ruído */}
              <div className="p-4 bg-slate-950/70 border border-emerald-500/30 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">
                      <Filter className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Painel de Configuração Rápida & Redução de Ruído</h4>
                      <p className="text-xs text-slate-400">
                        Controle quais tipos de notificações chegam ao seu terminal e filtre ruídos de jogos frios.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        const allOn: Record<string, boolean> = {};
                        Object.keys(noiseReduction.enabledCategories).forEach((k) => (allOn[k] = true));
                        setNoiseReduction({ ...noiseReduction, enabledCategories: allOn });
                      }}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-semibold rounded-lg border border-slate-700"
                    >
                      Ativar Todas
                    </button>
                    <button
                      onClick={() => {
                        const debtsOnly: Record<string, boolean> = {
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
                        };
                        setNoiseReduction({ ...noiseReduction, enabledCategories: debtsOnly });
                      }}
                      className="px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-[11px] font-semibold rounded-lg border border-amber-500/30"
                    >
                      Apenas Dívidas
                    </button>
                  </div>
                </div>

                {/* Hide Finished Matches toggle */}
                <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-cyan-400" />
                    <div>
                      <span className="text-xs font-bold text-slate-200">Ocultar Partidas Finalizadas (FT)</span>
                      <p className="text-[11px] text-slate-400">Mantém o feed limpo exibindo apenas jogos rolando ao vivo (1H / 2H / HT)</p>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={noiseReduction.hideFinishedMatches}
                    onChange={(e) => setNoiseReduction({ ...noiseReduction, hideFinishedMatches: e.target.checked })}
                    className="w-4 h-4 accent-emerald-500 rounded cursor-pointer"
                  />
                </div>

                {/* Categories Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                  {[
                    { id: "imminent_goal", name: "Gols Iminentes (5m)" },
                    { id: "back_dominant", name: "Back Dominante" },
                    { id: "triple_debt", name: "Trinca de Dívidas" },
                    { id: "goal_debt_over", name: "Over Gols Devendo" },
                    { id: "corners", name: "Cantos & Funil" },
                    { id: "cards", name: "Cartões & Expulsão" },
                    { id: "btts_ambas", name: "Ambas Marcam (BTTS)" },
                    { id: "under_value", name: "Under Value" },
                    { id: "virada_turnaround", name: "Virada Improvável" },
                    { id: "cashout", name: "Cashout Proativo" },
                    { id: "pressao_blitz", name: "Pressão & Blitz" },
                  ].map((cat) => {
                    const active = noiseReduction.enabledCategories[cat.id] !== false;
                    return (
                      <button
                        key={cat.id}
                        onClick={() => handleToggleNoiseCategory(cat.id)}
                        className={`p-2 rounded-xl text-left border transition text-xs font-semibold flex items-center justify-between ${
                          active
                            ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
                            : "bg-slate-900/60 border-slate-800 text-slate-500 hover:border-slate-700"
                        }`}
                      >
                        <span className="truncate">{cat.name}</span>
                        {active ? <CheckSquare className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> : <Square className="w-3.5 h-3.5 text-slate-600 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Regras de Alerta Ativas no Servidor */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                      <Bell className="w-3.5 h-3.5 text-cyan-400" />
                      Regras de Alerta Ativas no Servidor ({alertRules.length})
                    </h5>
                    <p className="text-[11px] text-slate-400">Regras customizadas avaliadas em tempo real a cada pacote do Crawler.</p>
                  </div>
                  <button
                    onClick={() => setIsAddingRule(!isAddingRule)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition shadow-sm"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Nova Regra de Alerta
                  </button>
                </div>

                {/* Form to Add New Rule */}
                {isAddingRule && (
                  <div className="p-4 bg-slate-900 border border-emerald-500/40 rounded-xl space-y-3 animate-in fade-in">
                    <h6 className="font-bold text-xs text-emerald-300">Criar Nova Regra de Alerta</h6>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] text-slate-400 block mb-1">Nome da Regra</label>
                        <input
                          type="text"
                          value={newRuleName}
                          onChange={(e) => setNewRuleName(e.target.value)}
                          placeholder="Ex: Pressão Extrema com xG Alto"
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-400 block mb-1">Severidade</label>
                        <select
                          value={newRuleSeverity}
                          onChange={(e) => setNewRuleSeverity(e.target.value as AlertSeverity)}
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                        >
                          <option value="opportunity">Oportunidade (Verde)</option>
                          <option value="critical">Crítico (Vermelho)</option>
                          <option value="warning">Aviso (Amarelo)</option>
                          <option value="info">Informativo (Azul)</option>
                        </select>
                      </div>
                    </div>

                    {/* Condition */}
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                      <span className="text-[11px] font-semibold text-slate-300 block">Condição de Disparo:</span>
                      <div className="grid grid-cols-3 gap-2">
                        <select
                          value={newRuleConditions[0].metric}
                          onChange={(e) => {
                            const updated = [...newRuleConditions];
                            updated[0].metric = e.target.value as AlertMetric;
                            setNewRuleConditions(updated);
                          }}
                          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white"
                        >
                          {METRIC_OPTIONS.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        <select
                          value={newRuleConditions[0].operator}
                          onChange={(e) => {
                            const updated = [...newRuleConditions];
                            updated[0].operator = e.target.value as AlertOperator;
                            setNewRuleConditions(updated);
                          }}
                          className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white"
                        >
                          <option value=">=">&gt;= (Maior ou igual)</option>
                          <option value=">">&gt; (Maior que)</option>
                          <option value="<=">&lt;= (Menor ou igual)</option>
                          <option value="<">&lt; (Menor que)</option>
                          <option value="==">== (Igual a)</option>
                        </select>
                        <input
                          type="number"
                          value={newRuleConditions[0].value}
                          onChange={(e) => {
                            const updated = [...newRuleConditions];
                            updated[0].value = parseFloat(e.target.value) || 0;
                            setNewRuleConditions(updated);
                          }}
                          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        onClick={() => setIsAddingRule(false)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={handleCreateNewAlertRule}
                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-xs shadow"
                      >
                        Salvar Nova Regra no Disco
                      </button>
                    </div>
                  </div>
                )}

                {/* List of rules */}
                <div className="space-y-2">
                  {alertRules.map((rule) => {
                    const isEditingThisRule = editingRuleId === rule.id;

                    if (isEditingThisRule) {
                      return (
                        <div
                          key={rule.id}
                          className="p-4 bg-slate-900 border border-cyan-500/50 rounded-xl space-y-3 animate-in fade-in shadow-lg shadow-cyan-950/30"
                        >
                          <div className="flex items-center justify-between">
                            <h6 className="font-bold text-xs text-cyan-300 flex items-center gap-1.5">
                              <Pencil className="w-3.5 h-3.5" />
                              Editar Regra: {rule.name}
                            </h6>
                            <span className="text-[10px] text-slate-400 font-mono">ID: {rule.id}</span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className="text-[11px] text-slate-400 block mb-1">Nome da Regra</label>
                              <input
                                type="text"
                                value={editRuleName}
                                onChange={(e) => setEditRuleName(e.target.value)}
                                placeholder="Nome da Regra"
                                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                              />
                            </div>
                            <div>
                              <label className="text-[11px] text-slate-400 block mb-1">Severidade</label>
                              <select
                                value={editRuleSeverity}
                                onChange={(e) => setEditRuleSeverity(e.target.value as AlertSeverity)}
                                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                              >
                                <option value="opportunity">Oportunidade (Verde)</option>
                                <option value="critical">Crítico (Vermelho)</option>
                                <option value="warning">Aviso (Amarelo)</option>
                                <option value="info">Informativo (Azul)</option>
                              </select>
                            </div>
                          </div>

                          <div>
                            <label className="text-[11px] text-slate-400 block mb-1">Descrição (opcional)</label>
                            <input
                              type="text"
                              value={editRuleDesc}
                              onChange={(e) => setEditRuleDesc(e.target.value)}
                              placeholder="Ex: Dispara quando a pressão for maior que 80%"
                              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                            />
                          </div>

                          <div className="flex items-center gap-4 py-1">
                            <div className="flex items-center gap-2">
                              <label className="text-[11px] text-slate-400">Lógica entre condições:</label>
                              <select
                                value={editRuleLogic}
                                onChange={(e) => setEditRuleLogic(e.target.value as "AND" | "OR")}
                                className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                              >
                                <option value="AND">E (AND) - Todas devem bater</option>
                                <option value="OR">OU (OR) - Qualquer uma bater</option>
                              </select>
                            </div>
                            <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={editRuleSound}
                                onChange={(e) => setEditRuleSound(e.target.checked)}
                                className="rounded bg-slate-800 border-slate-700 text-cyan-500"
                              />
                              Alerta Sonoro
                            </label>
                          </div>

                          {/* Conditions List */}
                          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-[11px] font-semibold text-slate-300">Condições de Disparo:</span>
                              <button
                                type="button"
                                onClick={handleAddConditionToEdit}
                                className="text-[10px] text-cyan-400 hover:text-cyan-300 font-bold flex items-center gap-1"
                              >
                                <Plus className="w-3 h-3" />
                                Adicionar Condição
                              </button>
                            </div>

                            {editRuleConditions.map((cond, cIdx) => (
                              <div key={cIdx} className="grid grid-cols-12 gap-2 items-center">
                                <div className="col-span-5">
                                  <select
                                    value={cond.metric}
                                    onChange={(e) => {
                                      const updated = [...editRuleConditions];
                                      updated[cIdx].metric = e.target.value as AlertMetric;
                                      setEditRuleConditions(updated);
                                    }}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white"
                                  >
                                    {METRIC_OPTIONS.map((m) => (
                                      <option key={m.value} value={m.value}>{m.label}</option>
                                    ))}
                                  </select>
                                </div>
                                <div className="col-span-3">
                                  <select
                                    value={cond.operator}
                                    onChange={(e) => {
                                      const updated = [...editRuleConditions];
                                      updated[cIdx].operator = e.target.value as AlertOperator;
                                      setEditRuleConditions(updated);
                                    }}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white"
                                  >
                                    <option value=">=">&gt;= (Maior/Igual)</option>
                                    <option value=">">&gt; (Maior)</option>
                                    <option value="<=">&lt;= (Menor/Igual)</option>
                                    <option value="<">&lt; (Menor)</option>
                                    <option value="==">== (Igual)</option>
                                  </select>
                                </div>
                                <div className="col-span-3">
                                  <input
                                    type="number"
                                    step="any"
                                    value={cond.value}
                                    onChange={(e) => {
                                      const updated = [...editRuleConditions];
                                      updated[cIdx].value = parseFloat(e.target.value) || 0;
                                      setEditRuleConditions(updated);
                                    }}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white font-mono"
                                  />
                                </div>
                                <div className="col-span-1 flex justify-center">
                                  {editRuleConditions.length > 1 && (
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveConditionFromEdit(cIdx)}
                                      className="p-1 text-slate-500 hover:text-rose-400"
                                      title="Remover condição"
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>

                          <div className="flex justify-end gap-2 pt-1">
                            <button
                              onClick={handleCancelEditRule}
                              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
                            >
                              Cancelar
                            </button>
                            <button
                              onClick={handleSaveEditRule}
                              className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white font-bold rounded-lg text-xs shadow-md shadow-cyan-950/30"
                            >
                              Salvar Alterações
                            </button>
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={rule.id}
                        className={`p-3 rounded-xl border flex items-center justify-between gap-3 transition ${
                          rule.enabled
                            ? "bg-slate-900/80 border-slate-700 text-slate-200"
                            : "bg-slate-950/40 border-slate-800 text-slate-500"
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className={`w-2 h-2 rounded-full ${rule.enabled ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
                            <span className="font-bold text-xs text-white truncate">{rule.name}</span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-slate-800 border border-slate-700 uppercase">
                              {rule.severity}
                            </span>
                          </div>
                          {rule.description && (
                            <p className="text-[11px] text-slate-400 mt-0.5 truncate">{rule.description}</p>
                          )}
                          <div className="flex items-center gap-3 text-[10px] text-slate-500 mt-1 font-mono">
                            <span>Condições: {rule.conditions.map((c) => `${c.metric} ${c.operator} ${c.value}`).join(` ${rule.logic || "AND"} `)}</span>
                            <span>Disparos: {rule.triggerCount}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={() => handleStartEditRule(rule)}
                            className="p-1.5 text-slate-400 hover:text-cyan-300 hover:bg-slate-800 rounded-lg transition"
                            title="Editar regra"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleToggleAlertRule(rule.id)}
                            className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border transition ${
                              rule.enabled
                                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25"
                                : "bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200"
                            }`}
                          >
                            {rule.enabled ? "Ativa" : "Pausada"}
                          </button>
                          <button
                            onClick={() => handleDeleteAlertRule(rule.id)}
                            className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                            title="Excluir regra"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 3: CASAS DE APOSTAS & EXCHANGE                       */}
          {/* ======================================================== */}
          {activeTab === "bookmakers" && (
            <div className="space-y-6">
              {/* Top Controls Banner */}
              <div className="p-4 bg-slate-950/70 border border-cyan-500/30 rounded-2xl space-y-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-cyan-500/10 rounded-lg text-cyan-400">
                      <Building2 className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Principais Casas de Apostas & Exchange</h4>
                      <p className="text-xs text-slate-400">
                        Ative as casas para cotações em tempo real e cálculo de Fair Odds (+EV).
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSelectAllBookmakers(true)}
                      className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-[11px] font-bold rounded-lg shadow-sm"
                    >
                      Ativar Todas (9)
                    </button>
                    <button
                      onClick={handleSelectExchangesOnly}
                      className="px-2.5 py-1 bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-[11px] font-bold rounded-lg"
                    >
                      Apenas Betfair & Pinnacle
                    </button>
                    <button
                      onClick={() => handleSelectAllBookmakers(false)}
                      className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 text-[11px] rounded-lg border border-slate-700"
                    >
                      Desativar
                    </button>
                  </div>
                </div>
              </div>

              {/* Bookmakers Cards Grid with API Keys */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {AVAILABLE_BOOKMAKERS.map((b) => {
                  const cred = bookmakerCreds[b.id] || {
                    bookmakerId: b.id,
                    name: b.name,
                    enabled: false,
                    apiKey: "",
                    connectionStatus: "unconfigured",
                  };
                  const isEnabled = (rulesConfig.enabledBookmakers || []).includes(b.id);
                  const isTesting = testingBookmakerId === b.id;
                  const isConnected = cred.connectionStatus === "connected" || (cred.apiKey && cred.apiKey.length > 4);

                  return (
                    <div
                      key={b.id}
                      className={`p-4 rounded-xl border transition flex flex-col justify-between space-y-3 ${
                        isEnabled
                          ? "bg-slate-900 border-cyan-500/40 shadow-sm"
                          : "bg-slate-950/40 border-slate-800 text-slate-500"
                      }`}
                    >
                      <div>
                        {/* Header of card */}
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className={`font-black text-sm ${b.tagColor}`}>{b.name}</span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded font-bold uppercase bg-slate-800 text-slate-300 border border-slate-700">
                              {b.type}
                            </span>
                          </div>
                          <button
                            onClick={() => handleToggleBookmaker(b.id)}
                            className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border transition ${
                              isEnabled
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                                : "bg-slate-800 text-slate-400 border-slate-700"
                            }`}
                          >
                            {isEnabled ? "Ativa" : "Inativa"}
                          </button>
                        </div>

                        {/* API Key Input */}
                        <div className="space-y-1">
                          <label className="text-[10px] text-slate-400 flex items-center justify-between">
                            <span>Chave de API / Feed:</span>
                            <span className={`font-mono text-[9px] ${isConnected ? "text-emerald-400" : "text-slate-500"}`}>
                              {isConnected ? "● Conectada" : "○ Não configurada"}
                            </span>
                          </label>
                          <input
                            type="text"
                            value={cred.apiKey || ""}
                            onChange={(e) => handleUpdateBookmakerKey(b.id, e.target.value)}
                            placeholder={`API Key ${b.shortName}...`}
                            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-cyan-300 font-mono focus:outline-none focus:border-cyan-500"
                          />
                        </div>
                      </div>

                      {/* Footer: Test button & status */}
                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
                        <button
                          onClick={() => handleTestBookmakerApi(b.id)}
                          disabled={isTesting}
                          className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg text-[11px] font-medium transition disabled:opacity-50"
                        >
                          <Activity className={`w-3 h-3 text-cyan-400 ${isTesting ? "animate-spin" : ""}`} />
                          <span>{isTesting ? "Testando..." : "Testar Ping"}</span>
                        </button>

                        {testResultMsg?.id === b.id && (
                          <span
                            className={`text-[10px] font-mono ${
                              testResultMsg.success ? "text-emerald-400 font-bold" : "text-rose-400"
                            }`}
                          >
                            {testResultMsg.msg}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 4: CRAWLER PYTHON & WEBHOOKS                         */}
          {/* ======================================================== */}
          {activeTab === "crawler" && (
            <div className="space-y-6">
              {/* Endpoints Webhooks */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
                <div className="flex items-center justify-between">
                  <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Radio className="w-3.5 h-3.5 text-emerald-400" />
                    Endpoints de Webhook Ativos ({customWebhooks.length})
                  </h5>
                  <button
                    onClick={() => setIsAddingWebhook(!isAddingWebhook)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition shadow-sm"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Novo Webhook
                  </button>
                </div>

                {isAddingWebhook && (
                  <div className="p-4 bg-slate-900 border border-emerald-500/40 rounded-xl space-y-3 animate-in fade-in">
                    <h6 className="font-bold text-xs text-emerald-300">Cadastrar Novo Webhook de Ingestão</h6>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] text-slate-400 block mb-1">Nome do Webhook</label>
                        <input
                          type="text"
                          value={newWebhookName}
                          onChange={(e) => setNewWebhookName(e.target.value)}
                          placeholder="Ex: Playwright Flashscore Live"
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-400 block mb-1">Slug da URL (/api/crawler/webhook/:slug)</label>
                        <input
                          type="text"
                          value={newWebhookSlug}
                          onChange={(e) => setNewWebhookSlug(e.target.value)}
                          placeholder="Ex: flashscore-live"
                          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        onClick={() => setIsAddingWebhook(false)}
                        className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-xs"
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={handleCreateWebhook}
                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-xs shadow"
                      >
                        Criar Endpoint no Servidor
                      </button>
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  {customWebhooks.map((wh) => (
                    <div
                      key={wh.id}
                      className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${wh.active ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
                          <span className="font-bold text-xs text-white">{wh.name}</span>
                          <code className="text-[10px] text-emerald-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 font-mono">
                            /api/crawler/webhook/{wh.slug}
                          </code>
                        </div>
                        <div className="flex items-center gap-3 text-[10px] text-slate-400 mt-1 font-mono">
                          <span>Status: {wh.lastStatus || "ok"}</span>
                          <span>Chamadas: {wh.totalCalls || 0}</span>
                          {wh.lastCallTimestamp && (
                            <span>Último pacote: {new Date(wh.lastCallTimestamp).toLocaleTimeString()}</span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleToggleWebhook(wh.id)}
                          className={`px-2 py-1 rounded text-[10px] font-bold border transition ${
                            wh.active
                              ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
                              : "bg-slate-800 border-slate-700 text-slate-400"
                          }`}
                        >
                          {wh.active ? "Ativo" : "Pausado"}
                        </button>
                        <button
                          onClick={() => handleDeleteWebhook(wh.id)}
                          className="p-1 text-slate-500 hover:text-rose-400 rounded transition"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Download Python Scripts */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h5 className="font-bold text-xs text-slate-200">Script Python Unificado Pronto para Execução</h5>
                  <p className="text-xs text-slate-400">Baixe o motor oficial unificado <b className="text-cyan-400 font-mono">bridge_web.py</b> pré-configurado para modo Standalone Local.</p>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href="/api/crawler/download-bridge"
                    download="bridge_web.py"
                    className="flex items-center gap-1.5 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-bold shadow-md shadow-cyan-900/30 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Baixar bridge_web.py (Motor Unificado Standalone)
                  </a>
                </div>
              </div>

              {/* Tabela de TTLs do Cacheamento Adaptativo por TIER */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">
                      <Gauge className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Cacheamento por TIER (Redução de Requisições)</h4>
                      <p className="text-xs text-slate-400">
                        Cadência adaptativa inteligente que bloqueia requisições redundantes de acordo com a urgência da partida.
                      </p>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">
                    -75% a -90% Requisições Redundantes
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 pt-1">
                  <div className="p-2.5 bg-slate-900/90 border border-amber-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block">Tier 0 (Sinais)</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">12s TTL</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Alta frequência</span>
                  </div>
                  <div className="p-2.5 bg-slate-900/90 border border-cyan-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block">Tier 0.5 (Premium)</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">25s TTL</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Grandes ligas</span>
                  </div>
                  <div className="p-2.5 bg-slate-900/90 border border-emerald-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block">Tier 1/2 (20-83')</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">35s-45s</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Janela ativa</span>
                  </div>
                  <div className="p-2.5 bg-slate-900/90 border border-blue-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block">Tier 3 (Rodízio)</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">80s TTL</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Ligas menores</span>
                  </div>
                  <div className="p-2.5 bg-slate-900/90 border border-purple-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider block">HT (Intervalo)</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">150s TTL</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Economia máxima</span>
                  </div>
                  <div className="p-2.5 bg-slate-900/90 border border-rose-500/30 rounded-xl text-center">
                    <span className="text-[10px] font-bold text-rose-400 uppercase tracking-wider block">No Stats</span>
                    <span className="text-sm font-black text-white font-mono mt-0.5 block">10 min</span>
                    <span className="text-[9px] text-slate-400 block mt-0.5">Backoff auto</span>
                  </div>
                </div>
              </div>

              {/* Catálogo de Jogos & Descoberta Assíncrona (live_daemon / bridge_web) */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-cyan-500/10 rounded-lg text-cyan-400">
                      <Compass className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Catálogo Persistente & Descoberta em Background</h4>
                      <p className="text-xs text-slate-400">
                        Otimizações de descoberta de jogos ao vivo desacopladas do ciclo principal de varredura estatística.
                      </p>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/50">
                    bridge_web.py + Catalog Engine
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                  {/* Intervalo de Descoberta */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Intervalo de Descoberta (s):</span>
                      <span className="font-mono text-cyan-400">{rulesConfig.crawlerConfig?.discoveryIntervalSeconds || 180}s</span>
                    </label>
                    <input
                      type="range"
                      min={60}
                      max={600}
                      step={30}
                      value={rulesConfig.crawlerConfig?.discoveryIntervalSeconds || 180}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            discoveryIntervalSeconds: val,
                          },
                        });
                      }}
                      className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Varre a grade completa do Flashscore para descobrir novos jogos.</p>
                  </div>

                  {/* Faxina do Catálogo (Prune Stale) */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Faxina do Catálogo (min):</span>
                      <span className="font-mono text-cyan-400">{rulesConfig.crawlerConfig?.autoPruneMinutes || 30} min</span>
                    </label>
                    <input
                      type="range"
                      min={10}
                      max={90}
                      step={5}
                      value={rulesConfig.crawlerConfig?.autoPruneMinutes || 30}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            autoPruneMinutes: val,
                          },
                        });
                      }}
                      className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Remove partidas não vistas do catálogo para economizar memória.</p>
                  </div>

                  {/* Backoff de Jogos sem Stats */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Backoff Sem Stats (min):</span>
                      <span className="font-mono text-cyan-400">{rulesConfig.crawlerConfig?.noStatsBackoffMinutes || 10} min</span>
                    </label>
                    <input
                      type="range"
                      min={3}
                      max={30}
                      step={1}
                      value={rulesConfig.crawlerConfig?.noStatsBackoffMinutes || 10}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            noStatsBackoffMinutes: val,
                          },
                        });
                      }}
                      className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Cooldown para partidas sem suporte a xG/chutes detalhados.</p>
                  </div>
                </div>

                {/* Toggles de Bloqueio de Recursos e Background Discovery */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <h6 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                        <Zap className="w-3.5 h-3.5 text-amber-400" />
                        Bloqueio de Recursos Pesados (Route Filter)
                      </h6>
                      <p className="text-[10px] text-slate-400">Aborta o carregamento de imagens, fontes e analytics no Playwright.</p>
                    </div>
                    <button
                      onClick={() => {
                        const curr = rulesConfig.crawlerConfig?.routeResourceBlock ?? true;
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            routeResourceBlock: !curr,
                          },
                        });
                      }}
                      className={`px-3 py-1 rounded-lg text-xs font-bold border transition ${
                        (rulesConfig.crawlerConfig?.routeResourceBlock ?? true)
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                          : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}
                    >
                      {(rulesConfig.crawlerConfig?.routeResourceBlock ?? true) ? "Ativado" : "Desativado"}
                    </button>
                  </div>

                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl flex items-center justify-between">
                    <div>
                      <h6 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                        <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                        Descoberta em Thread Paralela Desacoplada
                      </h6>
                      <p className="text-[10px] text-slate-400">Não trava o loop de atualização ao vivo durante a descoberta de jogos.</p>
                    </div>
                    <button
                      onClick={() => {
                        const curr = rulesConfig.crawlerConfig?.enableBackgroundDiscovery ?? true;
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            enableBackgroundDiscovery: !curr,
                          },
                        });
                      }}
                      className={`px-3 py-1 rounded-lg text-xs font-bold border transition ${
                        (rulesConfig.crawlerConfig?.enableBackgroundDiscovery ?? true)
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                          : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}
                    >
                      {(rulesConfig.crawlerConfig?.enableBackgroundDiscovery ?? true) ? "Ativado" : "Desativado"}
                    </button>
                  </div>
                </div>

                {/* Faxina Manual do Catálogo e Jogos Encerrados */}
                <div className="p-3.5 bg-slate-900/90 border border-cyan-500/30 rounded-xl flex items-center justify-between flex-wrap gap-3 mt-2">
                  <div className="max-w-xl">
                    <h6 className="text-xs font-bold text-white flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                      Faxina Geral de Catálogo & Partidas Encerradas
                    </h6>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Remove todas as partidas encerradas/FT da memória e reseta as supressões manuais para uma nova rodada limpa. <i>(O intervalo de descoberta de rotina preserva o catálogo e as exclusões manuais sem resetá-las).</i>
                    </p>
                  </div>
                  <button
                    onClick={handleExecuteFaxina}
                    disabled={isExecutingFaxina}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-bold shadow-md shadow-cyan-950/40 transition disabled:opacity-50"
                  >
                    {isExecutingFaxina ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    <span>{isExecutingFaxina ? "Executando Faxina..." : "Executar Faxina do Catálogo"}</span>
                  </button>
                </div>
                {faxinaStatus && (
                  <div className="p-2.5 bg-cyan-950/80 border border-cyan-500/50 rounded-xl text-xs text-cyan-200 font-medium animate-in fade-in">
                    {faxinaStatus}
                  </div>
                )}
              </div>

              {/* Watchlist por Tiers de Prioridade (Gestão de Capacidade & Velocidade) */}
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">
                      <ListOrdered className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-sm">Watchlist Priorizada por Tiers de Jogo</h4>
                      <p className="text-xs text-slate-400">
                        Distribuição inteligente dos slots de escaneamento para focar em oportunidades de alto valor com máxima frequência.
                      </p>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">
                    Tier 0 → 0.5 → 1/2 → 3
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                  {/* Tamanho Máximo da Watchlist */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Capacidade Watchlist:</span>
                      <span className="font-mono text-emerald-400">{rulesConfig.crawlerConfig?.maxWatchlistSize || 15} jogos</span>
                    </label>
                    <input
                      type="range"
                      min={5}
                      max={40}
                      step={1}
                      value={rulesConfig.crawlerConfig?.maxWatchlistSize || 15}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            maxWatchlistSize: val,
                          },
                        });
                      }}
                      className="w-full accent-emerald-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Total de jogos prioritários escaneados a cada ciclo.</p>
                  </div>

                  {/* Slots Reservados Tier 3 */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Slots Rodízio (Tier 3):</span>
                      <span className="font-mono text-emerald-400">{rulesConfig.crawlerConfig?.tier3ReservedSlots || 2} slots</span>
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={10}
                      step={1}
                      value={rulesConfig.crawlerConfig?.tier3ReservedSlots || 2}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            tier3ReservedSlots: val,
                          },
                        });
                      }}
                      className="w-full accent-emerald-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Garante que ligas alternativas passem por varredura contínua.</p>
                  </div>

                  {/* Janela de Minutos (Entrada Watchlist) */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Janela Watchlist:</span>
                      <span className="font-mono text-emerald-400">
                        {rulesConfig.crawlerConfig?.minEntryMinute || 20}' a {rulesConfig.crawlerConfig?.maxEntryMinute || 83}'
                      </span>
                    </label>
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="number"
                        min={0}
                        max={45}
                        value={rulesConfig.crawlerConfig?.minEntryMinute || 20}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 0;
                          setRulesConfig({
                            ...rulesConfig,
                            crawlerConfig: {
                              ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                              minEntryMinute: val,
                            },
                          });
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white font-mono text-center"
                      />
                      <span className="text-slate-500 text-xs">até</span>
                      <input
                        type="number"
                        min={45}
                        max={95}
                        value={rulesConfig.crawlerConfig?.maxEntryMinute || 83}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 90;
                          setRulesConfig({
                            ...rulesConfig,
                            crawlerConfig: {
                              ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                              maxEntryMinute: val,
                            },
                          });
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white font-mono text-center"
                      />
                    </div>
                    <p className="text-[10px] text-slate-500">Minuto inicial e final para entrada de partidas na lista ativa.</p>
                  </div>

                  {/* Anti-Spam Cooldown */}
                  <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                      <span>Anti-Spam Sinais (min):</span>
                      <span className="font-mono text-emerald-400">{rulesConfig.crawlerConfig?.antiSpamCooldownMinutes || 5} min</span>
                    </label>
                    <input
                      type="range"
                      min={1}
                      max={15}
                      step={1}
                      value={rulesConfig.crawlerConfig?.antiSpamCooldownMinutes || 5}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                            antiSpamCooldownMinutes: val,
                          },
                        });
                      }}
                      className="w-full accent-emerald-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                    />
                    <p className="text-[10px] text-slate-500">Mantém o jogo fixo no Tier 0 para monitorar evolução pós-sinal.</p>
                  </div>
                </div>

                {/* Habilitação dos Níveis de Tiers */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                  {[
                    { key: "enableTier0Signals", label: "Tier 0 (Sinais & Posições)", desc: "Prioridade Absoluta" },
                    { key: "enableTier05PremiumLeagues", label: "Tier 0.5 (Ligas Premium A/B/C)", desc: "Grandes Campeonatos" },
                    { key: "enableTier12Window", label: "Tier 1 & 2 (Janela 20-83' & Stats)", desc: "Oportunidades em Curso" },
                    { key: "enableTier3Rotation", label: "Tier 3 (Rodízio de Ligas)", desc: "Exploração FIFO" },
                  ].map((tf) => {
                    const active = (rulesConfig.crawlerConfig?.tierFilter as any)?.[tf.key] ?? true;
                    return (
                      <button
                        key={tf.key}
                        onClick={() => {
                          const currentTiers = rulesConfig.crawlerConfig?.tierFilter || {
                            enableTier0Signals: true,
                            enableTier05PremiumLeagues: true,
                            enableTier12Window: true,
                            enableTier3Rotation: true,
                          };
                          setRulesConfig({
                            ...rulesConfig,
                            crawlerConfig: {
                              ...(rulesConfig.crawlerConfig || (DEFAULT_MODAL_CONFIG.crawlerConfig as any)),
                              tierFilter: {
                                ...currentTiers,
                                [tf.key]: !active,
                              },
                            },
                          });
                        }}
                        className={`p-2.5 rounded-xl text-left border transition ${
                          active
                            ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
                            : "bg-slate-900/60 border-slate-800 text-slate-500"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[11px] font-bold">{tf.label}</span>
                          {active ? <CheckSquare className="w-3.5 h-3.5 text-emerald-400" /> : <Square className="w-3.5 h-3.5 text-slate-600" />}
                        </div>
                        <span className="text-[10px] text-slate-400 block">{tf.desc}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* TAB 5: BACKUP & PERFIL                                   */}
          {/* ======================================================== */}
          {activeTab === "backup_profile" && (
            <div className="space-y-6">
              {/* Local File Path Banner */}
              <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <FileJson className="w-4 h-4 text-emerald-400" />
                    Arquivo de Persistência em Disco:
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 bg-slate-800 text-slate-300 rounded border border-slate-700">
                    JSON UTF-8
                  </span>
                </div>
                <div className="bg-slate-900 px-3 py-2 rounded-lg font-mono text-xs text-emerald-300 border border-slate-800/80 break-all select-all">
                  {filePath}
                </div>
              </div>

              {/* Perfil do Administrador Local */}
              <div className="p-4 bg-slate-950/50 border border-slate-800/80 rounded-xl space-y-3">
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-cyan-400" />
                  Perfil do Administrador Local
                </h4>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Nome de Exibição</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={displayNameInput}
                      onChange={(e) => setDisplayNameInput(e.target.value)}
                      placeholder="Ex: Trader Local Pro"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500"
                    />
                    <button
                      onClick={() => handleSaveToDisk(undefined, "Nome de exibição salvo no disco!")}
                      className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg text-xs font-semibold transition"
                    >
                      Salvar
                    </button>
                  </div>
                </div>
              </div>

              {/* Backup / Export / Import */}
              <div className="p-4 bg-slate-950/50 border border-slate-800/80 rounded-xl space-y-3">
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <FolderArchive className="w-3.5 h-3.5 text-amber-400" />
                  Backup Manual & Transferência
                </h4>
                <p className="text-xs text-slate-400">
                  Exporte o arquivo de configuração para salvar em pen-drive ou importar em outra máquina.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    onClick={handleExportDownload}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold shadow-md shadow-emerald-900/30 transition active:scale-95"
                  >
                    <Download className="w-4 h-4" />
                    Baixar Backup (.JSON)
                  </button>

                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition active:scale-95"
                  >
                    <Upload className="w-4 h-4 text-cyan-400" />
                    Importar Backup JSON
                  </button>
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".json,application/json"
                    className="hidden"
                  />

                  <button
                    onClick={handleResetToDefaults}
                    className="flex items-center gap-1.5 px-3.5 py-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 rounded-xl text-xs font-semibold transition"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Restaurar Padrão de Fábrica
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800 flex items-center justify-between bg-slate-950/70 flex-wrap gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
            <span>Ratio Ativo: <b className="text-amber-400">{rulesConfig.chancesPerGoalRatio.toFixed(1)}:1</b></span>
            <span>•</span>
            <span>Casas: <b className="text-cyan-400">{rulesConfig.enabledBookmakers?.length ?? 8}/9</b></span>
            <span>•</span>
            <span>Regras: <b className="text-emerald-400">{alertRules.length}</b></span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleSaveToDisk()}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition shadow-sm"
            >
              Gravar Alterações
            </button>
            <button
              onClick={onClose}
              className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold border border-slate-700 transition"
            >
              Fechar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
