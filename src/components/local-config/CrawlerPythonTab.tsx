import React, { useState, useEffect } from "react";
import {
  Terminal,
  Download,
  Copy,
  Check,
  Radio,
  Server,
  Code,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Play,
  RotateCw,
  Webhook,
  Plus,
  Trash2,
  Zap,
  ShieldCheck,
  Eye,
  EyeOff,
  Activity,
  Clock,
  ArrowRight,
  Sliders,
  Globe,
  Key,
  Layers,
  FileText,
  KeyRound,
  Compass,
  Gauge,
  Cpu,
  CheckSquare,
  Square,
  RefreshCw,
} from "lucide-react";
import { safeFetchJson } from "../../api";
import {
  CustomWebhookEndpoint,
  WebhookDeliveryLog,
  CrawlerStatus,
  OperationalRulesConfig,
  UserProfile,
} from "../../types";

interface CrawlerPythonTabProps {
  userProfile: UserProfile | null;
  rulesConfig: OperationalRulesConfig;
  setRulesConfig: (config: OperationalRulesConfig) => void;
  customWebhooks: CustomWebhookEndpoint[];
  setCustomWebhooks: (webhooks: CustomWebhookEndpoint[]) => void;
  handleSaveToDisk: (customPayload?: any, successMessage?: string) => Promise<void>;
  copyToken: () => void;
  copiedToken: boolean;
  handleRegenerateToken: () => Promise<void>;
}

