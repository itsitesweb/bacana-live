import React from "react";
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  Tooltip,
} from "recharts";
import { Match } from "../types";
import { Compass, Flame, Shield, Award } from "lucide-react";

interface PitchRadarVisualizerProps {
  match: Match;
}

export function PitchRadarVisualizer({ match }: PitchRadarVisualizerProps) {
  // Normalize radar values to 0-100 scale for balanced polygon comparison
  const stats = match.stats;

  const radarData = [
    {
      metric: "Posse de Bola",
      Home: stats.possession.home,
      Away: stats.possession.away,
      fullMark: 100,
    },
    {
      metric: "Ataques Perig.",
      Home: Math.min(100, (stats.dangerousAttacks.home / 70) * 100),
      Away: Math.min(100, (stats.dangerousAttacks.away / 70) * 100),
      rawHome: stats.dangerousAttacks.home,
      rawAway: stats.dangerousAttacks.away,
      fullMark: 100,
    },
    {
      metric: "Chutes no Gol",
      Home: Math.min(100, (stats.shotsOnTarget.home / 12) * 100),
      Away: Math.min(100, (stats.shotsOnTarget.away / 12) * 100),
      rawHome: stats.shotsOnTarget.home,
      rawAway: stats.shotsOnTarget.away,
      fullMark: 100,
    },
    {
      metric: "Escanteios",
      Home: Math.min(100, (stats.corners.home / 14) * 100),
      Away: Math.min(100, (stats.corners.away / 14) * 100),
      rawHome: stats.corners.home,
      rawAway: stats.corners.away,
      fullMark: 100,
    },
    {
      metric: "xG Gols Esp.",
      Home: Math.min(100, (stats.xG.home / 3.0) * 100),
      Away: Math.min(100, (stats.xG.away / 3.0) * 100),
      rawHome: stats.xG.home.toFixed(2),
      rawAway: stats.xG.away.toFixed(2),
      fullMark: 100,
    },
    {
      metric: "Pressão Terço",
      Home: stats.pressureIndex.home,
      Away: stats.pressureIndex.away,
      fullMark: 100,
    },
  ];

  // Calculate territorial momentum bias for 2D Pitch
  const homeDominance = stats.pressureIndex.home;
  const awayDominance = stats.pressureIndex.away;
  const totalPress = homeDominance + awayDominance || 1;
  const homePct = Math.round((homeDominance / totalPress) * 100);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* 2D Interactive Pitch Visualization */}
      <div className="lg:col-span-6 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Compass className="w-5 h-5 text-emerald-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Ocupação Territorial & Terço Ofensivo
              </h3>
            </div>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              Campo 2D Ao Vivo
            </span>
          </div>

          <p className="text-xs text-slate-400 mb-4">
            Mapeamento dinâmico de zonas de perigo e tendências de transição ofensiva.
          </p>
        </div>

        {/* Tactical Pitch Visual Canvas */}
        <div className="relative w-full aspect-[16/10] bg-emerald-950/60 rounded-xl border-2 border-emerald-700/60 overflow-hidden shadow-inner flex items-center justify-center">
          {/* Pitch lines */}
          <div className="absolute inset-0 grid grid-cols-6 opacity-20 pointer-events-none">
            <div className="bg-emerald-900/40"></div>
            <div className="bg-emerald-800/40"></div>
            <div className="bg-emerald-900/40"></div>
            <div className="bg-emerald-800/40"></div>
            <div className="bg-emerald-900/40"></div>
            <div className="bg-emerald-800/40"></div>
          </div>

          {/* Center line and circle */}
          <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-emerald-400/40 transform -translate-x-1/2"></div>
          <div className="absolute top-1/2 left-1/2 w-20 h-20 rounded-full border border-emerald-400/40 transform -translate-x-1/2 -translate-y-1/2"></div>
          <div className="absolute top-1/2 left-1/2 w-1.5 h-1.5 rounded-full bg-emerald-400/70 transform -translate-x-1/2 -translate-y-1/2"></div>

          {/* Left Penalty Box (Home Defense / Away Attack Target) */}
          <div className="absolute left-0 top-1/4 bottom-1/4 w-20 border-r border-t border-b border-emerald-400/40 bg-emerald-950/40"></div>
          <div className="absolute left-0 top-1/3 bottom-1/3 w-8 border-r border-t border-b border-emerald-400/40"></div>
          <div className="absolute left-14 top-1/2 w-1 h-1 rounded-full bg-emerald-400/60 -translate-y-1/2"></div>

          {/* Right Penalty Box (Away Defense / Home Attack Target) */}
          <div className="absolute right-0 top-1/4 bottom-1/4 w-20 border-l border-t border-b border-emerald-400/40 bg-emerald-950/40"></div>
          <div className="absolute right-0 top-1/3 bottom-1/3 w-8 border-l border-t border-b border-emerald-400/40"></div>
          <div className="absolute right-14 top-1/2 w-1 h-1 rounded-full bg-emerald-400/60 -translate-y-1/2"></div>

          {/* Live Heat Zones Gradient depending on pressure */}
          <div
            className="absolute inset-0 pointer-events-none transition-all duration-700 opacity-60"
            style={{
              background: `radial-gradient(ellipse at ${homePct > 55 ? "75% 50%" : "25% 50%"}, ${
                homePct > 55 ? "rgba(16, 185, 129, 0.45)" : "rgba(6, 182, 212, 0.45)"
              } 0%, transparent 65%)`,
            }}
          />

          {/* Dynamic Action Center / Ball Location Indicator */}
          <div
            className="absolute top-1/2 -translate-y-1/2 transition-all duration-700 z-10 flex flex-col items-center"
            style={{ left: `${Math.min(85, Math.max(15, homePct))}%` }}
          >
            <div className="relative">
              <div className="w-5 h-5 rounded-full bg-amber-400 text-slate-950 font-extrabold flex items-center justify-center text-[10px] shadow-lg shadow-amber-500/50 animate-pulse">
                ⚽
              </div>
              <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-bold text-amber-300 bg-slate-950/90 px-1.5 py-0.5 rounded border border-amber-400/30 whitespace-nowrap">
                {homePct > 50 ? `${match.homeTeam.shortName} Ataque` : `${match.awayTeam.shortName} Ataque`}
              </span>
            </div>
          </div>

          {/* Team side banners */}
          <div className="absolute top-2 left-3 text-xs font-bold text-emerald-300 bg-slate-950/80 px-2 py-0.5 rounded border border-emerald-600/30 flex items-center gap-1">
            <span>{match.homeTeam.logo}</span>
            <span>{match.homeTeam.shortName}</span>
          </div>

          <div className="absolute top-2 right-3 text-xs font-bold text-cyan-300 bg-slate-950/80 px-2 py-0.5 rounded border border-cyan-600/30 flex items-center gap-1">
            <span>{match.awayTeam.shortName}</span>
            <span>{match.awayTeam.logo}</span>
          </div>
        </div>

        {/* Territorial Pressure Stats Footer */}
        <div className="grid grid-cols-3 gap-2 mt-4 text-center">
          <div className="bg-slate-950/70 p-2 rounded-xl border border-slate-800">
            <span className="text-[10px] text-slate-400 block font-medium">Terço Defensivo</span>
            <span className="text-xs font-bold text-slate-200">{100 - homePct}%</span>
          </div>
          <div className="bg-slate-950/70 p-2 rounded-xl border border-slate-800">
            <span className="text-[10px] text-slate-400 block font-medium">Meio-Campo</span>
            <span className="text-xs font-bold text-emerald-400">{stats.possession.home}% vs {stats.possession.away}%</span>
          </div>
          <div className="bg-slate-950/70 p-2 rounded-xl border border-slate-800">
            <span className="text-[10px] text-slate-400 block font-medium">Terço Ofensivo</span>
            <span className="text-xs font-bold text-emerald-400">{homePct}%</span>
          </div>
        </div>
      </div>

      {/* Radar Matrix Comparison */}
      <div className="lg:col-span-6 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Award className="w-5 h-5 text-cyan-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Matriz Comparativa Multidimensional
              </h3>
            </div>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
              Radar de Performance
            </span>
          </div>
          <p className="text-xs text-slate-400 mb-2">
            Equilíbrio de atributos técnicos e ofensivos padronizados em escala percentual.
          </p>
        </div>

        {/* Radar Chart */}
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart cx="50%" cy="50%" outerRadius="75%" data={radarData}>
              <PolarGrid stroke="#334155" />
              <PolarAngleAxis dataKey="metric" stroke="#94A3B8" fontSize={10} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} stroke="#475569" fontSize={9} />

              <Radar
                name={match.homeTeam.name}
                dataKey="Home"
                stroke="#10B981"
                fill="#10B981"
                fillOpacity={0.4}
              />
              <Radar
                name={match.awayTeam.name}
                dataKey="Away"
                stroke="#06B6D4"
                fill="#06B6D4"
                fillOpacity={0.35}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }}
                formatter={(value) => <span className="text-slate-300 font-medium">{value}</span>}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const item = payload[0].payload;
                    return (
                      <div className="bg-slate-950 border border-slate-700 p-2.5 rounded-xl shadow-xl text-xs space-y-1">
                        <span className="font-bold text-white block border-b border-slate-800 pb-1">
                          {item.metric}
                        </span>
                        <div className="flex justify-between text-emerald-400 gap-4">
                          <span>{match.homeTeam.name}:</span>
                          <span className="font-bold">{item.rawHome ?? `${Math.round(item.Home)}%`}</span>
                        </div>
                        <div className="flex justify-between text-cyan-400 gap-4">
                          <span>{match.awayTeam.name}:</span>
                          <span className="font-bold">{item.rawAway ?? `${Math.round(item.Away)}%`}</span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
