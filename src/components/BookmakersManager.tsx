import React, { useState, useEffect } from "react";
import { safeFetchJson } from "../api";
import {
  BookmakerId,
  BookmakerApiCredential,
  BookmakerApiMap,
  DEFAULT_BOOKMAKER_CREDENTIALS,
  AVAILABLE_BOOKMAKERS,
  OperationalRulesConfig,
} from "../types";
import {
  Key,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Copy,
  Check,
  RefreshCw,
  Save,
  Zap,
  Building2,
  Server,
  Activity,
  Sliders,
  ExternalLink,
  Lock,
  Sparkles,
  Info,
  CheckSquare,
  XSquare,
} from "lucide-react";

interface BookmakersManagerProps {
  rulesConfig?: OperationalRulesConfig | null;
  onUpdateRulesConfig?: (config: OperationalRulesConfig) => Promise<void>;
}

// Meta information for primary bookmakers
const PRIMARY_BOOKMAKERS: BookmakerId[] = ["bet365", "betano", "betfair", "pinnacle", "esportivabet"];
const SECONDARY_BOOKMAKERS: BookmakerId[] = ["sportingbet", "kto", "superbet", "1xbet"];

const BOOKMAKER_HIGHLIGHTS: Record<
  BookmakerId,
  {
    tagline: string;
    marketSpecialty: string;
    recommendedFor: string;
    accentColor: string;
    borderColor: string;
    bgGradient: string;
    officialDocsUrl: string;
  }
> = {
  bet365: {
    tagline: "Líder Global em Cotações Ao Vivo & Linhas Asiáticas",
    marketSpecialty: "Over/Under Gols Limite, Cantos Asiáticos e Race to Corners",
    recommendedFor: "Estratégia Diagnóstico, Funil de Cantos e Pressão Vendável",
    accentColor: "text-emerald-400",
    borderColor: "border-emerald-500/40",
    bgGradient: "from-emerald-950/30 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.bet365.com",
  },
  betano: {
    tagline: "SuperOdds & Mercados de Estatísticas Individuais",
    marketSpecialty: "Finalizações no Alvo, Ambas Marcam (BTTS) e Cartões",
    recommendedFor: "Jogo Quente (Cartões), Risco de Expulsão e BTTS",
    accentColor: "text-orange-400",
    borderColor: "border-orange-500/40",
    bgGradient: "from-orange-950/30 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.betano.com",
  },
  betfair: {
    tagline: "Maior Bolsa Esportiva do Mundo (Exchange P2P)",
    marketSpecialty: "Back/Lay em Tempo Real, Cashout Automatizado e Liquidez",
    recommendedFor: "Cashout Proativo, Virada Improvável (Lay Zebra) e Back Dominante",
    accentColor: "text-amber-400",
    borderColor: "border-amber-500/40",
    bgGradient: "from-amber-950/30 via-slate-900 to-slate-950",
    officialDocsUrl: "https://developer.betfair.com",
  },
  pinnacle: {
    tagline: "Casa Sharp com Menor Margem (2.5%) e Maiores Limites",
    marketSpecialty: "Mercados Principais 1X2, Over/Under Fechamento e Handicap Sharp",
    recommendedFor: "Arbitragem, Comparação de Odd Justa (+EV) e Linhas Eficientes",
    accentColor: "text-rose-400",
    borderColor: "border-rose-500/40",
    bgGradient: "from-rose-950/30 via-slate-900 to-slate-950",
    officialDocsUrl: "https://www.pinnacle.com/en/api",
  },
  esportivabet: {
    tagline: "Plataforma Nacional com Odds Turbinadas & Saques Rápidos PIX",
    marketSpecialty: "Over Gols Limite, Cantos Asiáticos, Ambas Marcam e Mercados ao Vivo",
    recommendedFor: "Operações rápidas no futebol brasileiro e Diagnóstico",
    accentColor: "text-emerald-400",
    borderColor: "border-emerald-500/40",
    bgGradient: "from-emerald-950/30 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.esportivabet.com",
  },
  sportingbet: {
    tagline: "Sportsbook Tradicional com Mercados de Gols",
    marketSpecialty: "Gols Totais e Mercados Rápidos de 10 minutos",
    recommendedFor: "Gols em Atraso e Linhas Tradicionais",
    accentColor: "text-blue-400",
    borderColor: "border-blue-500/30",
    bgGradient: "from-blue-950/20 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.sportingbet.com",
  },
  kto: {
    tagline: "Mercados Dinâmicos e Pagamento Antecipado",
    marketSpecialty: "Gols e Mercados Rápidos",
    recommendedFor: "Operações de valor no mercado brasileiro",
    accentColor: "text-rose-400",
    borderColor: "border-rose-500/30",
    bgGradient: "from-rose-950/20 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.kto.com",
  },
  superbet: {
    tagline: "SuperPlacar e Cotações Turbinadas",
    marketSpecialty: "Combos de Estatísticas e Over Gols",
    recommendedFor: "Cruzamento com Gatilhos de Surto 5m",
    accentColor: "text-red-400",
    borderColor: "border-red-500/30",
    bgGradient: "from-red-950/20 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.superbet.com",
  },
  '1xbet': {
    tagline: "Maior Catálogo de Ligas e Mercados Alternativos",
    marketSpecialty: "Cantos, Faltas, Chutes e Mercados Alternativos",
    recommendedFor: "Ligas Menores e Cobertura Global",
    accentColor: "text-cyan-400",
    borderColor: "border-cyan-500/30",
    bgGradient: "from-cyan-950/20 via-slate-900 to-slate-950",
    officialDocsUrl: "https://api.1xbet.com",
  },
};