export function CrawlerPythonTab({
  userProfile,
  rulesConfig,
  setRulesConfig,
  customWebhooks,
  setCustomWebhooks,
  handleSaveToDisk,
  copyToken,
  copiedToken,
  handleRegenerateToken,
}: CrawlerPythonTabProps) {
  const [subTab, setSubTab] = useState<
    "overview" | "catalog" | "webhooks" | "snippets" | "logs" | "instructions"
  >("overview");

  // Webhooks state
  const [webhookLogs, setWebhookLogs] = useState<WebhookDeliveryLog[]>([]);
  const [selectedWebhookForCode, setSelectedWebhookForCode] = useState<CustomWebhookEndpoint | null>(
    customWebhooks[0] || null
  );
  const [showSecretMap, setShowSecretMap] = useState<Record<string, boolean>>({});
  const [copiedSnippet, setCopiedSnippet] = useState<boolean>(false);
  const [copiedWebhookId, setCopiedWebhookId] = useState<string | null>(null);

  // Form / Test state
  const [isAddingWebhook, setIsAddingWebhook] = useState<boolean>(false);
  const [editingWebhookId, setEditingWebhookId] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    slug: "",
    secretToken: "",
    description: "",
    active: true,
    asyncMode: true,
    autoTriggerAlerts: true,
    autoComputeMomentum: true,
    targetLeague: "Geral / Brasileirão Série A",
  });
  const [testingWebhookId, setTestingWebhookId] = useState<string | null>(null);
  const [webhookTestFeedback, setWebhookTestFeedback] = useState<{
    id: string;
    success: boolean;
    message: string;
  } | null>(null);
  const [codeLang, setCodeLang] = useState<"python" | "async_python" | "curl" | "node">("python");

  // Fetch Webhook Logs
  const fetchWebhookLogs = async () => {
    try {
      const data = await safeFetchJson<{ logs: WebhookDeliveryLog[] }>("/api/crawler/webhook-logs");
      if (data?.logs) {
        setWebhookLogs(data.logs);
      }
    } catch {}
  };

  useEffect(() => {
    fetchWebhookLogs();
    const interval = setInterval(fetchWebhookLogs, 6000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (customWebhooks.length > 0 && !selectedWebhookForCode) {
      setSelectedWebhookForCode(customWebhooks[0]);
    }
  }, [customWebhooks]);

  const handleOpenCreateWebhook = () => {
    setEditingWebhookId(null);
    const randomSec = `sec_${Math.random().toString(36).substring(2, 10)}_${Date.now().toString().slice(-4)}`;
    setFormData({
      name: "",
      slug: "",
      secretToken: randomSec,
      description: "Recepção assíncrona de dados de partidas em tempo real.",
      active: true,
      asyncMode: true,
      autoTriggerAlerts: true,
      autoComputeMomentum: true,
      targetLeague: "Geral / Brasileirão Série A",
    });
    setIsAddingWebhook(true);
  };

  const handleOpenEditWebhook = (wh: CustomWebhookEndpoint) => {
    setEditingWebhookId(wh.id);
    setFormData({
      name: wh.name,
      slug: wh.slug,
      secretToken: wh.secretToken,
      description: wh.description,
      active: wh.active,
      asyncMode: wh.asyncMode,
      autoTriggerAlerts: wh.autoTriggerAlerts,
      autoComputeMomentum: wh.autoComputeMomentum,
      targetLeague: wh.targetLeague || "Geral",
    });
    setIsAddingWebhook(true);
  };

  const handleSaveWebhookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    const formattedSlug = (formData.slug.trim() || formData.name.toLowerCase())
      .replace(/[^a-z0-9_-]/gi, "-")
      .toLowerCase();

    let updatedList: CustomWebhookEndpoint[];
    if (editingWebhookId) {
      updatedList = customWebhooks.map((w) =>
        w.id === editingWebhookId
          ? {
              ...w,
              name: formData.name.trim(),
              slug: formattedSlug,
              secretToken: formData.secretToken.trim() || w.secretToken,
              description: formData.description.trim(),
              active: formData.active,
              asyncMode: formData.asyncMode,
              autoTriggerAlerts: formData.autoTriggerAlerts,
              autoComputeMomentum: formData.autoComputeMomentum,
              targetLeague: formData.targetLeague.trim(),
            }
          : w
      );
    } else {
      const newWh: CustomWebhookEndpoint = {
        id: `wh_${Date.now()}`,
        name: formData.name.trim(),
        slug: formattedSlug,
        secretToken: formData.secretToken.trim() || `sec_${Date.now()}`,
        description: formData.description.trim() || "Endpoint de ingestão personalizado",
        active: formData.active,
        asyncMode: formData.asyncMode,
        autoTriggerAlerts: formData.autoTriggerAlerts,
        autoComputeMomentum: formData.autoComputeMomentum,
        targetLeague: formData.targetLeague.trim() || "Geral",
        createdAt: new Date().toISOString(),
        totalCalls: 0,
        lastStatus: "ok",
      };
      updatedList = [...customWebhooks, newWh];
    }

    setCustomWebhooks(updatedList);
    setIsAddingWebhook(false);
    await handleSaveToDisk(
      { customWebhooks: updatedList },
      editingWebhookId ? "Webhook atualizado com sucesso!" : "Novo Webhook criado e salvo no disco!"
    );
  };

  const handleToggleWebhook = async (whId: string) => {
    const updated = customWebhooks.map((w) => (w.id === whId ? { ...w, active: !w.active } : w));
    setCustomWebhooks(updated);
    await handleSaveToDisk({ customWebhooks: updated }, "Status do webhook atualizado no disco!");
  };

  const handleDeleteWebhook = async (whId: string) => {
    if (window.confirm("Deseja excluir permanentemente este endpoint de webhook?")) {
      const updated = customWebhooks.filter((w) => w.id !== whId);
      setCustomWebhooks(updated);
      await handleSaveToDisk({ customWebhooks: updated }, "Webhook excluído do disco!");
    }
  };

  const handleTestWebhook = async (wh: CustomWebhookEndpoint) => {
    setTestingWebhookId(wh.id);
    setWebhookTestFeedback(null);

    const mockPayload = {
      matches: [
        {
          id: `test_match_${Date.now()}`,
          homeTeamName: "Flamengo",
          awayTeamName: "Palmeiras",
          homeScore: 1,
          awayScore: 0,
          minute: 68,
          status: "IN_PLAY",
          league: "Brasileirão Série A",
          stats: {
            possession: { home: 62, away: 38 },
            shotsOnTarget: { home: 6, away: 2 },
            shotsOffTarget: { home: 8, away: 4 },
            corners: { home: 7, away: 3 },
            dangerousAttacks: { home: 54, away: 28 },
            xg: { home: 1.85, away: 0.42 },
          },
        },
      ],
    };

    const startTime = Date.now();
    try {
      const res = await fetch(`/api/crawler/webhook/${wh.slug}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${wh.secretToken}`,
        },
        body: JSON.stringify(mockPayload),
      });
      const latency = Date.now() - startTime;
      const json = await res.json();

      if (res.ok && json.success) {
        setWebhookTestFeedback({
          id: wh.id,
          success: true,
          message: `Sucesso (${latency}ms)! Pacote ingerido (${json.matchesIngested || 1} partida).`,
        });
        fetchWebhookLogs();
      } else {
        setWebhookTestFeedback({
          id: wh.id,
          success: false,
          message: `Erro ${res.status}: ${json.error || "Falha na validação"}`,
        });
      }
    } catch (err: any) {
      setWebhookTestFeedback({
        id: wh.id,
        success: false,
        message: `Falha de rede: ${err.message}`,
      });
    } finally {
      setTestingWebhookId(null);
    }
  };

  const tokenToUse = userProfile?.crawlerToken || "footstats-crawler-live-key-99";
  const activeWh = selectedWebhookForCode || customWebhooks[0] || {
    id: "default",
    name: "Ingestão Geral",
    slug: "ingest",
    secretToken: tokenToUse,
  };

  const localHost = "http://127.0.0.1:3000";
  const endpointUrl = `${localHost}/api/crawler/webhook/${activeWh.slug}`;

  // Code Snippets Generation
  const getPythonSnippet = () => {
    return `# -*- coding: utf-8 -*-
"""
FootStats Radar - Ingestão de Dados em Tempo Real via Python
Requisitos: pip install requests
"""
import requests
import json
import time

ENDPOINT_URL = "${endpointUrl}"
SECRET_TOKEN = "${activeWh.secretToken}"

def send_matches_to_radar(matches_list):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SECRET_TOKEN}",
        "X-Crawler-Key": SECRET_TOKEN
    }
    
    payload = {
        "matches": matches_list,
        "timestamp": int(time.time()),
        "source": "Python_Crawler_Engine"
    }
    
    try:
        response = requests.post(ENDPOINT_URL, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Ingerido com sucesso: {data.get('matchesIngested')} jogos.")
            return True
        else:
            print(f"[ERRO {response.status_code}] {response.text}")
            return False
    except Exception as e:
        print(f"[FALHA DE REDE] {e}")
        return False

# Exemplo de partida coletada:
sample_match = [{
    "id": "match_live_001",
    "homeTeamName": "Real Madrid",
    "awayTeamName": "Barcelona",
    "homeScore": 1,
    "awayScore": 1,
    "minute": 74,
    "status": "IN_PLAY",
    "league": "La Liga",
    "stats": {
        "possession": {"home": 56, "away": 44},
        "shotsOnTarget": {"home": 7, "away": 4},
        "shotsOffTarget": {"home": 6, "away": 3},
        "corners": {"home": 8, "away": 3},
        "dangerousAttacks": {"home": 62, "away": 39},
        "xg": {"home": 1.94, "away": 1.12}
    }
}]

if __name__ == "__main__":
    send_matches_to_radar(sample_match)
`;
  };

  const getAsyncPythonSnippet = () => {
    return `# -*- coding: utf-8 -*-
"""
FootStats Radar - Ingestão Assíncrona de Alta Velocidade (aiohttp)
Requisitos: pip install aiohttp
"""
import aiohttp
import asyncio
import time

ENDPOINT_URL = "${endpointUrl}"
SECRET_TOKEN = "${activeWh.secretToken}"

async def push_batch_async(session, matches):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SECRET_TOKEN}"
    }
    payload = {"matches": matches, "timestamp": int(time.time())}
    
    async with session.post(ENDPOINT_URL, json=payload, headers=headers) as resp:
        res = await resp.json()
        print(f"Status: {resp.status} -> {res}")

async def main():
    async with aiohttp.ClientSession() as session:
        # Substitua com seus dados coletados
        await push_batch_async(session, [{"id": "flamengo_vs_palmeiras", "homeTeamName": "Flamengo", "awayTeamName": "Palmeiras", "homeScore": 2, "awayScore": 1, "minute": 82, "status": "IN_PLAY"}])

if __name__ == "__main__":
    asyncio.run(main())
`;
  };

  const getCurlSnippet = () => {
    return `curl -X POST "${endpointUrl}" \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${activeWh.secretToken}" \\
  -d '{
    "matches": [
      {
        "id": "match_live_curl_01",
        "homeTeamName": "Arsenal",
        "awayTeamName": "Chelsea",
        "homeScore": 2,
        "awayScore": 0,
        "minute": 65,
        "status": "IN_PLAY",
        "league": "Premier League",
        "stats": {
          "possession": { "home": 58, "away": 42 },
          "shotsOnTarget": { "home": 6, "away": 2 },
          "corners": { "home": 6, "away": 3 },
          "dangerousAttacks": { "home": 50, "away": 30 },
          "xg": { "home": 1.78, "away": 0.35 }
        }
      }
    ]
  }'`;
  };

  const getNodeSnippet = () => {
    return `// FootStats Radar - Ingestão via Node.js / TypeScript
const ENDPOINT_URL = "${endpointUrl}";
const SECRET_TOKEN = "${activeWh.secretToken}";

async function sendMatches(matches) {
  const response = await fetch(ENDPOINT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": \`Bearer \${SECRET_TOKEN}\`,
    },
    body: JSON.stringify({
      matches,
      timestamp: Date.now(),
    }),
  });

  const data = await response.json();
  console.log("Resposta:", data);
}
`;
  };

  const getSnippetCode = () => {
    switch (codeLang) {
      case "python":
        return getPythonSnippet();
      case "async_python":
        return getAsyncPythonSnippet();
      case "curl":
        return getCurlSnippet();
      case "node":
        return getNodeSnippet();
    }
  };

  const copyCodeSnippet = () => {
    navigator.clipboard.writeText(getSnippetCode());
    setCopiedSnippet(true);
    setTimeout(() => setCopiedSnippet(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Sub-Tabs de Navegação Interna */}
      <div className="flex items-center gap-1.5 p-1 bg-slate-950/80 rounded-xl border border-slate-800/80 overflow-x-auto">
        {[
          { id: "overview", label: "Visão Geral & Scripts", icon: <Terminal className="w-3.5 h-3.5" /> },
          { id: "catalog", label: "Catálogo & Cache TIER", icon: <Compass className="w-3.5 h-3.5" /> },
          { id: "webhooks", label: `Webhooks (${customWebhooks.length})`, icon: <Webhook className="w-3.5 h-3.5" /> },
          { id: "snippets", label: "Exemplos de Código", icon: <Code className="w-3.5 h-3.5" /> },
          { id: "logs", label: `Logs Recentes (${webhookLogs.length})`, icon: <Activity className="w-3.5 h-3.5" /> },
          { id: "instructions", label: "Especificação JSON", icon: <FileText className="w-3.5 h-3.5" /> },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setSubTab(t.id as any)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
              subTab === t.id
                ? "bg-slate-800 text-purple-300 border border-purple-500/40 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {/* ======================================================== */}
      {/* 1. VISÃO GERAL & SCRIPTS                                 */}
      {/* ======================================================== */}
      {subTab === "overview" && (
        <div className="space-y-6 animate-in fade-in">
          {/* Download Python Scripts */}
          <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between flex-wrap gap-3">
            <div>
              <h5 className="font-bold text-xs text-slate-200">Script Python Unificado Pronto para Execução</h5>
              <p className="text-xs text-slate-400">
                Baixe o motor oficial unificado <b className="text-cyan-400 font-mono">bridge_web.py</b> pré-configurado para modo Standalone Local.
              </p>
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
        </div>
      )}

      {/* ======================================================== */}
      {/* 2. CATÁLOGO & DESCOBERTA EM BACKGROUND                   */}
      {/* ======================================================== */}
      {subTab === "catalog" && (
        <div className="space-y-6 animate-in fade-in">
          <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <div className="p-2 bg-cyan-500/10 rounded-lg text-cyan-400">
                  <Compass className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="font-bold text-white text-sm">Catálogo Persistente & Descoberta em Background</h4>
                  <p className="text-xs text-slate-400">
                    Otimizações de descoberta de partidas ao vivo desacopladas do ciclo de varredura detalhada.
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
                        ...(rulesConfig.crawlerConfig as any),
                        discoveryIntervalSeconds: val,
                      },
                    });
                  }}
                  className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                />
                <p className="text-[10px] text-slate-500">Frequência com que a aba inicial de jogos é varrida.</p>
              </div>

              {/* Faxina do Catálogo */}
              <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                  <span>Faxina Catálogo (min):</span>
                  <span className="font-mono text-cyan-400">{rulesConfig.crawlerConfig?.catalogPruneMinutes || 25} min</span>
                </label>
                <input
                  type="range"
                  min={10}
                  max={60}
                  step={5}
                  value={rulesConfig.crawlerConfig?.catalogPruneMinutes || 25}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setRulesConfig({
                      ...rulesConfig,
                      crawlerConfig: {
                        ...(rulesConfig.crawlerConfig as any),
                        catalogPruneMinutes: val,
                      },
                    });
                  }}
                  className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                />
                <p className="text-[10px] text-slate-500">Expurgo automático de partidas encerradas do catálogo.</p>
              </div>

              {/* Backoff Sem Estatísticas */}
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
                        ...(rulesConfig.crawlerConfig as any),
                        noStatsBackoffMinutes: val,
                      },
                    });
                  }}
                  className="w-full accent-cyan-500 h-1.5 bg-slate-950 rounded-lg cursor-pointer"
                />
                <p className="text-[10px] text-slate-500">Pausa em jogos sem aba de estatísticas para não travar o scraper.</p>
              </div>
            </div>

            {/* Watchlist Priorizada */}
            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-xl space-y-3 pt-3">
              <h5 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                Configurações da Watchlist Priorizada
              </h5>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                {/* Tamanho da Watchlist */}
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
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
                          ...(rulesConfig.crawlerConfig as any),
                          maxWatchlistSize: val,
                        },
                      });
                    }}
                    className="w-full accent-emerald-500 h-1.5 bg-slate-900 rounded-lg cursor-pointer"
                  />
                  <p className="text-[10px] text-slate-500">Total de jogos prioritários escaneados a cada ciclo.</p>
                </div>

                {/* Slots Reservados Tier 3 */}
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
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
                          ...(rulesConfig.crawlerConfig as any),
                          tier3ReservedSlots: val,
                        },
                      });
                    }}
                    className="w-full accent-emerald-500 h-1.5 bg-slate-900 rounded-lg cursor-pointer"
                  />
                  <p className="text-[10px] text-slate-500">Garante que ligas alternativas passem por varredura contínua.</p>
                </div>

                {/* Janela Watchlist */}
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
                  <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                    <span>Janela Minutos:</span>
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
                            ...(rulesConfig.crawlerConfig as any),
                            minEntryMinute: val,
                          },
                        });
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white font-mono text-center"
                    />
                    <span className="text-slate-500 text-xs">até</span>
                    <input
                      type="number"
                      min={45}
                      max={95}
                      value={rulesConfig.crawlerConfig?.maxEntryMinute || 83}
                      onChange={(e) => {
                        const val = parseInt(e.target.value) || 83;
                        setRulesConfig({
                          ...rulesConfig,
                          crawlerConfig: {
                            ...(rulesConfig.crawlerConfig as any),
                            maxEntryMinute: val,
                          },
                        });
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white font-mono text-center"
                    />
                  </div>
                </div>

                {/* Anti-Spam Cooldown */}
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1.5">
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
                          ...(rulesConfig.crawlerConfig as any),
                          antiSpamCooldownMinutes: val,
                        },
                      });
                    }}
                    className="w-full accent-emerald-500 h-1.5 bg-slate-900 rounded-lg cursor-pointer"
                  />
                  <p className="text-[10px] text-slate-500">Mantém o jogo fixo no Tier 0 para monitorar evolução pós-sinal.</p>
                </div>
              </div>

              {/* Toggles de Tiers */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
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
                            ...(rulesConfig.crawlerConfig as any),
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
                          : "bg-slate-950 border-slate-800 text-slate-500"
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
        </div>
      )}

      {/* ======================================================== */}
      {/* 3. GERENCIADOR DE WEBHOOKS                               */}
      {/* ======================================================== */}
      {subTab === "webhooks" && (
        <div className="space-y-4 animate-in fade-in">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Webhook className="w-3.5 h-3.5 text-emerald-400" />
                Endpoints Webhooks de Ingestão ({customWebhooks.length})
              </h5>
              <p className="text-xs text-slate-400">Configure slugs e segredos para alimentar o Radar via scripts externos.</p>
            </div>
            <button
              onClick={handleOpenCreateWebhook}
              className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              Novo Webhook
            </button>
          </div>

          {/* Form Modal / Inset */}
          {isAddingWebhook && (
            <form onSubmit={handleSaveWebhookSubmit} className="p-4 bg-slate-900 border border-emerald-500/40 rounded-xl space-y-3 animate-in fade-in">
              <h6 className="font-bold text-xs text-emerald-300">
                {editingWebhookId ? "Editar Endpoint de Webhook" : "Cadastrar Novo Webhook de Ingestão"}
              </h6>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Nome de Identificação</label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="Ex: Playwright Flashscore Live"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Slug da URL (/api/crawler/webhook/:slug)</label>
                  <input
                    type="text"
                    value={formData.slug}
                    onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                    placeholder="Ex: flashscore-live"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Token Secreto do Webhook</label>
                  <input
                    type="text"
                    value={formData.secretToken}
                    onChange={(e) => setFormData({ ...formData, secretToken: e.target.value })}
                    placeholder="Token secreto..."
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Liga Alvo / Tag</label>
                  <input
                    type="text"
                    value={formData.targetLeague}
                    onChange={(e) => setFormData({ ...formData, targetLeague: e.target.value })}
                    placeholder="Ex: Premier League / Geral"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Descrição</label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Ex: Coleta a cada 15 segundos dos jogos em andamento..."
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
                />
              </div>

              <div className="flex flex-wrap gap-4 pt-1">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.autoTriggerAlerts}
                    onChange={(e) => setFormData({ ...formData, autoTriggerAlerts: e.target.checked })}
                    className="accent-emerald-500"
                  />
                  <span>Disparar Alertas Sonoros e Push</span>
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.autoComputeMomentum}
                    onChange={(e) => setFormData({ ...formData, autoComputeMomentum: e.target.checked })}
                    className="accent-emerald-500"
                  />
                  <span>Calcular Gráfico de Pressão & Momentum</span>
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAddingWebhook(false)}
                  className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-xs"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-xs shadow"
                >
                  Salvar Webhook no Disco
                </button>
              </div>
            </form>
          )}

          {/* Webhooks List */}
          <div className="space-y-2">
            {customWebhooks.map((wh) => {
              const isTesting = testingWebhookId === wh.id;
              const isShowingSecret = Boolean(showSecretMap[wh.id]);
              const url = `${localHost}/api/crawler/webhook/${wh.slug}`;

              return (
                <div
                  key={wh.id}
                  className="p-3.5 bg-slate-900/80 border border-slate-800 rounded-xl space-y-2 hover:border-slate-700 transition"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${wh.active ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
                      <span className="font-bold text-xs text-white">{wh.name}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 text-emerald-400 border border-slate-800">
                        /api/crawler/webhook/{wh.slug}
                      </span>
                      {wh.targetLeague && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">
                          {wh.targetLeague}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleTestWebhook(wh)}
                        disabled={isTesting}
                        className="flex items-center gap-1 px-2.5 py-1 bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/30 text-cyan-300 rounded-lg text-[11px] font-bold transition disabled:opacity-50"
                      >
                        <Play className={`w-3 h-3 text-cyan-400 ${isTesting ? "animate-spin" : ""}`} />
                        <span>{isTesting ? "Enviando..." : "Testar Webhook"}</span>
                      </button>
                      <button
                        onClick={() => handleOpenEditWebhook(wh)}
                        className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded-lg text-[11px] transition"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleToggleWebhook(wh.id)}
                        className={`px-2 py-1 rounded text-[11px] font-bold border transition ${
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

                  {/* Secret Token & Info Row */}
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono pt-1 border-t border-slate-800/60 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span>Token:</span>
                      <span className="bg-slate-950 px-2 py-0.5 rounded text-purple-300 border border-slate-800">
                        {isShowingSecret ? wh.secretToken : "••••••••••••••••"}
                      </span>
                      <button
                        onClick={() => setShowSecretMap({ ...showSecretMap, [wh.id]: !isShowingSecret })}
                        className="text-slate-400 hover:text-white"
                        title={isShowingSecret ? "Ocultar" : "Revelar"}
                      >
                        {isShowingSecret ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      </button>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(wh.secretToken);
                          setCopiedWebhookId(wh.id);
                          setTimeout(() => setCopiedWebhookId(null), 2000);
                        }}
                        className="text-slate-400 hover:text-white"
                        title="Copiar Token"
                      >
                        {copiedWebhookId === wh.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </div>

                    <div className="flex items-center gap-3">
                      <span>Status: <b className="text-slate-200">{wh.lastStatus || "ok"}</b></span>
                      <span>Chamadas: <b className="text-cyan-400">{wh.totalCalls || 0}</b></span>
                      {wh.lastCallTimestamp && (
                        <span>Último: {new Date(wh.lastCallTimestamp).toLocaleTimeString()}</span>
                      )}
                    </div>
                  </div>

                  {/* Test Feedback */}
                  {webhookTestFeedback?.id === wh.id && (
                    <div
                      className={`p-2 rounded-lg text-xs font-mono flex items-center gap-1.5 ${
                        webhookTestFeedback.success
                          ? "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"
                          : "bg-rose-500/15 border border-rose-500/40 text-rose-300"
                      }`}
                    >
                      {webhookTestFeedback.success ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
                      <span>{webhookTestFeedback.message}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* 4. EXEMPLOS DE CÓDIGO (SNIPPETS)                         */}
      {/* ======================================================== */}
      {subTab === "snippets" && (
        <div className="space-y-4 animate-in fade-in">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Code className="w-3.5 h-3.5 text-cyan-400" />
                Exemplos Interativos de Envio de Payload HTTP
              </h5>
              <p className="text-xs text-slate-400">Copie o código pronto para enviar dados de partidas para o Webhook selecionado.</p>
            </div>

            {/* Language & Webhook Selectors */}
            <div className="flex items-center gap-2">
              <select
                value={selectedWebhookForCode?.id || ""}
                onChange={(e) => {
                  const target = customWebhooks.find((w) => w.id === e.target.value);
                  if (target) setSelectedWebhookForCode(target);
                }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200"
              >
                {customWebhooks.map((w) => (
                  <option key={w.id} value={w.id}>
                    Endpoint: {w.name}
                  </option>
                ))}
              </select>

              <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800">
                {[
                  { id: "python", label: "Python (requests)" },
                  { id: "async_python", label: "Python (aiohttp)" },
                  { id: "curl", label: "cURL Bash" },
                  { id: "node", label: "Node.js" },
                ].map((l) => (
                  <button
                    key={l.id}
                    onClick={() => setCodeLang(l.id as any)}
                    className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                      codeLang === l.id ? "bg-cyan-600 text-white" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Code Viewer */}
          <div className="relative rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-slate-900/80 border-b border-slate-800 text-xs text-slate-400">
              <span className="font-mono text-cyan-300">
                POST {endpointUrl}
              </span>
              <button
                onClick={copyCodeSnippet}
                className="flex items-center gap-1 px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-bold transition"
              >
                {copiedSnippet ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSnippet ? "Copiado!" : "Copiar Código"}</span>
              </button>
            </div>
            <pre className="p-4 text-xs font-mono text-slate-300 overflow-x-auto leading-relaxed max-h-[380px]">
              {getSnippetCode()}
            </pre>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* 5. LOGS DE ENTREGAS HTTP                                 */}
      {/* ======================================================== */}
      {subTab === "logs" && (
        <div className="space-y-4 animate-in fade-in">
          <div className="flex items-center justify-between">
            <div>
              <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-amber-400" />
                Histórico Recente de Requisições HTTP Recebidas
              </h5>
              <p className="text-xs text-slate-400">Logs das últimas entregas recebidas nos endpoints de webhooks.</p>
            </div>
            <button
              onClick={fetchWebhookLogs}
              className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition"
            >
              <RotateCw className="w-3.5 h-3.5 text-cyan-400" />
              <span>Atualizar</span>
            </button>
          </div>

          {webhookLogs.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/40 border border-slate-800 rounded-xl space-y-2">
              <Terminal className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="text-xs text-slate-400">Nenhum log registrado ainda. Execute o script ou teste um webhook acima.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[380px] overflow-y-auto">
              {webhookLogs.map((log) => (
                <div
                  key={log.id}
                  className="p-3 bg-slate-900/70 border border-slate-800 rounded-xl flex items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`px-1.5 py-0.5 rounded font-bold uppercase text-[10px] ${
                        log.statusCode === 200
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      }`}
                    >
                      {log.statusCode} {log.method}
                    </span>
                    <span className="text-slate-300 truncate">{log.endpoint}</span>
                    {log.ip && <span className="text-slate-500 text-[10px]">({log.ip})</span>}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 text-slate-400 text-[11px]">
                    {log.latencyMs !== undefined && <span>{log.latencyMs}ms</span>}
                    <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ======================================================== */}
      {/* 6. ESPECIFICAÇÃO JSON & ARQUITETURA                      */}
      {/* ======================================================== */}
      {subTab === "instructions" && (
        <div className="space-y-4 text-xs text-slate-300 animate-in fade-in">
          <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-xl space-y-3">
            <h5 className="font-bold text-sm text-white flex items-center gap-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              Especificação do Formato JSON da Partida
            </h5>
            <p className="text-slate-400">
              O backend do FootStats Radar aceita arrays de partidas no campo <code className="text-emerald-300">matches</code>.
            </p>

            <pre className="bg-slate-900 p-3 rounded-lg border border-slate-800 font-mono text-[11px] text-emerald-300 overflow-x-auto">
{`{
  "matches": [
    {
      "id": "partida_123",              // Obrigatório: ID único
      "homeTeamName": "Flamengo",        // Obrigatório: Nome Mandante
      "awayTeamName": "Fluminense",      // Obrigatório: Nome Visitante
      "homeScore": 1,                    // Placar Mandante
      "awayScore": 0,                    // Placar Visitante
      "minute": 55,                      // Minuto atual de jogo
      "status": "IN_PLAY",               // "IN_PLAY", "HT", "FINISHED"
      "league": "Brasileirão Série A",   // Campeonato
      "stats": {
        "possession": { "home": 60, "away": 40 },
        "shotsOnTarget": { "home": 5, "away": 2 },
        "shotsOffTarget": { "home": 4, "away": 3 },
        "corners": { "home": 6, "away": 2 },
        "dangerousAttacks": { "home": 45, "away": 22 },
        "xg": { "home": 1.45, "away": 0.38 }
      }
    }
  ]
}`}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
