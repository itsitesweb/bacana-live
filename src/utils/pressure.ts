import { MatchStats, MomentumPoint } from "../types";

/**
 * Utilitário para cálculo e formatação do Índice de Pressão focado nos últimos 5 minutos (0 a 100%)
 */
export function getLivePressure5Min(
  stats: Partial<MatchStats> | undefined,
  minute: number = 45,
  momentumTimeline?: MomentumPoint[]
): { home: number; away: number; trend: "home" | "away" | "neutral"; dominanceText: string } {
  if (!stats) {
    return { home: 50, away: 50, trend: "neutral", dominanceText: "Jogo Equilibrado (5m)" };
  }

  // 1. Se houver pontos no momentumTimeline nos últimos 5 minutos, calcula a média ponderada estrita de 5m
  if (momentumTimeline && Array.isArray(momentumTimeline) && momentumTimeline.length > 0) {
    const curMin = minute > 0 ? minute : (momentumTimeline[momentumTimeline.length - 1]?.minute || 45);
    const last5Points = momentumTimeline.filter(
      (pt) => pt.minute >= Math.max(1, curMin - 5) && pt.minute <= curMin
    );

    if (last5Points.length > 0) {
      let sumHome = 0;
      let sumAway = 0;
      let count = 0;

      last5Points.forEach((pt, idx) => {
        // Pontos mais recentes têm maior peso temporal
        const weight = 1 + idx * 0.3;
        const hPress = pt.homePressure ?? 50;
        const aPress = pt.awayPressure ?? 50;

        // Bônus para eventos recentes de perigo no minuto
        const dangerBonusHome = (pt.homeDangerousAttack ? 15 : 0) + (pt.homeShot ? 25 : 0);
        const dangerBonusAway = (pt.awayDangerousAttack ? 15 : 0) + (pt.awayShot ? 25 : 0);

        sumHome += (hPress + dangerBonusHome) * weight;
        sumAway += (aPress + dangerBonusAway) * weight;
        count += weight;
      });

      const avgHome = sumHome / (count || 1);
      const avgAway = sumAway / (count || 1);
      const total = avgHome + avgAway;

      if (total > 0) {
        let pctH = Math.round((avgHome / total) * 100);
        pctH = Math.max(5, Math.min(95, pctH));
        const pctA = 100 - pctH;

        let trend: "home" | "away" | "neutral" = "neutral";
        let dominanceText = "Pressão Equilibrada (5m)";
        if (pctH >= 70) {
          trend = "home";
          dominanceText = "Blitz Ofensiva Mandante (5m)";
        } else if (pctH >= 60) {
          trend = "home";
          dominanceText = "Pressão Mandante (5m)";
        } else if (pctA >= 70) {
          trend = "away";
          dominanceText = "Blitz Ofensiva Visitante (5m)";
        } else if (pctA >= 60) {
          trend = "away";
          dominanceText = "Pressão Visitante (5m)";
        }

        return { home: pctH, away: pctA, trend, dominanceText };
      }
    }
  }

  // 2. Estimativa heurística calibrada para a janela de 5 minutos baseada no ritmo recente
  const dang10H = Number(stats.dangerousAttacksLast10?.home || 0);
  const dang10A = Number(stats.dangerousAttacksLast10?.away || 0);
  const apm10H = Number(stats.apmLast10?.home || (dang10H / 10));
  const apm10A = Number(stats.apmLast10?.away || (dang10A / 10));
  const sotH = Number(stats.shotsOnTarget?.home || 0);
  const sotA = Number(stats.shotsOnTarget?.away || 0);
  const cornH = Number(stats.corners?.home || 0);
  const cornA = Number(stats.corners?.away || 0);
  const xgH = Number(stats.xG?.home || 0);
  const xgA = Number(stats.xG?.away || 0);
  const possH = Number(stats.possession?.home ?? 50);
  const possA = Number(stats.possession?.away ?? 50);

  // Considera ataques por minuto e finalizações recentes
  const score5mHome =
    (apm10H * 5.0 * 8.0) +
    (dang10H * 4.5) +
    (sotH * 3.0) +
    (cornH * 2.0) +
    (xgH * 8.0) +
    (possH * 0.3);

  const score5mAway =
    (apm10A * 5.0 * 8.0) +
    (dang10A * 4.5) +
    (sotA * 3.0) +
    (cornA * 2.0) +
    (xgA * 8.0) +
    (possA * 0.3);

  const total = score5mHome + score5mAway;
  if (total <= 0) {
    return { home: 50, away: 50, trend: "neutral", dominanceText: "Ritmo Neutro (5m)" };
  }

  let pctH = Math.round((score5mHome / total) * 100);
  pctH = Math.max(5, Math.min(95, pctH));
  const pctA = 100 - pctH;

  let trend: "home" | "away" | "neutral" = "neutral";
  let dominanceText = "Ritmo Equilibrado (5m)";
  if (pctH >= 68) {
    trend = "home";
    dominanceText = "Blitz Ofensiva Mandante (5m)";
  } else if (pctH >= 58) {
    trend = "home";
    dominanceText = "Pressão Mandante (5m)";
  } else if (pctA >= 68) {
    trend = "away";
    dominanceText = "Blitz Ofensiva Visitante (5m)";
  } else if (pctA >= 58) {
    trend = "away";
    dominanceText = "Pressão Visitante (5m)";
  }

  return { home: pctH, away: pctA, trend, dominanceText };
}

