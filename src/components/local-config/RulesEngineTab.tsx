import React, { useState } from "react";
import {
  Zap,
  Sliders,
  Clock,
  Filter,
  Flame,
  Sparkles,
  Target,
  TrendingUp,
  ShieldAlert,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { OperationalRulesConfig } from "../../types";

interface RulesEngineTabProps {
  rulesConfig: OperationalRulesConfig;
  setRulesConfig: (config: OperationalRulesConfig) => void;
  applyRatioPreset: (val: number) => void;
}

export function RulesEngineTab({
  rulesConfig,
  setRulesConfig,
  applyRatioPreset,
}: RulesEngineTabProps) {
  const [showFormulas, setShowFormulas] = useState<boolean>(false);

  return (
    <div className="space-y-6">
      {/* 1. Ratio Central do Radar (Diagnóstico) */}
      <div className="p-4 bg-slate-950/70 border border-amber-500/30 rounded-2xl space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-amber-500/10 rounded-lg text-amber-400">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <h4 className="font-bold text-white text-sm">Parâmetro Central do Radar (Diagnóstico)</h4>
              <p className="text-xs text-slate-400">
                Proporção de Chances Claras (CC) necessárias para justificar 1 gol na dívida estatística.
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

      {/* 2. Taxas de Ritmo e Janelas de Minutos */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Taxas Máximas de Ritmo */}
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
            <span className="text-[10px] text-slate-500">Padrão: 15.0 min/CC para qualificar como jogo em ritmo ativo</span>
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

        {/* Janela de Minutos & Margem xG */}
        <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
          <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-emerald-400" />
            Janela de Minutos & Margem xG
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
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.1"
                min="0.2"
                max="3.0"
                value={rulesConfig.debtMarginXG}
                onChange={(e) => setRulesConfig({ ...rulesConfig, debtMarginXG: parseFloat(e.target.value) || 1.0 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
              <span className="text-xs text-slate-400 whitespace-nowrap">xG devidos</span>
            </div>
            <span className="text-[10px] text-slate-500">Padrão: 1.0 xG de atraso para confirmar dívida severa</span>
          </div>
        </div>
      </div>

      {/* 3. Parâmetros Específicos: Funil de Cantos & Under Value */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Funil de Cantos */}
        <div className="p-4 bg-slate-950/60 border border-teal-500/30 rounded-xl space-y-3">
          <h5 className="font-bold text-xs text-teal-300 uppercase tracking-wider flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-teal-400" />
            Parâmetros do Funil de Cantos
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Min. Cantos HT</label>
              <input
                type="number"
                min="1"
                max="10"
                value={rulesConfig.funilCantosMinCornersHt || 2}
                onChange={(e) => setRulesConfig({ ...rulesConfig, funilCantosMinCornersHt: parseInt(e.target.value) || 2 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Min. Cantos FT</label>
              <input
                type="number"
                min="3"
                max="20"
                value={rulesConfig.funilCantosMinCornersFt || 5}
                onChange={(e) => setRulesConfig({ ...rulesConfig, funilCantosMinCornersFt: parseInt(e.target.value) || 5 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
          </div>
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Máx. Min/Canto</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.5"
                min="5"
                max="30"
                value={rulesConfig.funilCantosMaxMinPerCorner || 14.0}
                onChange={(e) => setRulesConfig({ ...rulesConfig, funilCantosMaxMinPerCorner: parseFloat(e.target.value) || 14.0 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
              <span className="text-xs text-slate-400">min/canto</span>
            </div>
          </div>
        </div>

        {/* Under Value */}
        <div className="p-4 bg-slate-950/60 border border-indigo-500/30 rounded-xl space-y-3">
          <h5 className="font-bold text-xs text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
            Parâmetros do Under Value / Lay
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Minuto Inicial</label>
              <input
                type="number"
                min="10"
                max="60"
                value={rulesConfig.underValueMinMinute || 25}
                onChange={(e) => setRulesConfig({ ...rulesConfig, underValueMinMinute: parseInt(e.target.value) || 25 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Minuto Final</label>
              <input
                type="number"
                min="60"
                max="90"
                value={rulesConfig.underValueMaxMinute || 78}
                onChange={(e) => setRulesConfig({ ...rulesConfig, underValueMaxMinute: parseInt(e.target.value) || 78 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">xG Máximo</label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="2.0"
                value={rulesConfig.underValueMaxXg || 0.60}
                onChange={(e) => setRulesConfig({ ...rulesConfig, underValueMaxXg: parseFloat(e.target.value) || 0.60 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Chutes no Gol Máx.</label>
              <input
                type="number"
                min="0"
                max="5"
                value={rulesConfig.underValueMaxSot || 2}
                onChange={(e) => setRulesConfig({ ...rulesConfig, underValueMaxSot: parseInt(e.target.value) || 2 })}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 4. Módulos de Regras Operacionais do Terminal Python */}
      <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-4">
        <div className="flex items-center justify-between">
          <h5 className="font-bold text-xs text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-amber-400" />
            Módulos de Regras Operacionais do Terminal Python (14 Estratégias)
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

      {/* 5. Metodologia & Fórmulas Matemáticas de Diagnóstico */}
      <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
        <button
          onClick={() => setShowFormulas(!showFormulas)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-amber-400" />
            <span className="font-bold text-xs text-white uppercase tracking-wider">
              Metodologia & Fórmulas Matemáticas de Diagnóstico
            </span>
          </div>
          {showFormulas ? (
            <ChevronUp className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          )}
        </button>

        {showFormulas && (
          <div className="space-y-3 pt-2 text-xs text-slate-300 border-t border-slate-800/80 animate-in fade-in">
            <div className="p-3 bg-slate-900 rounded-xl space-y-1">
              <span className="font-bold text-amber-400 block">1. Saldo de Dívida de Gols</span>
              <p className="text-slate-400">
                Calcula o déficit estatístico entre as Chances Claras produzidas e os gols marcados no placar real.
              </p>
              <code className="block bg-slate-950 p-2 rounded text-[11px] font-mono text-emerald-300">
                Saldo = (Chances Claras / Ratio) - Gols Marcados
              </code>
            </div>

            <div className="p-3 bg-slate-900 rounded-xl space-y-1">
              <span className="font-bold text-cyan-400 block">2. Taxa de Ritmo Operacional</span>
              <p className="text-slate-400">
                Mede a frequência temporal de criação de perigo real pela equipe. Quanto menor o número, maior a agressividade.
              </p>
              <code className="block bg-slate-950 p-2 rounded text-[11px] font-mono text-cyan-300">
                Taxa de Ritmo = Minuto Atual / Chances Claras
              </code>
            </div>

            <div className="p-3 bg-slate-900 rounded-xl space-y-1">
              <span className="font-bold text-purple-400 block">3. Trinca de Dívidas (CC + xG + xGOT)</span>
              <p className="text-slate-400">
                O gatilho mais confiável do mercado: convergência de 3 métricas em atraso (Chances Claras ≥ 2.0 dívida, xG Total ≥ 1.0 dívida e xGOT no alvo).
              </p>
            </div>

            <div className="p-3 bg-slate-900 rounded-xl space-y-1">
              <span className="font-bold text-yellow-400 block">4. Pressão Vendável</span>
              <p className="text-slate-400">
                Detecta situações onde a pressão no campo de ataque é dominante (Índice de Pressão ≥ 75% ou Diferencial de Pressão ≥ 40%), configurando ineficiência defensiva iminente.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