export function BookmakersManager({
  rulesConfig,
  onUpdateRulesConfig,
}: BookmakersManagerProps) {
  const [credentials, setCredentials] = useState<BookmakerApiMap>(() => {
    return rulesConfig?.bookmakerCredentials || { ...DEFAULT_BOOKMAKER_CREDENTIALS };
  });

  const [visibleKeys, setVisibleKeys] = useState<Record<BookmakerId, boolean>>({
    bet365: false,
    betano: false,
    betfair: false,
    pinnacle: false,
    esportivabet: false,
    sportingbet: false,
    kto: false,
    superbet: false,
    '1xbet': false,
  });

  const [copiedId, setCopiedId] = useState<BookmakerId | null>(null);
  const [testingId, setTestingId] = useState<BookmakerId | null>(null);
  const [testResults, setTestResults] = useState<
    Record<
      BookmakerId,
      { success: boolean; latencyMs: number; message: string; timestamp: string } | null
    >
  >({
    bet365: null,
    betano: null,
    betfair: null,
    pinnacle: null,
    esportivabet: null,
    sportingbet: null,
    kto: null,
    superbet: null,
    '1xbet': null,
  });

  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState<string | null>(null);
  const [showSecondaryList, setShowSecondaryList] = useState(false);
  const [activeTab, setActiveTab] = useState<"primary" | "all">("primary");

  // Load config from backend on mount
  useEffect(() => {
    async function loadBackendBookmakers() {
      const data = await safeFetchJson<{ bookmakers: BookmakerApiMap }>("/api/bookmakers/config");
      if (data?.bookmakers) {
        setCredentials(data.bookmakers);
      }
    }
    loadBackendBookmakers();
  }, []);

  // Sync if parent rulesConfig changes
  useEffect(() => {
    if (rulesConfig?.bookmakerCredentials) {
      setCredentials((prev) => ({
        ...prev,
        ...rulesConfig.bookmakerCredentials,
      }));
    }
  }, [rulesConfig?.bookmakerCredentials]);

  const toggleVisibleKey = (id: BookmakerId) => {
    setVisibleKeys((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleCopyKey = (id: BookmakerId, keyText: string) => {
    if (!keyText) return;
    navigator.clipboard.writeText(keyText);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleToggleEnable = (id: BookmakerId) => {
    setCredentials((prev) => {
      const cur = prev[id] || {
        bookmakerId: id,
        name: id.toUpperCase(),
        enabled: false,
        apiKey: "",
      };
      const updated = {
        ...prev,
        [id]: {
          ...cur,
          enabled: !cur.enabled,
        },
      };

      // Propagate immediately to parent state so alerts update in real-time
      if (onUpdateRulesConfig && rulesConfig) {
        const enabledBookmakerIds = (Object.keys(updated) as BookmakerId[]).filter(
          (k) => updated[k]?.enabled
        );
        onUpdateRulesConfig({
          ...rulesConfig,
          enabledBookmakers: enabledBookmakerIds,
          bookmakerCredentials: updated,
        }).catch((err) => console.error("Erro ao sincronizar regras:", err));
      }

      return updated;
    });
  };

  const handleKeyChange = (id: BookmakerId, value: string) => {
    setCredentials((prev) => {
      const cur = prev[id] || {
        bookmakerId: id,
        name: id.toUpperCase(),
        enabled: true,
        apiKey: "",
      };
      return {
        ...prev,
        [id]: {
          ...cur,
          apiKey: value,
          connectionStatus: value.trim() ? "connected" : "unconfigured",
        },
      };
    });
  };

  const handleSecretChange = (id: BookmakerId, value: string) => {
    setCredentials((prev) => {
      const cur = prev[id];
      if (!cur) return prev;
      return {
        ...prev,
        [id]: {
          ...cur,
          apiSecret: value,
        },
      };
    });
  };

  const handleEnvironmentToggle = (id: BookmakerId) => {
    setCredentials((prev) => {
      const cur = prev[id];
      if (!cur) return prev;
      const nextEnv = cur.environment === "production" ? "sandbox" : "production";
      return {
        ...prev,
        [id]: {
          ...cur,
          environment: nextEnv,
        },
      };
    });
  };

  // Test single bookmaker connection
  const handleTestConnection = async (id: BookmakerId) => {
    setTestingId(id);
    try {
      const cred = credentials[id];
      const res = await fetch(`/api/bookmakers/${id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          apiKey: cred.apiKey,
          enabled: cred.enabled,
          environment: cred.environment,
          apiSecret: cred.apiSecret,
        }),
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setTestResults((prev) => ({
          ...prev,
          [id]: {
            success: true,
            latencyMs: data.latencyMs,
            message: data.message || "Conexão validada com sucesso!",
            timestamp: new Date().toLocaleTimeString(),
          },
        }));

        setCredentials((prev) => ({
          ...prev,
          [id]: {
            ...prev[id],
            connectionStatus: "connected",
            latencyMs: data.latencyMs,
            lastTested: new Date().toISOString(),
          },
        }));
      } else {
        setTestResults((prev) => ({
          ...prev,
          [id]: {
            success: false,
            latencyMs: 0,
            message: data.message || data.error || "Falha na conexão com a API",
            timestamp: new Date().toLocaleTimeString(),
          },
        }));
      }
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [id]: {
          success: false,
          latencyMs: 0,
          message: err.message || "Erro de rede ao conectar",
          timestamp: new Date().toLocaleTimeString(),
        },
      }));
    } finally {
      setTestingId(null);
    }
  };

  // Test all primary bookmakers
  const handleTestAllPrimary = async () => {
    for (const bId of PRIMARY_BOOKMAKERS) {
      await handleTestConnection(bId);
    }
  };

  // Save all credentials to backend
  const handleSaveToBackend = async () => {
    setIsSaving(true);
    setSaveSuccessMessage(null);
    try {
      // 1. Save to dedicated bookmakers endpoint
      const res = await fetch("/api/bookmakers/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });

      if (!res.ok) {
        throw new Error("Erro na resposta do servidor.");
      }

      // 2. Also update parent rulesConfig so the entire app is in sync
      const enabledBookmakerIds = (Object.keys(credentials) as BookmakerId[]).filter(
        (id) => credentials[id].enabled
      );

      if (onUpdateRulesConfig && rulesConfig) {
        await onUpdateRulesConfig({
          ...rulesConfig,
          enabledBookmakers: enabledBookmakerIds,
          bookmakerCredentials: credentials,
        });
      }

      setSaveSuccessMessage("Todas as preferências e chaves de API foram salvas no backend com sucesso!");
      setTimeout(() => setSaveSuccessMessage(null), 5000);
    } catch (err) {
      console.error("Erro ao salvar credenciais:", err);
      alert("Houve um erro ao salvar as preferências no servidor.");
    } finally {
      setIsSaving(false);
    }
  };

  // Enable all 4 primary bookmakers (Bet365, Betano, Betfair, Pinnacle)
  const handleEnableAllPrimary = () => {
    setCredentials((prev) => {
      const next = { ...prev };
      for (const id of PRIMARY_BOOKMAKERS) {
        if (next[id]) {
          next[id] = { ...next[id], enabled: true };
        }
      }
      if (onUpdateRulesConfig && rulesConfig) {
        const enabledBookmakerIds = (Object.keys(next) as BookmakerId[]).filter(
          (k) => next[k]?.enabled
        );
        onUpdateRulesConfig({
          ...rulesConfig,
          enabledBookmakers: enabledBookmakerIds,
          bookmakerCredentials: next,
        }).catch((err) => console.error("Erro ao sincronizar regras:", err));
      }
      return next;
    });
  };

  // Fill in demo keys for testing
  const handleFillDemoKeys = () => {
    setCredentials((prev) => {
      const next = {
        ...prev,
        ...DEFAULT_BOOKMAKER_CREDENTIALS,
      };
      if (onUpdateRulesConfig && rulesConfig) {
        const enabledBookmakerIds = (Object.keys(next) as BookmakerId[]).filter(
          (k) => next[k]?.enabled
        );
        onUpdateRulesConfig({
          ...rulesConfig,
          enabledBookmakers: enabledBookmakerIds,
          bookmakerCredentials: next,
        }).catch((err) => console.error("Erro ao sincronizar regras:", err));
      }
      return next;
    });
  };

  const activeCount = (Object.values(credentials) as BookmakerApiCredential[]).filter((c) => c?.enabled).length;
  const configuredCount = (Object.values(credentials) as BookmakerApiCredential[]).filter((c) => c?.apiKey && c.apiKey.trim().length > 3).length;

  return (
    <div className="space-y-6">
      {/* Top Banner & Overview Card */}
      <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-amber-500/10 via-emerald-500/5 to-transparent rounded-full blur-3xl -z-0 pointer-events-none" />

        <div className="relative z-10 space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/40">
                  <Building2 className="w-6 h-6" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                    Módulo de Casas de Apostas & Chaves de API
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                      Odds Ao Vivo & +EV
                    </span>
                  </h2>
                  <p className="text-xs text-slate-400">
                    Ative ou desative as principais casas (Bet365, Betano, Betfair, Pinnacle), associe suas API Keys e salve suas preferências diretamente no servidor.
                  </p>
                </div>
              </div>
            </div>

            {/* Top Action Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleFillDemoKeys}
                className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold border border-slate-700 transition flex items-center gap-1.5"
                title="Preencher chaves de demonstração para testes rápidos"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                Chaves de Demonstração
              </button>

              <button
                type="button"
                onClick={handleTestAllPrimary}
                disabled={Boolean(testingId)}
                className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold border border-slate-700 transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${testingId ? "animate-spin" : ""}`} />
                Testar Conexões
              </button>

              <button
                type="button"
                onClick={handleSaveToBackend}
                disabled={isSaving}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-950/50 transition flex items-center gap-1.5 disabled:opacity-50"
              >
                {isSaving ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                Salvar Preferências no Backend
              </button>
            </div>
          </div>

          {/* Success Feedback Alert */}
          {saveSuccessMessage && (
            <div className="p-3 rounded-xl bg-emerald-950/70 border border-emerald-500/50 text-emerald-300 text-xs font-medium flex items-center justify-between animate-in fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{saveSuccessMessage}</span>
              </div>
              <button
                onClick={() => setSaveSuccessMessage(null)}
                className="text-emerald-400 hover:text-white text-[11px]"
              >
                Fechar
              </button>
            </div>
          )}

          {/* Summary Metric Counters */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Casas Ativas</span>
                <span className="text-base font-extrabold text-white font-mono">{activeCount} / 8</span>
              </div>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center">
                <CheckSquare className="w-4 h-4" />
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block">APIs Configuradas</span>
                <span className="text-base font-extrabold text-amber-400 font-mono">{configuredCount} / 8</span>
              </div>
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center">
                <Key className="w-4 h-4" />
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Latência Média</span>
                <span className="text-base font-extrabold text-cyan-400 font-mono">~35ms (Fast)</span>
              </div>
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 flex items-center justify-center">
                <Activity className="w-4 h-4" />
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Comparador +EV</span>
                <span className="text-base font-extrabold text-emerald-400 font-mono">Habilitado</span>
              </div>
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center">
                <Zap className="w-4 h-4" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Section Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900/90 p-3 rounded-xl border border-slate-800">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("primary")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              activeTab === "primary"
                ? "bg-amber-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Principais Casas ({PRIMARY_BOOKMAKERS.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              activeTab === "all"
                ? "bg-slate-800 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Todas as Casas ({AVAILABLE_BOOKMAKERS.length})
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <button
            type="button"
            onClick={handleEnableAllPrimary}
            className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition flex items-center gap-1 font-medium"
          >
            <CheckSquare className="w-3.5 h-3.5 text-emerald-400" />
            Ativar Principais (Bet365, Betano, Betfair, Pinnacle)
          </button>
        </div>
      </div>

      {/* PRIMARY BOOKMAKERS GRID (Bet365, Betano, Betfair, Pinnacle) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-amber-400" />
            <h3 className="text-sm font-black uppercase tracking-wider text-slate-200">
              Principais Casas de Apostas & Exchange
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Cotações ao vivo integradas ao motor Código 3:1 e Dicas de Trade
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {PRIMARY_BOOKMAKERS.map((bId) => {
            const bkInfo = AVAILABLE_BOOKMAKERS.find((b) => b.id === bId)!;
            const cred = credentials[bId] || {
              bookmakerId: bId,
              name: bkInfo.name,
              enabled: true,
              apiKey: "",
            };
            const meta = BOOKMAKER_HIGHLIGHTS[bId];
            const testRes = testResults[bId];
            const isTesting = testingId === bId;
            const isKeyVisible = visibleKeys[bId];
            const hasApiKey = Boolean(cred.apiKey && cred.apiKey.trim().length > 3);

            return (
              <div
                key={bId}
                className={`rounded-2xl border bg-gradient-to-br ${meta.bgGradient} p-5 shadow-xl transition-all relative space-y-4 ${
                  cred.enabled ? meta.borderColor : "border-slate-800 opacity-80"
                }`}
              >
                {/* Header of the Bookmaker Card */}
                <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 pb-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-3 rounded-xl ${bkInfo.badgeBg} border text-lg font-black shrink-0`}>
                      {bkInfo.shortName}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-base font-extrabold text-white">{bkInfo.name}</h4>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${
                          bkInfo.type === 'exchange'
                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                            : bkInfo.type === 'sharp'
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                            : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        }`}>
                          {bkInfo.type === 'exchange' ? 'BOLSA / EXCHANGE' : bkInfo.type === 'sharp' ? 'SHARP BOOKMAKER' : 'SPORTSBOOK'}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          Margem ~{bkInfo.marginPct}%
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{meta.tagline}</p>
                    </div>
                  </div>

                  {/* Toggle Button */}
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleToggleEnable(bId)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                        cred.enabled ? "bg-emerald-600" : "bg-slate-700"
                      }`}
                      title={cred.enabled ? "Desativar casa" : "Ativar casa"}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          cred.enabled ? "translate-x-6" : "translate-x-1"
                        }`}
                      />
                    </button>
                    <span className={`text-[10px] font-bold ${cred.enabled ? "text-emerald-400" : "text-slate-500"}`}>
                      {cred.enabled ? "ATIVADA" : "DESATIVADA"}
                    </span>
                  </div>
                </div>

                {/* API Key Input Section */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Key className="w-3.5 h-3.5 text-amber-400" />
                      Chave de API (API Key / Access Token):
                    </label>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                        hasApiKey
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      }`}>
                        {hasApiKey ? "Chave Presente" : "Chave Não Informada"}
                      </span>
                    </div>
                  </div>

                  <div className="relative flex items-center">
                    <input
                      type={isKeyVisible ? "text" : "password"}
                      value={cred.apiKey || ""}
                      onChange={(e) => handleKeyChange(bId, e.target.value)}
                      placeholder={`Ex: ${bId}_api_key_xxxxxxxx`}
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-amber-500 pr-24 placeholder-slate-600"
                    />

                    <div className="absolute right-2 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => toggleVisibleKey(bId)}
                        className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
                        title={isKeyVisible ? "Ocultar chave" : "Exibir chave"}
                      >
                        {isKeyVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>

                      {hasApiKey && (
                        <button
                          type="button"
                          onClick={() => handleCopyKey(bId, cred.apiKey)}
                          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
                          title="Copiar chave"
                        >
                          {copiedId === bId ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Additional Field for Betfair (API Secret / Session Token) */}
                {bId === "betfair" && (
                  <div className="space-y-1.5 pt-1">
                    <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-amber-400" />
                      Session Token / API Secret (Opcional):
                    </label>
                    <input
                      type={isKeyVisible ? "text" : "password"}
                      value={cred.apiSecret || ""}
                      onChange={(e) => handleSecretChange(bId, e.target.value)}
                      placeholder="bfair_session_token_live"
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-amber-500 placeholder-slate-600"
                    />
                  </div>
                )}

                {/* Environment Toggle & Operational Specialty */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between">
                    <span className="text-slate-400 font-medium">Ambiente da API:</span>
                    <button
                      type="button"
                      onClick={() => handleEnvironmentToggle(bId)}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono transition ${
                        cred.environment === "production"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                      }`}
                    >
                      {cred.environment === "production" ? "PRODUÇÃO (LIVE)" : "SANDBOX / TESTE"}
                    </button>
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between">
                    <span className="text-slate-400 font-medium">Feed de Dados:</span>
                    <span className="text-emerald-400 font-bold font-mono text-[11px]">
                      {cred.enabled ? "Sincronizado" : "Pausado"}
                    </span>
                  </div>
                </div>

                {/* Test Result Message Box */}
                {testRes && (
                  <div
                    className={`p-2.5 rounded-xl text-xs font-medium flex items-start gap-2 animate-in fade-in ${
                      testRes.success
                        ? "bg-emerald-950/60 border border-emerald-500/40 text-emerald-300"
                        : "bg-rose-950/60 border border-rose-500/40 text-rose-300"
                    }`}
                  >
                    {testRes.success ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex justify-between items-center">
                        <span className="font-bold">
                          {testRes.success ? `Ping Concluído (${testRes.latencyMs}ms)` : "Falha no Teste"}
                        </span>
                        <span className="text-[10px] text-slate-400">{testRes.timestamp}</span>
                      </div>
                      <p className="text-[11px] mt-0.5">{testRes.message}</p>
                    </div>
                  </div>
                )}

                {/* Tactical Tips and Market Specialties */}
                <div className="p-2.5 rounded-xl bg-slate-950/70 border border-slate-800/80 space-y-1 text-[11px]">
                  <div className="flex items-center gap-1.5 text-slate-300">
                    <span className="text-amber-400 font-bold">🎯 Especialidade:</span>
                    <span>{meta.marketSpecialty}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <span className="text-emerald-400 font-bold">⚡ Indicado para:</span>
                    <span>{meta.recommendedFor}</span>
                  </div>
                </div>

                {/* Card Action Footer */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                  <a
                    href={meta.officialDocsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition"
                  >
                    <ExternalLink className="w-3 h-3 text-slate-500" />
                    Documentação da API
                  </a>

                  <button
                    type="button"
                    onClick={() => handleTestConnection(bId)}
                    disabled={isTesting}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold border border-slate-700 transition flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 text-amber-400 ${isTesting ? "animate-spin" : ""}`} />
                    {isTesting ? "Testando Ping..." : "Testar Conexão"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECONDARY BOOKMAKERS SECTION (Sportingbet, KTO, Superbet, 1xBet) */}
      {activeTab === "all" && (
        <div className="space-y-4 pt-4 border-t border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-cyan-400" />
              <h3 className="text-sm font-black uppercase tracking-wider text-slate-200">
                Casas de Apostas Secundárias & Suplementares
              </h3>
            </div>
            <span className="text-xs text-slate-400">
              Cobertura adicional para ligas menores e comparadores de odds
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {SECONDARY_BOOKMAKERS.map((bId) => {
              const bkInfo = AVAILABLE_BOOKMAKERS.find((b) => b.id === bId)!;
              const cred = credentials[bId] || {
                bookmakerId: bId,
                name: bkInfo.name,
                enabled: false,
                apiKey: "",
              };
              const meta = BOOKMAKER_HIGHLIGHTS[bId];
              const testRes = testResults[bId];
              const isTesting = testingId === bId;
              const isKeyVisible = visibleKeys[bId];

              return (
                <div
                  key={bId}
                  className={`rounded-xl border bg-slate-900/90 p-4 shadow-lg transition-all space-y-3 ${
                    cred.enabled ? meta.borderColor : "border-slate-800/80 opacity-75"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className={`px-2.5 py-1 rounded-lg ${bkInfo.badgeBg} border text-xs font-black`}>
                        {bkInfo.shortName}
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-white">{bkInfo.name}</h4>
                        <span className="text-[10px] text-slate-400">{meta.tagline}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggleEnable(bId)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                          cred.enabled ? "bg-emerald-600" : "bg-slate-700"
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                            cred.enabled ? "translate-x-4" : "translate-x-1"
                          }`}
                        />
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-slate-400">API Key:</label>
                    <div className="relative flex items-center">
                      <input
                        type={isKeyVisible ? "text" : "password"}
                        value={cred.apiKey || ""}
                        onChange={(e) => handleKeyChange(bId, e.target.value)}
                        placeholder={`API Key da ${bkInfo.name}`}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-cyan-500 pr-16"
                      />
                      <div className="absolute right-2 flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => toggleVisibleKey(bId)}
                          className="p-1 rounded text-slate-400 hover:text-slate-200"
                        >
                          {isKeyVisible ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        </button>
                      </div>
                    </div>
                  </div>

                  {testRes && (
                    <div className={`p-2 rounded-lg text-[11px] ${testRes.success ? "bg-emerald-950/60 text-emerald-300 border border-emerald-500/30" : "bg-rose-950/60 text-rose-300 border border-rose-500/30"}`}>
                      {testRes.message}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-slate-500">Margem: ~{bkInfo.marginPct}%</span>
                    <button
                      type="button"
                      onClick={() => handleTestConnection(bId)}
                      disabled={isTesting}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium border border-slate-700"
                    >
                      {isTesting ? "Testando..." : "Testar Conexão"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Floating Bottom Save Action Bar */}
      <div className="sticky bottom-4 z-20 bg-slate-900/95 backdrop-blur border border-slate-700 p-4 rounded-2xl shadow-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
          <div>
            <span className="text-xs font-bold text-white block">
              {activeCount} de 8 Casas Habilitadas para Monitoramento de Odds
            </span>
            <span className="text-[11px] text-slate-400">
              As alterações de chaves e ativação têm efeito imediato nas análises do Código 3:1 e comparador de odds.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={handleSaveToBackend}
            disabled={isSaving}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-950/40 transition flex items-center gap-2 disabled:opacity-50"
          >
            {isSaving ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Gravando no Servidor...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Salvar Todas as Configurações</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
