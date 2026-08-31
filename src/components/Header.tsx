import { Activity, Bell, Radio, Terminal, Zap, Volume2, VolumeX, Sliders, HardDrive, KeyRound, User as UserIcon, Check, Copy, ShieldCheck } from "lucide-react";
import { CrawlerStatus } from "../types";
import { useAuth } from "../context/AuthContext";
import React, { useState } from "react";

interface HeaderProps {
  activeTab: "dashboard" | "alerts";
  setActiveTab: (tab: "dashboard" | "alerts") => void;
  crawlerStatus: CrawlerStatus | null;
  unreadAlertsCount: number;
  soundEnabled: boolean;
  setSoundEnabled: (enabled: boolean) => void;
  liveMatchesCount: number;
  onOpenLocalConfig?: (tab?: "rules_engine" | "alerts_noise" | "bookmakers" | "crawler" | "backup_profile") => void;
  ratioConfigured?: number;
}

export function Header({
  activeTab,
  setActiveTab,
  crawlerStatus,
  unreadAlertsCount,
  soundEnabled,
  setSoundEnabled,
  liveMatchesCount,
  onOpenLocalConfig,
  ratioConfigured = 3.0,
}: HeaderProps) {
  const isCrawlerOnline = crawlerStatus?.connected;
  const { userProfile } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);

  const copyToken = () => {
    if (userProfile?.crawlerToken) {
      navigator.clipboard.writeText(userProfile.crawlerToken);
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    }
  };

  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 text-slate-950 shadow-md shadow-emerald-500/20">
              <Activity className="w-6 h-6 stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-lg font-black tracking-tight text-white">BacanaLive</span>
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  RADAR PRO
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 hidden lg:inline">
                  Standalone Local
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                Terminal de futebol ao vivo, Diagnóstico & Ingestão Local
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center bg-slate-950/80 p-1 rounded-xl border border-slate-800/80">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-2 ${
                activeTab === "dashboard"
                  ? "bg-slate-800 text-white shadow-sm shadow-black/40 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Radio className="w-3.5 h-3.5 text-emerald-400" />
              <span>Jogos ao Vivo</span>
              {liveMatchesCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-md bg-emerald-500/20 text-emerald-300 text-[10px] font-bold">
                  {liveMatchesCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("alerts")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-2 relative ${
                activeTab === "alerts"
                  ? "bg-slate-800 text-white shadow-sm shadow-black/40 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Bell className="w-3.5 h-3.5 text-amber-400" />
              <span>Alertas & Regras</span>
              {unreadAlertsCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-md bg-rose-500 text-white text-[10px] font-bold animate-bounce">
                  {unreadAlertsCount}
                </span>
              )}
            </button>
          </nav>

          {/* Quick Controls & Local Storage */}
          <div className="flex items-center space-x-2">
            {/* Active Engine Ratio Indicator / Direct Shortcut to CONFIG -> rules_engine */}
            {onOpenLocalConfig && (
              <button
                id="btn-header-active-ratio"
                onClick={() => onOpenLocalConfig("rules_engine")}
                title={`Motor de Regras Ativo: Índice ${ratioConfigured.toFixed(1)}:1 (Chances Claras por Gol). Clique para configurar.`}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 hover:border-amber-500/50 transition cursor-pointer shadow-sm group"
              >
                <Sliders className="w-3.5 h-3.5 text-amber-400 group-hover:rotate-45 transition-transform" />
                <span className="text-[10px] text-slate-400 font-semibold uppercase hidden md:inline">Índice:</span>
                <span className="font-mono text-amber-300 font-black tracking-tight">{ratioConfigured.toFixed(1)}:1</span>
              </button>
            )}

            {/* Local Storage & Unified Config Button */}
            {onOpenLocalConfig && (
              <button
                id="btn-local-config"
                onClick={() => onOpenLocalConfig()}
                title="Central de Configuração Local & Motor de Regras"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 transition shadow-sm"
              >
                <HardDrive className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden sm:inline">Config Local</span>
              </button>
            )}

            {/* Audio Toggle */}
            <button
              onClick={() => setSoundEnabled(!soundEnabled)}
              title={soundEnabled ? "Alertas sonoros ativados" : "Alertas sonoros desativados"}
              className={`p-2 rounded-lg border transition-colors ${
                soundEnabled
                  ? "bg-slate-800/80 border-slate-700 text-emerald-400 hover:bg-slate-700"
                  : "bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300"
              }`}
            >
              {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {/* User Profile / Local Mode Info */}
            <div className="relative">
              <button
                id="btn-user-profile-menu"
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="flex items-center gap-2 p-1.5 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition"
              >
                <div className="w-7 h-7 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 flex items-center justify-center font-bold text-xs">
                  <UserIcon className="w-4 h-4" />
                </div>
                <span className="text-xs font-semibold text-slate-300 hidden md:inline max-w-[110px] truncate">
                  {userProfile?.displayName || "Trader Local"}
                </span>
              </button>

              {/* User Dropdown */}
              {showUserMenu && (
                <div
                  className="absolute right-0 mt-2 w-72 bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-4 z-50 animate-in fade-in slide-in-from-top-2 duration-150"
                  onMouseLeave={() => setShowUserMenu(false)}
                >
                  <div className="flex items-center gap-3 pb-3 border-b border-slate-800">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 flex items-center justify-center font-bold text-base">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold text-white truncate">
                        {userProfile?.displayName || "Trader Local Pro"}
                      </div>
                      <div className="text-[11px] text-slate-400 truncate">Modo Standalone Local</div>
                      <div className="mt-1">
                        <span className="px-2 py-0.2 rounded text-[9px] font-extrabold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          Admin Local
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Crawler Token Info */}
                  <div className="my-3 p-2.5 rounded-xl bg-slate-950 border border-slate-800/80">
                    <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                      <span className="flex items-center gap-1 font-semibold text-slate-300">
                        <KeyRound className="w-3 h-3 text-emerald-400" />
                        Token Local do Crawler:
                      </span>
                      <button
                        onClick={copyToken}
                        className="text-emerald-400 hover:text-emerald-300 font-bold flex items-center gap-0.5"
                      >
                        {copiedToken ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                        {copiedToken ? "Copiado!" : "Copiar"}
                      </button>
                    </div>
                    <code className="block text-[11px] font-mono text-emerald-400 bg-slate-900 px-2 py-1 rounded border border-slate-800 truncate select-all">
                      {userProfile?.crawlerToken || "footstats-crawler-live-key-99"}
                    </code>
                  </div>

                  {/* Actions */}
                  <div className="space-y-1.5 pt-1">
                    {onOpenLocalConfig && (
                      <button
                        onClick={() => {
                          setShowUserMenu(false);
                          onOpenLocalConfig();
                        }}
                        className="w-full py-2 px-3 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 text-xs font-bold transition flex items-center gap-2 border border-emerald-500/20"
                      >
                        <HardDrive className="w-3.5 h-3.5 text-emerald-400" />
                        Gerenciar Arquivo de Configuração
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