/**
 * Utilitário para cálculo e formatação do Índice de Pressão Geral da partida
 */
export function getLivePressure(
  stats: Partial<MatchStats> | undefined,
  minute: number = 45
): { home: number; away: number } {
  if (!stats) {
    return { home: 50, away: 50 };
  }

  const existingH = stats.pressureIndex?.home;
  const existingA = stats.pressureIndex?.away;
  if (typeof existingH === "number" && typeof existingA === "number" && (existingH !== 50 || existingA !== 50)) {
    return { home: existingH, away: existingA };
  }

  const dangH = Number(stats.dangerousAttacks?.home || 0);
  const dangA = Number(stats.dangerousAttacks?.away || 0);
  const dang10H = Number(stats.dangerousAttacksLast10?.home || 0);
  const dang10A = Number(stats.dangerousAttacksLast10?.away || 0);
  const sotH = Number(stats.shotsOnTarget?.home || 0);
  const sotA = Number(stats.shotsOnTarget?.away || 0);
  const soffH = Number(stats.shotsOffTarget?.home || 0);
  const soffA = Number(stats.shotsOffTarget?.away || 0);
  const cornH = Number(stats.corners?.home || 0);
  const cornA = Number(stats.corners?.away || 0);
  const xgH = Number(stats.xG?.home || 0);
  const xgA = Number(stats.xG?.away || 0);
  const possH = Number(stats.possession?.home ?? 50);
  const possA = Number(stats.possession?.away ?? 50);

  const totalPoints = dangH + dangA + sotH + sotA + cornH + cornA + soffH + soffA;
  if (totalPoints === 0) {
    if (possH !== 50 || possA !== 50) {
      const pTot = (possH + possA) || 100;
      return {
        home: Math.round((possH / pTot) * 100),
        away: Math.round((possA / pTot) * 100),
      };
    }
    return { home: 50, away: 50 };
  }

  const scoreHome =
    (dang10H * 3.0) +
    (dangH * 1.2) +
    (sotH * 3.5) +
    (soffH * 1.2) +
    (cornH * 2.0) +
    (xgH * 10.0) +
    (possH * 0.25);

  const scoreAway =
    (dang10A * 3.0) +
    (dangA * 1.2) +
    (sotA * 3.5) +
    (soffA * 1.2) +
    (cornA * 2.0) +
    (xgA * 10.0) +
    (possA * 0.25);

  const total = scoreHome + scoreAway;
  if (total <= 0) return { home: 50, away: 50 };

  let pctHome = Math.round((scoreHome / total) * 100);
  pctHome = Math.max(5, Math.min(95, pctHome));
  const pctAway = 100 - pctHome;

  return { home: pctHome, away: pctAway };
}

