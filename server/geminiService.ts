import { GoogleGenAI, Type } from "@google/genai";
import { Match, TacticalAnalysis } from "../src/types";

let aiClient: GoogleGenAI | null = null;

function getAiClient(): GoogleGenAI {
  if (!aiClient) {
    aiClient = new GoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY,
      httpOptions: {
        headers: {
          "User-Agent": "aistudio-build",
        },
      },
    });
  }
  return aiClient;
}

export async function generateTacticalAnalysis(match: Match): Promise<TacticalAnalysis> {
  const prompt = `Você é um analista tático sênior de futebol e especialista em análise de momentum e trading esportivo ao vivo.
Analise a partida atual com base nos dados estatísticos e de pressão em tempo real:

Jogo: ${match.homeTeam.name} vs ${match.awayTeam.name} (${match.league})
Placar: ${match.score.home} x ${match.score.away} | Minuto: ${match.minute}' (${match.status})
Posse de Bola: ${match.stats.possession.home}% vs ${match.stats.possession.away}%
xG (Gols Esperados): ${match.stats.xG.home.toFixed(2)} vs ${match.stats.xG.away.toFixed(2)}
Finalizações no Gol: ${match.stats.shotsOnTarget.home} vs ${match.stats.shotsOnTarget.away} (Fora: ${match.stats.shotsOffTarget.home} vs ${match.stats.shotsOffTarget.away})
Ataques Perigosos: ${match.stats.dangerousAttacks.home} vs ${match.stats.dangerousAttacks.away}
Ataques Perigosos últimos 10min: ${match.stats.dangerousAttacksLast10.home} vs ${match.stats.dangerousAttacksLast10.away}
Escanteios: ${match.stats.corners.home} vs ${match.stats.corners.away}
Cartões: Amarelos (${match.stats.yellowCards.home} vs ${match.stats.yellowCards.away}), Vermelhos (${match.stats.redCards.home} vs ${match.stats.redCards.away})
Índice de Pressão Atual (0-100): ${match.stats.pressureIndex.home} vs ${match.stats.pressureIndex.away}
Últimos Eventos: ${match.events.slice(-4).map(e => `${e.minute}' [${e.type}] ${e.team === 'home' ? match.homeTeam.name : match.awayTeam.name} ${e.player || ''}`).join(', ')}

Forneça um diagnóstico tático aprofundado e prático em Português do Brasil com recomendações analíticas sobre o fluxo do jogo, tendências de gols, escanteios e cartões.`;

  try {
    const ai = getAiClient();
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            summary: {
              type: Type.STRING,
              description: "Resumo conciso de 2 a 3 frases sobre o panorama atual do confronto e dinâmica de jogo.",
            },
            momentumVerdict: {
              type: Type.STRING,
              enum: ["home_dominant", "away_dominant", "balanced", "end_to_end"],
              description: "Veredito sobre o domínio da partida.",
            },
            likelyNextEvent: {
              type: Type.STRING,
              description: "Evento mais provável nos próximos 10-15 minutos (ex: 'Gol do time da casa por blitz ofensiva', 'Pressão de escanteios').",
            },
            nextGoalProbability: {
              type: Type.OBJECT,
              properties: {
                home: { type: Type.NUMBER, description: "Probabilidade percentual estimada de 0 a 100 de o mandante marcar o próximo gol" },
                away: { type: Type.NUMBER, description: "Probabilidade percentual estimada de 0 a 100 de o visitante marcar o próximo gol" },
                noGoal: { type: Type.NUMBER, description: "Probabilidade percentual estimada de 0 a 100 de não haver mais gols" },
              },
              required: ["home", "away", "noGoal"],
            },
            keyInsights: {
              type: Type.ARRAY,
              items: { type: Type.STRING },
              description: "3 a 4 insights táticos específicos baseados nos dados de xG, finalizações e ataques perigosos.",
            },
            cornerPressureScore: {
              type: Type.NUMBER,
              description: "Índice de 0 a 100 para tendência iminente de escanteios.",
            },
            cardRiskScore: {
              type: Type.NUMBER,
              description: "Índice de 0 a 100 de risco de novos cartões/expulsões devido à temperatura do jogo.",
            },
            tradingAngles: {
              type: Type.ARRAY,
              items: { type: Type.STRING },
              description: "2 a 3 ângulos estatísticos de valor (ex: 'Over 1.5 Gols', 'Pressão de Cantos FT', 'Underdog value').",
            },
          },
          required: [
            "summary",
            "momentumVerdict",
            "likelyNextEvent",
            "nextGoalProbability",
            "keyInsights",
            "cornerPressureScore",
            "cardRiskScore",
            "tradingAngles",
          ],
        },
      },
    });

    const parsed = JSON.parse(response.text?.trim() || "{}");
    return {
      matchId: match.id,
      summary: parsed.summary || "Análise concluída com base nas métricas ao vivo.",
      momentumVerdict: parsed.momentumVerdict || "balanced",
      likelyNextEvent: parsed.likelyNextEvent || "Disputa acirrada no meio-campo.",
      nextGoalProbability: parsed.nextGoalProbability || { home: 40, away: 30, noGoal: 30 },
      keyInsights: parsed.keyInsights || [
        "Equipe mandante mantendo alto volume no terço final.",
        "Transições rápidas do time visitante gerando contragolpes perigosos.",
      ],
      cornerPressureScore: parsed.cornerPressureScore || 65,
      cardRiskScore: parsed.cardRiskScore || 45,
      tradingAngles: parsed.tradingAngles || ["Acompanhar linha de escanteios asiáticos."],
      analyzedAt: new Date().toISOString(),
    };
  } catch (err) {
    console.error("Erro ao gerar análise com Gemini:", err);
    // Fallback heurístico inteligente
    const homePressure = match.stats.pressureIndex.home;
    const awayPressure = match.stats.pressureIndex.away;
    const verdict = homePressure > 65 ? "home_dominant" : awayPressure > 65 ? "away_dominant" : "balanced";
    
    return {
      matchId: match.id,
      summary: `Partida no minuto ${match.minute}' com ${match.score.home} x ${match.score.away}. Índice de pressão indica ${verdict === 'home_dominant' ? 'domínio do mandante' : verdict === 'away_dominant' ? 'domínio do visitante' : 'jogo equilibrado'}.`,
      momentumVerdict: verdict,
      likelyNextEvent: homePressure > awayPressure ? `Pressão ofensiva do ${match.homeTeam.name}` : `Resistência defensiva e contra-ataques do ${match.awayTeam.name}`,
      nextGoalProbability: {
        home: Math.min(80, Math.max(10, Math.round(homePressure * 0.7))),
        away: Math.min(80, Math.max(10, Math.round(awayPressure * 0.7))),
        noGoal: Math.max(10, 100 - Math.round((homePressure + awayPressure) * 0.5)),
      },
      keyInsights: [
        `xG acumulado: ${match.homeTeam.shortName} (${match.stats.xG.home.toFixed(2)}) vs ${match.awayTeam.shortName} (${match.stats.xG.away.toFixed(2)})`,
        `Ataques perigosos últimos 10min: ${match.stats.dangerousAttacksLast10.home} x ${match.stats.dangerousAttacksLast10.away}`,
        `Total de finalizações no alvo: ${match.stats.shotsOnTarget.home + match.stats.shotsOnTarget.away}`,
      ],
      cornerPressureScore: Math.min(100, Math.round((match.stats.corners.home + match.stats.corners.away) * 8)),
      cardRiskScore: Math.min(100, Math.round((match.stats.yellowCards.home + match.stats.yellowCards.away) * 18)),
      tradingAngles: [
        `Métricas apontam ${match.stats.dangerousAttacks.home > match.stats.dangerousAttacks.away ? 'vantagem territorial de ' + match.homeTeam.name : 'equilíbrio com valor no empate'}`,
      ],
      analyzedAt: new Date().toISOString(),
    };
  }
}
