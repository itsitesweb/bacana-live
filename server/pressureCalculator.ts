import { MatchStats } from "../src/types";

/**
 * Calcula o Índice de Pressão Ofensiva em Tempo Real (0 a 100% para Mandante e Visitante)
 * baseado nas métricas dinâmicas do confronto:
 * - Ataques Perigosos e Ataques Perigosos nos últimos 10 minutos
 * - Finalizações no Alvo (peso alto) e Fora do Alvo
 * - Escanteios gerados
 * - Gols Esperados (xG)
 * - Posse de Bola territorial
 */
export function calculateDynamicPressureIndex(
  stats: Partial<MatchStats> | undefined,
  minute: number = 45
): { home: number; away: number } {
  if (!stats) {
    return { home: 50, away: 50 };
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

  // Se não há dados estatísticos relevantes no jogo (início de jogo ou sem dados de ataque)
  const totalActionPoints = dangH + dangA + sotH + sotA + cornH + cornA + soffH + soffA;
  if (totalActionPoints === 0) {
    // Usa posse como leve indicador inicial
    if (possH !== 50 || possA !== 50) {
      const pTotal = (possH + possA) || 100;
      return {
        home: Math.round((possH / pTotal) * 100),
        away: Math.round((possA / pTotal) * 100),
      };
    }
    return { home: 50, away: 50 };
  }

  // Ponderação matemática do momentum ofensivo:
  // - Ataques perigosos recentes (últimos 10 min): peso 3.0
  // - Ataques perigosos gerais: peso 1.2
  // - Finalizações certas (SOT): peso 3.5
  // - Finalizações fora: peso 1.2
  // - Escanteios: peso 2.0
  // - xG gerado: peso 10.0 por unidade (ex: 0.5 xG = 5.0 pts)
  // - Posse territorial: peso 0.25
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

  const totalScore = scoreHome + scoreAway;
  if (totalScore <= 0) {
    return { home: 50, away: 50 };
  }

  let pctHome = Math.round((scoreHome / totalScore) * 100);
  let pctAway = 100 - pctHome;

  // Limitar entre 5% e 95% para preservar legibilidade realista
  pctHome = Math.max(5, Math.min(95, pctHome));
  pctAway = 100 - pctHome;

  return { home: pctHome, away: pctAway };
}
