import {
  Match,
  OperationalRulesConfig,
  Codigo31Evaluation,
  Codigo31AlertType,
  TripleDebtEvaluation,
  PressaoVendavelEvaluation,
  DominantTrailingEvaluation,
  ImminentGoalEvaluation,
  FunilCantosEvaluation,
  RaceToCornersEvaluation,
  JogoQuenteEvaluation,
  RiscoExpulsaoEvaluation,
  AmbasMarcamEvaluation,
  UnderValueEvaluation,
  ViradaImprovavelEvaluation,
  CashoutProativoEvaluation,
  TraditionalRuleSignal,
  MatchRulesAnalysis,
  BettingTipData,
  BookmakerOdd,
  AVAILABLE_BOOKMAKERS,
  DEFAULT_BOOKMAKER_CREDENTIALS,
} from "../src/types";

// Default operational rules configuration
export const DEFAULT_RULES_CONFIG: OperationalRulesConfig = {
  chancesPerGoalRatio: 3.0, // Regra 3:1 (3 chances claras para 1 gol esperado)
  ccRateMaxMinutes: 15.0, // Máximo 15 min/CC
  ccRateForteMaxMinutes: 12.0, // Máximo 12 min/CC para Forte/Premium
  debtMarginXG: 1.0, // Dívida xG/xGOT (gols + 1.0)
  imminentGoalThresholdPct: 50, // Limiar padrão de variação nos últimos 5 min
  minAlertProbabilityPct: 50, // Faixa mínima de probabilidade para disparar alerta (%)
  maxAlertProbabilityPct: 100, // Faixa máxima de probabilidade para disparar alerta (%)
  enableCodigo31: true,
  enableTripleDebt: true,
  enablePressaoVendavel: true,
  enableDominantTrailing: true,
  enableV12OverBack: true,
  enableImminentGoal: true,
  // Novas Estratégias de Trade Esportivo
  enableFunilCantos: true,
  enableRaceToCorners: true,
  enableJogoQuenteCards: true,
  enableRiscoExpulsao: true,
  enableAmbasMarcamBTTS: true,
  enableUnderValue: true,
  enableViradaImprovavel: true,
  enableCashoutProativo: true,
  // Configurações Específicas do Under Value
  underValueMinMinute: 25,
  underValueMaxMinute: 78,
  underValueMaxXg: 0.60,
  underValueMaxSot: 2,
  // Configurações Específicas do Funil de Cantos
  funilCantosMinCornersHt: 2,
  funilCantosMinCornersFt: 5,
  funilCantosMaxMinPerCorner: 14,
  enabledBookmakers: ['bet365', 'betfair', 'pinnacle', 'betano', 'esportivabet', 'sportingbet', 'kto', 'superbet', '1xbet'],
  bookmakerCredentials: { ...DEFAULT_BOOKMAKER_CREDENTIALS },
  crawlerConfig: {
    maxWatchlistSize: 15,
    tier3ReservedSlots: 2,
    discoveryIntervalSeconds: 180,
    concurrentWorkers: 4,
    routeResourceBlock: true,
    enableBackgroundDiscovery: true,
    autoPruneMinutes: 30,
    noStatsBackoffMinutes: 10,
    minEntryMinute: 20,
    maxEntryMinute: 83,
    antiSpamCooldownMinutes: 5,
    tierFilter: {
      enableTier0Signals: true,
      enableTier05PremiumLeagues: true,
      enableTier12Window: true,
      enableTier3Rotation: true,
    },
  },
  soundAlertsEnabled: true,
  minMinuteAlert: 15,
  maxMinuteAlert: 85,
};

// ──────────────────────────────────────────────────────────────────────────
// GERADOR DE ODDS DAS CASAS E DICAS DE TRADING (+EV & PROBABILIDADES)
// ──────────────────────────────────────────────────────────────────────────
export function generateBettingTip(params: {
  marketCode: string;
  marketName: string;
  targetSelection: string;
  probabilityPct: number;
  confidence: 'extrema' | 'alta' | 'moderada';
  reasoning: string;
  actionText: string;
  match: Match;
  config?: OperationalRulesConfig;
}): BettingTipData {
  const prob = Math.max(12, Math.min(96, Math.round(params.probabilityPct)));
  const fairOdd = Number((100 / prob).toFixed(2));
  
  // Determine allowed bookmakers based on operational config
  let allowedBookmakerIds: Set<string> | null = null;
  if (params.config?.bookmakerCredentials) {
    const active = Object.entries(params.config.bookmakerCredentials)
      .filter(([_, cred]) => cred && cred.enabled !== false)
      .map(([id]) => id);
    allowedBookmakerIds = new Set(active);
  } else if (Array.isArray(params.config?.enabledBookmakers)) {
    allowedBookmakerIds = new Set(params.config.enabledBookmakers);
  }

  const bookmakersToUse = allowedBookmakerIds
    ? AVAILABLE_BOOKMAKERS.filter((bk) => allowedBookmakerIds!.has(bk.id))
    : AVAILABLE_BOOKMAKERS;

  // Real market baseline odd if provided by match feed
  let realMarketBaselineOdd: number | null = null;
  if (params.match.odds) {
    if (params.marketCode.startsWith("OVER_GOL") || params.marketCode === "OVER_PREMIUM") {
      realMarketBaselineOdd = params.match.odds.over25 || null;
    } else if (params.marketCode === "UNDER_VALUE") {
      realMarketBaselineOdd = params.match.odds.under25 || null;
    } else if (params.marketCode === "BTTS_YES") {
      realMarketBaselineOdd = params.match.odds.bttsYes || null;
    } else if (params.marketCode.startsWith("BACK_MANDANTE") || params.targetSelection.includes(params.match.homeTeam.name)) {
      realMarketBaselineOdd = params.match.odds.homeWin || null;
    } else if (params.marketCode.startsWith("BACK_VISITANTE") || params.targetSelection.includes(params.match.awayTeam.name)) {
      realMarketBaselineOdd = params.match.odds.awayWin || null;
    } else if (params.marketCode === "FUNIL_CANTOS" || params.marketCode === "RACE_CORNERS") {
      realMarketBaselineOdd = params.match.odds.cornerOver95 || null;
    }
  }

  const baseOddForBooks = realMarketBaselineOdd && realMarketBaselineOdd > 1.05
    ? realMarketBaselineOdd
    : fairOdd;

  // Seed determinístico baseado no tempo e placar para manter consistência
  const seed = (Math.floor(params.match.minute || 1) * 17 + ((params.match.score?.home || 0) * 7 + (params.match.score?.away || 0) * 11) + params.marketCode.length * 3) % 100;
  
  const bookmakerOdds: BookmakerOdd[] = bookmakersToUse.map((bk, idx) => {
    // Sharp books (Pinnacle/Betfair Exchange) têm menor margem de vig e odds mais altas
    const variation = ((seed + idx * 13) % 11 - 5) / 100; // -5% a +5%
    let multiplier = 1.0;
    if (bk.type === 'exchange') multiplier = 1.03;
    else if (bk.type === 'sharp') multiplier = 1.015;
    else multiplier = (100 - (bk.marginPct || 4.5)) / 100;

    let computedOdd = Number((baseOddForBooks * multiplier * (1 + variation * 0.4)).toFixed(2));
    computedOdd = Math.max(1.05, computedOdd);
    return {
      bookmakerId: bk.id,
      name: bk.name,
      shortName: bk.shortName,
      odd: computedOdd,
      marketLabel: params.targetSelection,
    };
  });

  // Identifica a melhor odd entre as casas ativas
  let maxOdd = bookmakerOdds.length > 0 ? Math.max(...bookmakerOdds.map((b) => b.odd)) : fairOdd;
  bookmakerOdds.forEach((b) => {
    b.isBest = b.odd === maxOdd;
  });

  const edgePct = Number((((maxOdd - fairOdd) / fairOdd) * 100).toFixed(1));
  const evStatus = edgePct >= 1.5 ? '+EV' : edgePct < -4.0 ? 'ALERTA' : 'NEUTRO';

  return {
    marketCode: params.marketCode,
    marketName: params.marketName,
    targetSelection: params.targetSelection,
    probabilityPct: prob,
    fairOdd,
    confidence: params.confidence,
    evStatus,
    edgePct,
    bookmakerOdds,
    reasoning: params.reasoning,
    actionText: params.actionText,
  };
}

// Titles and messages mapping from Python codigo_3_1.py
export const ALERT_DISPLAY_MAP: Record<Codigo31AlertType, { emoji: string; label: string }> = {
  over_bilateral_premium: { emoji: "🟢", label: "PREMIUM 3.1.2 — OVER BILATERAL PESADO" },
  over_premium_xg:        { emoji: "🟢", label: "PREMIUM 3.1.2 — CC + xG CONFIRMADOS" },
  over_premium:           { emoji: "🟢", label: "PREMIUM 3.1.2 — GOL MUITO DEVENDO" },
  back_premium:           { emoji: "🟢", label: "PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO" },
  over_forte:             { emoji: "🟠", label: "FORTE 3.1.2 — GOL DEVENDO" },
  back_forte:             { emoji: "🟠", label: "FORTE 3.1.2 — BACK DOMINANTE" },
  over_watch:             { emoji: "📡", label: "WATCH 3.1.2 — RADAR DE GOL" },
  back_watch:             { emoji: "📡", label: "WATCH 3.1.2 — RADAR DE BACK DOMINANTE" },
};

export const MESSAGE_TEMPLATES_MAP: Record<Codigo31AlertType, { motivo: string; leitura: string }> = {
  over_watch: {
    motivo: "Produção suficiente para gol, mas o placar ainda não pagou.",
    leitura: "Radar ativo. Não é entrada automática. Aguardar nova CC ou evolução para FORTE/PREMIUM.",
  },
  over_forte: {
    motivo: "Produção ofensiva forte, rate qualificado e placar abaixo da produção.",
    leitura: "Sinal operacional. Avaliar entrada em gol/Over conforme odd e contexto.",
  },
  over_premium: {
    motivo: "Volume alto de chances claras e placar claramente atrasado.",
    leitura: "Sinal premium de gol atrasado. Prioridade alta para análise de entrada.",
  },
  over_premium_xg: {
    motivo: "Chances claras e xG confirmam alta produção ofensiva com placar abaixo.",
    leitura: "Sinal premium confirmado por duas métricas. Prioridade máxima.",
  },
  over_bilateral_premium: {
    motivo: "Os dois times já criaram 3+ chances claras. Jogo aberto dos dois lados.",
    leitura: "Padrão forte para Over/BTTS. Não é sinal de Back; é sinal de jogo aberto.",
  },
  back_watch: {
    motivo: "Um time começou a abrir vantagem em chances claras, mas o placar ainda não refletiu.",
    leitura: "Radar ativo. Não é entrada automática. Aguardar confirmação de domínio para FORTE/PREMIUM.",
  },
  back_forte: {
    motivo: "Dominante tem vantagem clara em chances, mas o placar ainda não pagou essa produção.",
    leitura: "Sinal operacional para Back do dominante. Confirmar pressão atual antes da entrada.",
  },
  back_premium: {
    motivo: "Domínio extremo em chances claras, adversário sem produção relevante e placar contra a lógica do jogo.",
    leitura: "Sinal premium para reação do dominante. Prioridade alta.",
  },
};

const CODIGO_PRIORITY: Codigo31AlertType[] = [
  "over_bilateral_premium",
  "over_premium_xg",
  "over_premium",
  "back_premium",
  "over_forte",
  "back_forte",
  "over_watch",
  "back_watch",
];

// Helper to extract Big Chances (with fallback estimation if needed)
export function getMatchBigChances(match: Match): { home: number; away: number; total: number } {
  if (match.stats.bigChances) {
    const home = Math.max(0, Math.round(match.stats.bigChances.home || 0));
    const away = Math.max(0, Math.round(match.stats.bigChances.away || 0));
    return { home, away, total: home + away };
  }
  // Heuristic fallback if bigChances not yet populated: based on shots on target and xG
  const homeEst = Math.max(0, Math.floor((match.stats.shotsOnTarget.home * 0.4) + (match.stats.xG.home * 0.7)));
  const awayEst = Math.max(0, Math.floor((match.stats.shotsOnTarget.away * 0.4) + (match.stats.xG.away * 0.7)));
  return { home: homeEst, away: awayEst, total: homeEst + awayEst };
}

// ──────────────────────────────────────────────────────────────────────────
// 1. REGRA DIAGNÓSTICO (COM RATIO DINÂMICO AJUSTÁVEL)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateCodigo31(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): Codigo31Evaluation {
  const ratio = Math.max(1.0, config.chancesPerGoalRatio || 3.0);
  const bc = getMatchBigChances(match);
  const homeBc = bc.home;
  const awayBc = bc.away;
  const totalCc = bc.total;

  const homeScore = match.score.home || 0;
  const awayScore = match.score.away || 0;
  const totalGoals = homeScore + awayScore;
  const minute = match.minute || 1;

  const ccRate = totalCc > 0 ? Number((minute / totalCc).toFixed(1)) : 999.0;
  // Expected goals according to configured ratio (e.g. totalCc / 3.0)
  const expectedGoalsOver = Math.floor(totalCc / ratio);
  const isDevendoGol = totalGoals < expectedGoalsOver;
  const saldoGolsDevidos = Math.max(0, expectedGoalsOver - totalGoals);

  // Dominant team detection
  let dominantTeam: 'home' | 'away' | null = null;
  let dominantName = "";
  let dominantScore = 0;
  let oppScore = 0;
  let domCc = 0;
  let oppCc = 0;

  if (homeBc > awayBc) {
    dominantTeam = "home";
    dominantName = match.homeTeam.name;
    dominantScore = homeScore;
    oppScore = awayScore;
    domCc = homeBc;
    oppCc = awayBc;
  } else if (awayBc > homeBc) {
    dominantTeam = "away";
    dominantName = match.awayTeam.name;
    dominantScore = awayScore;
    oppScore = homeScore;
    domCc = awayBc;
    oppCc = homeBc;
  }

  const ccDiff = domCc - oppCc;
  const expectedDominantGoalsByCc = domCc >= ratio ? Math.floor(domCc / ratio) : 0;
  const isDominantDevendoGol = expectedDominantGoalsByCc > 0 && dominantScore < expectedDominantGoalsByCc;
  const saldoGolsDominante = Math.max(0, expectedDominantGoalsByCc - dominantScore);
  const domLead = dominantScore - oppScore;
  const isDominantTrailing = dominantScore < oppScore; // Dominante perdendo no placar

  const totalXg = (match.stats.xG.home || 0) + (match.stats.xG.away || 0);

  // Evaluate all candidates
  const candidates: Array<{
    alertType: Codigo31AlertType;
    level: 'watch' | 'forte' | 'premium';
    market: 'over' | 'back';
    reason: string;
    bucket: number;
  }> = [];

  // Minimum threshold based on ratio (e.g., if ratio=3, base CC threshold is 3)
  const minWatchCc = Math.max(2, Math.round(ratio));
  const minForteCc = Math.max(3, Math.round(ratio * 1.33));
  const minPremiumCc = Math.max(5, Math.round(ratio * 2.0));

  // 1. OVER BILATERAL PESADO
  if (homeBc >= minWatchCc && awayBc >= minWatchCc && totalCc >= minPremiumCc && isDevendoGol) {
    candidates.push({
      alertType: "over_bilateral_premium",
      level: "premium",
      market: "over",
      reason: "OVER_PREMIUM_BILATERAL",
      bucket: expectedGoalsOver,
    });
  }

  // 2. OVER PREMIUM + xG
  if (totalCc >= minPremiumCc && ccRate <= config.ccRateForteMaxMinutes && isDevendoGol && totalXg >= 2.5) {
    candidates.push({
      alertType: "over_premium_xg",
      level: "premium",
      market: "over",
      reason: "OVER_PREMIUM_CC_XG",
      bucket: expectedGoalsOver,
    });
  }

  // 3. OVER PREMIUM
  if (totalCc >= minPremiumCc && ccRate <= config.ccRateForteMaxMinutes && isDevendoGol) {
    candidates.push({
      alertType: "over_premium",
      level: "premium",
      market: "over",
      reason: "OVER_PREMIUM",
      bucket: expectedGoalsOver,
    });
  }

  // 4. BACK PREMIUM (CORREÇÃO: Bloqueado se dominante estiver perdendo [domLead < 0] ou já vencendo por 2+ [domLead >= 2])
  if (
    dominantTeam &&
    !isDominantTrailing &&
    domLead >= 0 &&
    domLead < 2 &&
    domCc >= minPremiumCc &&
    oppCc === 0 &&
    ccDiff >= minPremiumCc &&
    isDominantDevendoGol
  ) {
    candidates.push({
      alertType: "back_premium",
      level: "premium",
      market: "back",
      reason: "BACK_PREMIUM_EXTREMO",
      bucket: expectedDominantGoalsByCc,
    });
  }

  // 5. OVER FORTE
  if (totalCc >= minForteCc && ccRate <= config.ccRateForteMaxMinutes && isDevendoGol) {
    candidates.push({
      alertType: "over_forte",
      level: "forte",
      market: "over",
      reason: "OVER_FORTE",
      bucket: expectedGoalsOver,
    });
  }

  // 6. BACK FORTE (CORREÇÃO: Bloqueado se dominante estiver perdendo [domLead < 0] ou já vencendo por 2+ [domLead >= 2])
  if (
    dominantTeam &&
    !isDominantTrailing &&
    domLead >= 0 &&
    domLead < 2 &&
    domCc >= minForteCc &&
    oppCc <= 1 &&
    ccDiff >= minForteCc &&
    isDominantDevendoGol
  ) {
    candidates.push({
      alertType: "back_forte",
      level: "forte",
      market: "back",
      reason: "BACK_FORTE",
      bucket: expectedDominantGoalsByCc,
    });
  }

  // 7. OVER WATCH (Regra Original)
  if (totalCc >= minWatchCc && ccRate <= config.ccRateMaxMinutes && isDevendoGol) {
    candidates.push({
      alertType: "over_watch",
      level: "watch",
      market: "over",
      reason: "OVER_WATCH",
      bucket: expectedGoalsOver,
    });
  }

  // 8. BACK WATCH (CORREÇÃO: Bloqueado se dominante estiver perdendo [domLead < 0] ou já vencendo por 2+ [domLead >= 2])
  if (
    dominantTeam &&
    !isDominantTrailing &&
    domLead >= 0 &&
    domLead < 2 &&
    domCc >= minWatchCc &&
    oppCc <= 1 &&
    ccDiff >= minWatchCc &&
    isDominantDevendoGol
  ) {
    candidates.push({
      alertType: "back_watch",
      level: "watch",
      market: "back",
      reason: "BACK_WATCH",
      bucket: expectedDominantGoalsByCc,
    });
  }

  const homeExpectedGoalsByCc = Math.floor(homeBc / ratio);
  const awayExpectedGoalsByCc = Math.floor(awayBc / ratio);
  const homeDebt = Math.max(0, homeExpectedGoalsByCc - homeScore);
  const awayDebt = Math.max(0, awayExpectedGoalsByCc - awayScore);

  let debtorTeamName = "";
  let debtorTeamSide: 'home' | 'away' | 'both' | null = null;

  if (homeDebt > 0 && awayDebt > 0) {
    debtorTeamSide = 'both';
    debtorTeamName = `Ambos (${match.homeTeam.name} e ${match.awayTeam.name})`;
  } else if (homeDebt > 0) {
    debtorTeamSide = 'home';
    debtorTeamName = match.homeTeam.name;
  } else if (awayDebt > 0) {
    debtorTeamSide = 'away';
    debtorTeamName = match.awayTeam.name;
  } else if (dominantTeam) {
    if (homeBc > awayBc) {
      debtorTeamSide = 'home';
      debtorTeamName = match.homeTeam.name;
    } else if (awayBc > homeBc) {
      debtorTeamSide = 'away';
      debtorTeamName = match.awayTeam.name;
    } else {
      debtorTeamSide = 'both';
      debtorTeamName = `Ambos (${match.homeTeam.name} e ${match.awayTeam.name})`;
    }
  } else {
    debtorTeamSide = 'both';
    debtorTeamName = `Ambos (${match.homeTeam.name} e ${match.awayTeam.name})`;
  }

  // Sort by priority
  let chosenAlert: (typeof candidates)[0] | null = null;
  if (candidates.length > 0) {
    candidates.sort((a, b) => CODIGO_PRIORITY.indexOf(a.alertType) - CODIGO_PRIORITY.indexOf(b.alertType));
    chosenAlert = candidates[0];
  }

  const alertType = chosenAlert ? chosenAlert.alertType : null;
  const shouldAlert = Boolean(chosenAlert);
  
  let dynamicLabel = alertType ? ALERT_DISPLAY_MAP[alertType].label : (isDevendoGol ? "GOL EM ATRASO" : "SALDO EM DIA");
  if (alertType === "over_premium" && (debtorTeamSide === "home" || debtorTeamSide === "away")) {
    dynamicLabel = `PREMIUM 3.1.2 — GOL MUITO DEVENDO (${debtorTeamName})`;
  } else if (alertType === "over_forte" && (debtorTeamSide === "home" || debtorTeamSide === "away")) {
    dynamicLabel = `FORTE 3.1.2 — GOL DEVENDO (${debtorTeamName})`;
  }

  const display = alertType ? { emoji: ALERT_DISPLAY_MAP[alertType].emoji, label: dynamicLabel } : { emoji: "⚖️", label: dynamicLabel };
  const defaultReason = isDominantTrailing && isDominantDevendoGol
    ? "DOMINANTE_PERDENDO_BACK_BLOQUEADO"
    : isDevendoGol
    ? "GOL_DEVENDO_RADAR"
    : "SALDO_EM_DIA";

  const template = alertType ? MESSAGE_TEMPLATES_MAP[alertType] : {
    motivo: isDominantTrailing && isDominantDevendoGol
      ? `Time dominante (${dominantName}) com ${domCc} CCs está perdendo no placar (${dominantScore}-${oppScore}). Alerta de Back bloqueado por proteção de zebra.`
      : isDevendoGol
      ? `Total de ${totalCc} CC para ${totalGoals} gols (devendo ${saldoGolsDevidos} gol).`
      : "Produção ofensiva convertida em gols dentro do esperado.",
    leitura: isDominantTrailing && isDominantDevendoGol
      ? "Favorito perdendo — aguardar reação ofensiva comprovada e não entrar em Back cego."
      : isDevendoGol
      ? "Observar evolução de finalizações na área."
      : "Sem anomalia de conversão.",
  };

  // Build Telegram formatted message (Python format with each data point on a separate line)
  let formattedTelegram = "";
  if (alertType) {
    if (chosenAlert?.market === "back") {
      formattedTelegram = `${display.emoji} ${display.label}
Partida: ${match.homeTeam.name} ${homeScore}-${awayScore} ${match.awayTeam.name}
Minuto: ${minute}'
Time Dominante: ${dominantName}
CC: ${homeBc}x${awayBc}
Diferença CC: ${ccDiff}
Ritmo: ${ccRate} min/CC
Esperado Dominante (Ratio ${ratio.toFixed(1)}:1): ${expectedDominantGoalsByCc}
Gols Dominante: ${dominantScore}
Dívida: ${saldoGolsDominante} gol(s)`;
    } else {
      const xgLine = totalXg > 0 ? `xG Total: ${totalXg.toFixed(2)}\n` : "";
      const debtorLine = debtorTeamName ? `Time Devedor: ${debtorTeamName}\n` : "";
      formattedTelegram = `${display.emoji} ${display.label}
Partida: ${match.homeTeam.name} ${homeScore}-${awayScore} ${match.awayTeam.name}
Minuto: ${minute}'
${debtorLine}CC Total: ${homeBc}x${awayBc} = ${totalCc}
Ritmo: ${ccRate} min/CC
${xgLine}Esperado por CC (Ratio ${ratio.toFixed(1)}:1): ${expectedGoalsOver}
Gols Reais: ${totalGoals}
Dívida de Gols: ${saldoGolsDevidos} gol(s)`;
    }
  }

  let bettingTip: BettingTipData | undefined = undefined;
  if (alertType) {
    const isBack = chosenAlert?.market === "back";
    const prob = chosenAlert?.level === "premium" ? 84 : chosenAlert?.level === "forte" ? 75 : 67;
    bettingTip = generateBettingTip({
      marketCode: isBack ? "BACK_DOMINANTE" : "OVER_GOLS_DEVENDO",
      marketName: isBack ? `Back ${dominantName} (Diagnóstico)` : `Over ${totalGoals + 0.5} Gols`,
      targetSelection: isBack ? `Vitória ${dominantName} / HA 0.0` : `Mais de ${totalGoals + 0.5} Gols`,
      probabilityPct: prob,
      confidence: chosenAlert?.level === "premium" ? "extrema" : chosenAlert?.level === "forte" ? "alta" : "moderada",
      reasoning: template.motivo,
      actionText: isBack ? `Entrada em Back ${dominantName} no mercado 1X2 / Handicap` : `Entrada no mercado de Over Gols à frente`,
      match,
      config,
    });
  }

  return {
    alertType,
    shouldAlert,
    reason: chosenAlert ? chosenAlert.reason : defaultReason,
    level: chosenAlert ? chosenAlert.level : null,
    market: chosenAlert ? chosenAlert.market : null,
    bucket: chosenAlert ? chosenAlert.bucket : expectedGoalsOver,
    totalCc,
    homeCc: homeBc,
    awayCc: awayBc,
    totalGoals,
    homeScore,
    awayScore,
    ccRate,
    expectedGoalsByCc: expectedGoalsOver,
    isDevendoGol,
    saldoGolsDevidos,
    ratioUsed: ratio,
    dominantTeam,
    dominantName,
    dominantCc: domCc,
    oppCc,
    ccDiff,
    expectedDominantGoalsByCc,
    isDominantDevendoGol,
    saldoGolsDominante,
    isDominantTrailing,
    dominantLead: domLead,
    debtorTeamName,
    debtorTeamSide,
    title: display.label,
    emoji: display.emoji,
    motivo: template.motivo,
    leitura: template.leitura,
    formattedTelegram,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 2. TRIPLO FILTRO DE DÍVIDA DE GOLS (TRIPLE DEBT FILTER)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateTripleDebt(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): TripleDebtEvaluation {
  const bc = getMatchBigChances(match);
  const hCc = bc.home;
  const aCc = bc.away;
  const totalCc = bc.total;

  const hXg = match.stats.xG.home || 0;
  const aXg = match.stats.xG.away || 0;
  const totalXg = hXg + aXg;

  const hXgot = match.stats.xGOT?.home ?? Number((hXg * 0.85).toFixed(2));
  const aXgot = match.stats.xGOT?.away ?? Number((aXg * 0.85).toFixed(2));
  const totalXgot = hXgot + aXgot;

  const hG = match.score.home || 0;
  const aG = match.score.away || 0;
  const totalGoals = hG + aG;

  const debtMargin = config.debtMarginXG || 1.0;
  const ratio = config.chancesPerGoalRatio || 3.0;

  // Unilateral checks
  const hHits = (hCc >= 3 ? 1 : 0) +
    (hCc / (totalCc || 1) >= 0.7 ? 1 : 0) +
    (hXg / (totalXg || 1) >= 0.65 ? 1 : 0) +
    (hXgot / (totalXgot || 1) >= 0.65 ? 1 : 0) +
    (aCc <= 1 || (hCc - aCc) >= 2 ? 1 : 0);

  const aHits = (aCc >= 3 ? 1 : 0) +
    (aCc / (totalCc || 1) >= 0.7 ? 1 : 0) +
    (aXg / (totalXg || 1) >= 0.65 ? 1 : 0) +
    (aXgot / (totalXgot || 1) >= 0.65 ? 1 : 0) +
    (hCc <= 1 || (aCc - hCc) >= 2 ? 1 : 0);

  let scope: 'unilateral' | 'bilateral' | 'none' = 'none';
  let scopeSide: 'home' | 'away' | 'total' | null = null;
  let ccInScope = 0;
  let xgInScope = 0;
  let xgotInScope = 0;
  let goalsInScope = 0;

  if (hCc >= 3 && hHits >= 4) {
    scope = 'unilateral';
    scopeSide = 'home';
    ccInScope = hCc;
    xgInScope = hXg;
    xgotInScope = hXgot;
    goalsInScope = hG;
  } else if (aCc >= 3 && aHits >= 4) {
    scope = 'unilateral';
    scopeSide = 'away';
    ccInScope = aCc;
    xgInScope = aXg;
    xgotInScope = aXgot;
    goalsInScope = aG;
  } else if (totalCc >= 3 && totalXg >= 1.0 && totalXgot >= 1.0) {
    scope = 'bilateral';
    scopeSide = 'total';
    ccInScope = totalCc;
    xgInScope = totalXg;
    xgotInScope = totalXgot;
    goalsInScope = totalGoals;
  }

  const expectedGoalsByCc = Math.floor(ccInScope / ratio);
  const ccDebt = expectedGoalsByCc > goalsInScope;
  const xgDebt = xgInScope >= goalsInScope + debtMargin;
  const xgotDebt = xgotInScope >= goalsInScope + debtMargin;

  const failedReasons: string[] = [];
  if (!ccDebt) failedReasons.push("triple_debt_failed_cc");
  if (!xgDebt) failedReasons.push("triple_debt_failed_xg");
  if (!xgotDebt) failedReasons.push("triple_debt_failed_xgot");

  const tripleDebtFormed = scope !== 'none' && ccDebt && xgDebt && xgotDebt;
  let blockReason: string | null = null;

  if (scope === 'none') {
    blockReason = "scope_not_classified";
  } else if (failedReasons.length === 3) {
    blockReason = "no_real_debt";
  } else if (failedReasons.length > 0) {
    blockReason = failedReasons.join("+");
  }

  const debtorTeamName = scope === 'unilateral'
    ? (scopeSide === 'home' ? match.homeTeam.name : match.awayTeam.name)
    : scope === 'bilateral'
    ? 'Ambos os Times'
    : undefined;

  let statusBadge = "⚖️ Sem Dívida Trinca";
  if (tripleDebtFormed) {
    statusBadge = scope === 'unilateral' && debtorTeamName
      ? `💎 TRINCA DE DÍVIDAS ATIVA (${debtorTeamName})`
      : `💎 TRINCA DE DÍVIDAS ATIVA (${scope.toUpperCase()})`;
  } else if (ccDebt || xgDebt || xgotDebt) {
    statusBadge = `⚠️ Dívida Parcial (${[ccDebt ? 'CC' : '', xgDebt ? 'xG' : '', xgotDebt ? 'xGOT' : ''].filter(Boolean).join('+')})`;
  }

  let bettingTip: BettingTipData | undefined = undefined;
  if (tripleDebtFormed) {
    const isUni = scope === 'unilateral';
    const targetName = debtorTeamName || 'Equipe Devedora';
    bettingTip = generateBettingTip({
      marketCode: isUni ? "TRIPLE_DEBT_UNILATERAL" : "TRIPLE_DEBT_OVER",
      marketName: isUni ? `Próximo Gol (${targetName})` : `Over Gols (+0.5 Gol)`,
      targetSelection: isUni ? `Gol de ${targetName}` : `Mais de ${goalsInScope + 0.5} Gols`,
      probabilityPct: isUni ? 85 : 88,
      confidence: 'extrema',
      reasoning: `Tríplice Dívida Ativa: CC (${ccInScope}), xG (${xgInScope}) e xGOT (${xgotInScope}) com saldo atrasado de ${goalsInScope} gols marcados.`,
      actionText: isUni ? `Entrada em Próximo Gol / Back de ${targetName}` : `Entrada em Over Gols à frente`,
      match,
      config,
    });
  }

  return {
    tripleDebtFormed,
    scope,
    scopeSide,
    debtorTeamName,
    ccInScope,
    xgInScope: Number(xgInScope.toFixed(2)),
    xgotInScope: Number(xgotInScope.toFixed(2)),
    goalsInScope,
    expectedGoalsByCc,
    ccDebt,
    xgDebt,
    xgotDebt,
    failedReasons,
    blockReason,
    wouldBlockSignal: !tripleDebtFormed,
    statusBadge,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 3. PRESSÃO VENDÁVEL (BACK ALTO + LAY BAIXO)
// ──────────────────────────────────────────────────────────────────────────
export function evaluatePressaoVendavel(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): PressaoVendavelEvaluation {
  const minute = match.minute || 0;
  const hG = match.score.home || 0;
  const aG = match.score.away || 0;
  const bc = getMatchBigChances(match);

  const evalSide = (side: 'home' | 'away') => {
    const isHome = side === 'home';
    const ownG = isHome ? hG : aG;
    const oppG = isHome ? aG : hG;
    const ownDiff = ownG - oppG;
    const team = isHome ? match.homeTeam.name : match.awayTeam.name;

    const cc = isHome ? bc.home : bc.away;
    const xg = isHome ? match.stats.xG.home : match.stats.xG.away;
    const xgot = isHome
      ? (match.stats.xGOT?.home ?? xg * 0.85)
      : (match.stats.xGOT?.away ?? xg * 0.85);

    const shots = isHome ? (match.stats.shotsOnTarget.home + match.stats.shotsOffTarget.home) : (match.stats.shotsOnTarget.away + match.stats.shotsOffTarget.away);
    const sot = isHome ? match.stats.shotsOnTarget.home : match.stats.shotsOnTarget.away;
    const sotPct = shots > 0 ? Number((sot / shots).toFixed(2)) : 0;
    const oppXg = isHome ? match.stats.xG.away : match.stats.xG.home;

    const posse = isHome ? match.stats.possession.home : match.stats.possession.away;
    const toq = isHome ? (match.stats.boxTouches?.home ?? Math.round(match.stats.dangerousAttacks.home * 0.4)) : (match.stats.boxTouches?.away ?? Math.round(match.stats.dangerousAttacks.away * 0.4));
    const toqOpp = isHome ? (match.stats.boxTouches?.away ?? Math.round(match.stats.dangerousAttacks.away * 0.4)) : (match.stats.boxTouches?.home ?? Math.round(match.stats.dangerousAttacks.home * 0.4));

    const fails: string[] = [];
    if (minute < 25) fails.push("minute < 25");
    if (minute > 70) fails.push("minute > 70");
    if (ownDiff > 0) fails.push("ja_vencendo");
    if (ownDiff <= -2) fails.push("atras_por_2+");
    if (cc < 2) fails.push("cc < 2");
    if (xg < 1.0) fails.push("xg < 1.0");
    if (xgot < 0.8) fails.push("xgot < 0.8");
    const toqRatio = toqOpp > 0 ? toq / toqOpp : 2.5;
    if (posse < 60 && !(toqRatio >= 2.0 && toq >= 8)) fails.push("sem_dominancia_posse_ou_toques");
    if (sotPct < 0.35) fails.push("sot_pct < 35%");
    if (oppXg > 0.7) fails.push("opp_xg > 0.7");

    const qualified = fails.length === 0;
    return {
      side,
      team,
      qualified,
      fails,
      metrics: {
        cc,
        xg: Number(xg.toFixed(2)),
        xgot: Number(xgot.toFixed(2)),
        shots,
        sot,
        sotPct,
        posse,
        toquesArea: toq,
        oppXg: Number(oppXg.toFixed(2)),
      },
    };
  };

  const homeRes = evalSide('home');
  const awayRes = evalSide('away');

  let best = homeRes.qualified ? homeRes : awayRes.qualified ? awayRes : null;
  if (homeRes.qualified && awayRes.qualified) {
    best = homeRes.metrics.xg >= awayRes.metrics.xg ? homeRes : awayRes;
  }

  if (best && best.qualified) {
    const probTarget = Math.min(88, Math.max(55, Math.round(60 + (best.metrics.xg - best.metrics.oppXg) * 15)));
    const fairOdd = Number((100 / probTarget).toFixed(2));
    const minRecommendedOdd = Number((fairOdd * 1.1).toFixed(2));

    const tese = `BACK ${best.team} agora — pressão acumulada (${best.metrics.posse}% posse / ${best.metrics.cc} CC) e adversário sem reação (xG ${best.metrics.oppXg}). Modelo projeta ${probTarget}% de probabilidade de vitória. Odd justa = ${fairOdd}. Recomendado entrar se odd ≥ ${minRecommendedOdd} e vender no gol (LAY).`;

    const bettingTip = generateBettingTip({
      marketCode: "PRESSAO_VENDAVEL",
      marketName: `Pressão Vendável (${best.team})`,
      targetSelection: `Back ${best.team} / Lay Adversário`,
      probabilityPct: probTarget,
      confidence: 'alta',
      reasoning: tese,
      actionText: `Entrada recomendada se odd >= ${minRecommendedOdd.toFixed(2)}. Realizar Lay assim que sair o gol.`,
      match,
    });

    return {
      qualified: true,
      side: best.side,
      team: best.team,
      minute,
      score: `${hG}-${aG}`,
      tese,
      fairOdd,
      minRecommendedOdd,
      probTarget,
      fails: [],
      metrics: best.metrics,
      bettingTip,
    };
  }

  return {
    qualified: false,
    side: null,
    team: "",
    minute,
    score: `${hG}-${aG}`,
    tese: "Sem oportunidade de Pressão Vendável nos parâmetros defensivos atuais.",
    fails: [...homeRes.fails, ...awayRes.fails],
    metrics: homeRes.metrics.xg >= awayRes.metrics.xg ? homeRes.metrics : awayRes.metrics,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 4. BLINDAGEM DE FAVORITO PERDENDO (DOMINANT TRAILING PROTECTION)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateDominantTrailing(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): DominantTrailingEvaluation {
  const bc = getMatchBigChances(match);
  const hG = match.score.home || 0;
  const aG = match.score.away || 0;

  let dominantSide: 'home' | 'away' | null = null;
  if (bc.home > bc.away) dominantSide = 'home';
  else if (bc.away > bc.home) dominantSide = 'away';
  else if (match.stats.xG.home > match.stats.xG.away) dominantSide = 'home';
  else if (match.stats.xG.away > match.stats.xG.home) dominantSide = 'away';

  if (!dominantSide) {
    return {
      dominantSide: null,
      dominantScore: 0,
      opponentScore: 0,
      dominantIsTrailing: false,
      dominantTrailingBy: 0,
      dominantReactionConfirmed: true,
      livePressureStatus: 'neutro',
      entryAllowed: true,
      blockReason: "",
      status: 'NOT_TRAILING',
    };
  }

  const domScore = dominantSide === 'home' ? hG : aG;
  const oppScore = dominantSide === 'home' ? aG : hG;
  const isTrailing = oppScore > domScore;
  const trailingBy = Math.max(0, oppScore - domScore);

  if (!isTrailing) {
    return {
      dominantSide,
      dominantScore: domScore,
      opponentScore: oppScore,
      dominantIsTrailing: false,
      dominantTrailingBy: 0,
      dominantReactionConfirmed: true,
      livePressureStatus: 'forte',
      entryAllowed: true,
      blockReason: "",
      status: 'NOT_TRAILING',
    };
  }

  // If trailing, check for verified reaction
  const domPressure = dominantSide === 'home' ? match.stats.pressureIndex.home : match.stats.pressureIndex.away;
  let livePressureStatus: 'brutal' | 'forte' | 'neutro' | 'dead' = 'neutro';
  if (domPressure >= 85) livePressureStatus = 'brutal';
  else if (domPressure >= 68) livePressureStatus = 'forte';
  else if (domPressure <= 35) livePressureStatus = 'dead';

  const domDangerousAttacksLast10 = dominantSide === 'home' ? match.stats.dangerousAttacksLast10.home : match.stats.dangerousAttacksLast10.away;
  const domSot = dominantSide === 'home' ? match.stats.shotsOnTarget.home : match.stats.shotsOnTarget.away;

  // Criteria: pressure strong + attacks active
  const reactionConfirmed = domPressure >= 65 || domDangerousAttacksLast10 >= 6 || domSot >= 3;

  if (trailingBy >= 2 && livePressureStatus !== 'brutal') {
    return {
      dominantSide,
      dominantScore: domScore,
      opponentScore: oppScore,
      dominantIsTrailing: true,
      dominantTrailingBy: trailingBy,
      dominantReactionConfirmed: false,
      livePressureStatus,
      entryAllowed: false,
      blockReason: "dominant_trailing_by_two_or_more",
      status: 'DOMINANT_TRAILING_TRAP',
      blockMessage: "BLOQUEADO — Favorito perdendo por 2+ gols sem pressão brutal.",
    };
  }

  if (!reactionConfirmed) {
    return {
      dominantSide,
      dominantScore: domScore,
      opponentScore: oppScore,
      dominantIsTrailing: true,
      dominantTrailingBy: trailingBy,
      dominantReactionConfirmed: false,
      livePressureStatus,
      entryAllowed: false,
      blockReason: "dominant_trailing_without_confirmed_reaction",
      status: 'DOMINANT_TRAILING_TRAP',
      blockMessage: "BLOQUEADO — Favorito perdendo e sem reação ofensiva viva confirmada.",
    };
  }

  return {
    dominantSide,
    dominantScore: domScore,
    opponentScore: oppScore,
    dominantIsTrailing: true,
    dominantTrailingBy: trailingBy,
    dominantReactionConfirmed: true,
    livePressureStatus,
    entryAllowed: true,
    blockReason: "",
    status: 'DOMINANT_REACTION_CONFIRMED',
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 5. REGRAS TRADICIONAIS V1.2 (OVER & BACK)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateTraditionalSignals(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): TraditionalRuleSignal[] {
  const signals: TraditionalRuleSignal[] = [];
  const min = match.minute || 0;
  const bc = getMatchBigChances(match);
  const totalBc = bc.total;
  const minBc = Math.min(bc.home, bc.away);
  const domBc = Math.max(bc.home, bc.away);
  const oppBc = Math.min(bc.home, bc.away);
  const totalGoals = (match.score.home || 0) + (match.score.away || 0);
  const rate = totalBc > 0 ? min / totalBc : 999;
  const isHomeDom = bc.home >= bc.away;
  const domXgot = isHomeDom
    ? (match.stats.xGOT?.home ?? match.stats.xG.home * 0.85)
    : (match.stats.xGOT?.away ?? match.stats.xG.away * 0.85);

  // Over Premium (Min 36-50, Total CC >= 3, Rate <= 15, Min CC >= 1)
  if (min >= 36 && min <= 50 && totalBc >= 3 && rate <= 15 && minBc >= 1) {
    signals.push({
      ruleName: "OVER_PREMIUM",
      marketTarget: "OVER_2_5",
      confidenceTier: "A-",
      recommendedAction: "ENTER_OVER_PREMIUM",
      trace: `Over Premium ativado (Total CC: ${totalBc}, Rate: ${rate.toFixed(1)} min/CC)`,
    });
  }

  // Over Bilateral Forte (Min 36-65, Total CC >= 4, Min CC >= 2)
  if (min >= 36 && min <= 65 && totalBc >= 4 && rate <= 15 && minBc >= 2) {
    signals.push({
      ruleName: "OVER_BILATERAL_FORTE",
      marketTarget: "OVER_2_5",
      confidenceTier: "B+",
      recommendedAction: "ENTER_OVER_BILATERAL_FORTE",
      trace: `Over Bilateral Forte ativado (Total CC: ${totalBc}, Min CC: ${minBc})`,
    });
  }

  // Over Gol Limite (Min 76-83, Total CC >= 7, Gols 1-4)
  if (min >= 76 && min <= 83 && totalBc >= 7 && minBc >= 2 && Math.abs(match.score.home - match.score.away) >= 1) {
    signals.push({
      ruleName: "OVER_GOL_LIMITE",
      marketTarget: "NEXT_GOAL",
      confidenceTier: "Especial",
      recommendedAction: "ENTER_OVER_GOL_LIMITE",
      trace: `Over Gol Limite no final (Total CC: ${totalBc}, Gols: ${totalGoals})`,
    });
  }

  // Back T1 Main (Min 36-50, Dominante CC >= 3, Opp CC = 0, Dominante empatando ou vencendo por 1, nunca perdendo)
  const domScore = isHomeDom ? (match.score.home || 0) : (match.score.away || 0);
  const oppScore = isHomeDom ? (match.score.away || 0) : (match.score.home || 0);
  const domLead = domScore - oppScore;
  if (min >= 36 && min <= 50 && domBc >= 3 && oppBc === 0 && domXgot >= 0.5 && domLead >= 0 && domLead < 2) {
    signals.push({
      ruleName: "BACK_T1_MAIN",
      marketTarget: "BACK_DOMINANT",
      confidenceTier: "A",
      recommendedAction: "ENTER_BACK_T1_MAIN",
      trace: `Back T1 Main ativado (Dom CC: ${domBc}, Opp CC: 0, Placar: ${domScore}-${oppScore})`,
    });
  }

  return signals;
}

// ──────────────────────────────────────────────────────────────────────────
// 6. GOL IMINENTE: SURTO DE PRESSÃO RECENTE (ÚLTIMOS 5 MIN) + DÍVIDA ATIVA
// ──────────────────────────────────────────────────────────────────────────
export function evaluateImminentGoal(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): ImminentGoalEvaluation {
  const curMin = Math.max(1, match.minute || 1);
  const bc = getMatchBigChances(match);
  const totalBc = bc.total;
  const homeBc = bc.home;
  const awayBc = bc.away;
  const ratio = Math.max(1.0, config.chancesPerGoalRatio || 3.0);

  const totalGoals = (match.score.home || 0) + (match.score.away || 0);
  const expectedGoals = Math.floor(totalBc / ratio);
  const effectiveDebt = Math.max(0, expectedGoals - totalGoals);

  // Filter 5-minute timeline segments
  const last5Points = (match.momentumTimeline || []).filter(
    (pt) => pt.minute > Math.max(1, curMin - 5) && pt.minute <= curMin
  );
  const prev5Points = (match.momentumTimeline || []).filter(
    (pt) => pt.minute > Math.max(1, curMin - 10) && pt.minute <= Math.max(1, curMin - 5)
  );

  let homeLast5 = last5Points.filter((pt) => pt.homeShot).length;
  let awayLast5 = last5Points.filter((pt) => pt.awayShot).length;
  let homePrev5 = prev5Points.filter((pt) => pt.homeShot).length;
  let awayPrev5 = prev5Points.filter((pt) => pt.awayShot).length;

  if (homeLast5 === 0 && awayLast5 === 0) {
    homeLast5 = last5Points.filter((pt) => pt.homeDangerousAttack).length;
    awayLast5 = last5Points.filter((pt) => pt.awayDangerousAttack).length;
    homePrev5 = prev5Points.filter((pt) => pt.homeDangerousAttack).length;
    awayPrev5 = prev5Points.filter((pt) => pt.awayDangerousAttack).length;
  }

  let totalLast5 = homeLast5 + awayLast5;
  let totalPrev5 = homePrev5 + awayPrev5;
  let variationPct5m = 0;

  if (totalPrev5 > 0) {
    variationPct5m = Math.round(((totalLast5 - totalPrev5) / totalPrev5) * 100);
  } else if (totalLast5 > 0) {
    variationPct5m = 100;
  } else if (totalBc > 0) {
    const avg5Min = (totalBc / curMin) * 5;
    const recentPressure = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;
    const estLast5 = +(avg5Min * (recentPressure / 50)).toFixed(1);
    const estPrev5 = +avg5Min.toFixed(1);
    variationPct5m = estPrev5 > 0 ? Math.round(((estLast5 - estPrev5) / estPrev5) * 100) : 0;
    totalLast5 = estLast5;
    totalPrev5 = estPrev5;
  }

  // Determine beneficiary side
  let beneficiaryTeam: string | undefined = undefined;
  if (homeLast5 > awayLast5 && homeLast5 >= 2) {
    beneficiaryTeam = match.homeTeam.name;
  } else if (awayLast5 > homeLast5 && awayLast5 >= 2) {
    beneficiaryTeam = match.awayTeam.name;
  } else if (match.stats.pressureIndex.home > match.stats.pressureIndex.away + 15) {
    beneficiaryTeam = match.homeTeam.name;
  } else if (match.stats.pressureIndex.away > match.stats.pressureIndex.home + 15) {
    beneficiaryTeam = match.awayTeam.name;
  }

  // Live pressure metrics
  const avgPressure = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;
  const recentAttacks10 = (match.stats.dangerousAttacksLast10?.home || 0) + (match.stats.dangerousAttacksLast10?.away || 0);
  const thresholdPct = config.imminentGoalThresholdPct ?? 50;

  // Qualification logic:
  // 1. Extreme surge: variation >= thresholdPct AND (effectiveDebt >= 0.8 OR recentAttacks10 >= 7 OR avgPressure >= 65)
  // 2. High surge: variation >= (thresholdPct * 0.6) AND effectiveDebt >= 1 AND totalLast5 >= 2
  // 3. Late blitz: curMin >= 72 AND curMin <= 88 AND (variationPct5m > 0 || avgPressure >= 75)
  const isExtremeSurge = (variationPct5m >= thresholdPct && (effectiveDebt >= 0.8 || recentAttacks10 >= 7 || avgPressure >= 65)) || (variationPct5m >= (thresholdPct * 1.5) && totalLast5 >= 2);
  const isHighSurge = (variationPct5m >= (thresholdPct * 0.6) && effectiveDebt >= 1) || (variationPct5m >= (thresholdPct * 0.8) && recentAttacks10 >= 6);
  const isModerateSurge = (variationPct5m > 0 && effectiveDebt >= 1) || (curMin >= 72 && avgPressure >= 70 && variationPct5m >= 0);

  let isImminent = false;
  let intensity: ImminentGoalEvaluation['intensity'] = 'nenhuma';
  let confidenceScore = 0;
  let targetMarket: ImminentGoalEvaluation['targetMarket'] = null;
  let triggerReason = "";

  if (isExtremeSurge) {
    isImminent = true;
    intensity = 'extrema';
    confidenceScore = Math.min(96, Math.max(80, 75 + Math.round(variationPct5m / 5) + Math.round(effectiveDebt * 8)));
    targetMarket = curMin >= 75 ? 'OVER_GOL_LIMITE' : beneficiaryTeam ? 'PROXIMO_GOL' : 'OVER_GOL_LIMITE';
    triggerReason = `Surto ofensivo extremo (+${variationPct5m}% nos últimos 5m) com ${totalLast5} chances e dívida de ${effectiveDebt} gol(s)`;
  } else if (isHighSurge) {
    isImminent = true;
    intensity = 'alta';
    confidenceScore = Math.min(85, Math.max(68, 65 + Math.round(variationPct5m / 6) + Math.round(effectiveDebt * 6)));
    targetMarket = beneficiaryTeam ? 'PROXIMO_GOL' : 'OVER_GOL_LIMITE';
    triggerReason = `Aceleração contundente (+${variationPct5m}% nos últimos 5m) e pressão acumulada de ${avgPressure.toFixed(0)}%`;
  } else if (isModerateSurge) {
    isImminent = true;
    intensity = 'moderada';
    confidenceScore = Math.min(74, Math.max(55, 55 + Math.round(variationPct5m / 8)));
    targetMarket = 'PROXIMO_GOL';
    triggerReason = `Intensidade ascendente (+${variationPct5m}% nos 5m) em momento favorável de dívida`;
  } else {
    isImminent = false;
    intensity = 'nenhuma';
    confidenceScore = Math.max(10, Math.min(45, Math.round(avgPressure / 2)));
    triggerReason = `Ritmo estável ou em desaceleração (${variationPct5m}% nos últimos 5 minutos)`;
  }

  const title = isImminent
    ? `🚨 GOL IMINENTE (${intensity.toUpperCase()}) — ${variationPct5m > 0 ? `+${variationPct5m}%` : `${variationPct5m}%`} 5m`
    : `Ritmo Moderado (${variationPct5m}%)`;

  const actionText = isImminent
    ? targetMarket === 'OVER_GOL_LIMITE'
      ? `Entrada recomendada em Over Gol Limite / Próximo Gol (Gatilho Live disparado no minuto ${curMin}')`
      : beneficiaryTeam
      ? `Entrada recomendada em Próximo Gol de ${beneficiaryTeam} (Pressão dominante recente)`
      : `Entrada recomendada em Over Gols (Aceleração ofensiva confirmada)`
    : "Aguardar novo surto ofensivo ou confirmação de pressão.";

  let bettingTip: BettingTipData | undefined = undefined;
  if (isImminent) {
    const isBack = targetMarket === 'BACK_DOMINANTE';
    const totalGoals = (match.score.home || 0) + (match.score.away || 0);
    bettingTip = generateBettingTip({
      marketCode: isBack ? "GOL_IMINENTE_BACK" : "GOL_IMINENTE_OVER",
      marketName: isBack ? `Back / Próximo Gol (${beneficiaryTeam || 'Dominante'})` : `Over Gol Limite (+0.5 Gol)`,
      targetSelection: isBack ? `Gol de ${beneficiaryTeam || 'Dominante'}` : `Mais de ${totalGoals + 0.5} Gols`,
      probabilityPct: confidenceScore,
      confidence: intensity === 'extrema' ? 'extrema' : 'alta',
      reasoning: triggerReason,
      actionText,
      match,
    });
  }

  return {
    isImminent,
    intensity,
    variationPct5m,
    totalChancesLast5: totalLast5,
    totalChancesPrev5: totalPrev5,
    homeChancesLast5: homeLast5,
    awayChancesLast5: awayLast5,
    effectiveDebt,
    targetMarket,
    beneficiaryTeam,
    triggerReason,
    confidenceScore,
    title,
    actionText,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 7. FUNIL DE CANTOS (CANTOS LIMITE HT / FT)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateFunilCantos(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): FunilCantosEvaluation {
  if (!config.enableFunilCantos) {
    return { qualified: false, phase: null, minute: match.minute || 0, currentCorners: 0, targetLine: "", attacksPerMinLast10: 0, blockedShotsLast10: 0 };
  }

  const min = match.minute || 0;
  const currentCorners = (match.stats.corners.home || 0) + (match.stats.corners.away || 0);
  const homeAttacks = match.stats.dangerousAttacksLast10?.home || 0;
  const awayAttacks = match.stats.dangerousAttacksLast10?.away || 0;
  const totalAttacks10 = homeAttacks + awayAttacks;
  const attacksPerMinLast10 = Number((totalAttacks10 / 10).toFixed(2));
  const blockedShotsLast10 = (match.stats.blockedShots?.home || 0) + (match.stats.blockedShots?.away || 0);

  // HT Phase (min 35 - 45) or FT Phase (min 78 - 89)
  const isHtPhase = min >= 35 && min <= 45;
  const isFtPhase = min >= 77 && min <= 89;

  if (!isHtPhase && !isFtPhase) {
    return { qualified: false, phase: null, minute: min, currentCorners, targetLine: "", attacksPerMinLast10, blockedShotsLast10 };
  }

  // Validação Real dos Escanteios da Partida:
  // HT Limite exige no mínimo N escanteios no 1T (padrão >= 2)
  // FT Limite exige no mínimo N escanteios no jogo todo (padrão >= 5)
  const minCornersRequired = isHtPhase
    ? (config.funilCantosMinCornersHt ?? 2)
    : (config.funilCantosMinCornersFt ?? 5);

  const maxPaceMinutes = config.funilCantosMaxMinPerCorner ?? 14;
  const cornerPace = currentCorners > 0 ? Number((min / currentCorners).toFixed(1)) : 999;

  if (currentCorners < minCornersRequired || cornerPace > maxPaceMinutes) {
    return { qualified: false, phase: isHtPhase ? 'HT_LIMITE' : 'FT_LIMITE', minute: min, currentCorners, targetLine: "", attacksPerMinLast10, blockedShotsLast10 };
  }

  const phase = isHtPhase ? 'HT_LIMITE' : 'FT_LIMITE';
  const dominantAttackingSide = homeAttacks > awayAttacks ? match.homeTeam.name : awayAttacks > homeAttacks ? match.awayTeam.name : undefined;
  const avgPressure = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;

  // Qualification: active attacks in late half + pressure >= 60 OR high blocked shots
  const isQualified = (attacksPerMinLast10 >= 0.8 && avgPressure >= 58) || (attacksPerMinLast10 >= 0.6 && blockedShotsLast10 >= 3);

  if (!isQualified) {
    return { qualified: false, phase, minute: min, currentCorners, targetLine: "", attacksPerMinLast10, blockedShotsLast10 };
  }

  const targetCorners = currentCorners + 1;
  const targetLine = `Mais de ${currentCorners}.5 Escanteios (${phase === 'HT_LIMITE' ? '1º Tempo' : 'Final'})`;
  const prob = Math.min(92, Math.max(72, 70 + Math.round(attacksPerMinLast10 * 12) + (avgPressure > 75 ? 8 : 0)));

  const bettingTip = generateBettingTip({
    marketCode: "FUNIL_CANTOS",
    marketName: `Funil de Cantos Limite (${phase === 'HT_LIMITE' ? 'HT' : 'FT'})`,
    targetSelection: targetLine,
    probabilityPct: prob,
    confidence: prob >= 82 ? 'extrema' : 'alta',
    reasoning: `Ritmo acelerado de cantos (${currentCorners} cantos já ocorridos, taxa de 1 a cada ${cornerPace} min) + pressão no funil (${attacksPerMinLast10} ataques perigosos/min) aos ${min}'.`,
    actionText: `Entrar em Over Cantos Limite (Linha Atual: ${currentCorners}.5)`,
    match,
    config,
  });

  return {
    qualified: true,
    phase,
    minute: min,
    currentCorners,
    targetLine,
    attackingTeam: dominantAttackingSide,
    attacksPerMinLast10,
    blockedShotsLast10,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 8. RACE TO CORNERS (CORRIDA DE CANTOS 3, 5, 7)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateRaceToCorners(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): RaceToCornersEvaluation {
  if (!config.enableRaceToCorners) {
    return { qualified: false, targetRace: 5, leaderTeam: "", leaderSide: 'home', leaderCorners: 0, oppCorners: 0, paceMinPerCorner: 0 };
  }

  const min = Math.max(1, match.minute || 1);
  const hCorn = match.stats.corners.home || 0;
  const aCorn = match.stats.corners.away || 0;
  const hPress = match.stats.pressureIndex.home || 0;
  const aPress = match.stats.pressureIndex.away || 0;

  let leaderSide: 'home' | 'away' = 'home';
  let leaderCorners = hCorn;
  let oppCorners = aCorn;
  let leaderPress = hPress;
  let leaderTeam = match.homeTeam.name;

  if (aCorn > hCorn || (aCorn === hCorn && aPress > hPress)) {
    leaderSide = 'away';
    leaderCorners = aCorn;
    oppCorners = hCorn;
    leaderPress = aPress;
    leaderTeam = match.awayTeam.name;
  }

  // Determine appropriate target race
  let targetRace: 3 | 5 | 7 | 9 = 5;
  if (leaderCorners < 3 && min <= 35) targetRace = 3;
  else if (leaderCorners < 5 && min <= 65) targetRace = 5;
  else if (leaderCorners < 7 && min <= 80) targetRace = 7;
  else targetRace = 9;

  const cornersNeeded = targetRace - leaderCorners;
  const oppCornersNeeded = targetRace - oppCorners;
  const pace = leaderCorners > 0 ? Number((min / leaderCorners).toFixed(1)) : 99;

  const qualified =
    cornersNeeded <= 2 &&
    cornersNeeded > 0 &&
    oppCornersNeeded >= cornersNeeded + 2 &&
    leaderPress >= 65 &&
    pace <= 12;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const prob = Math.min(90, Math.max(70, 72 + (leaderPress - 65) + (oppCornersNeeded - cornersNeeded) * 4));
    bettingTip = generateBettingTip({
      marketCode: "RACE_TO_CORNERS",
      marketName: `Corrida de Escanteios (${targetRace})`,
      targetSelection: `Primeiro a ${targetRace} Cantos: ${leaderTeam}`,
      probabilityPct: prob,
      confidence: prob >= 80 ? 'extrema' : 'alta',
      reasoning: `${leaderTeam} lidera em cantos (${leaderCorners}x${oppCorners}) com pressão ativa de ${leaderPress}% e ritmo de ${pace} min/canto.`,
      actionText: `Apostar em ${leaderTeam} como primeiro a alcançar ${targetRace} escanteios.`,
      match,
    });
  }

  return {
    qualified,
    targetRace,
    leaderTeam,
    leaderSide,
    leaderCorners,
    oppCorners,
    paceMinPerCorner: pace,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 9. JOGO QUENTE & CLIMA DE CARTÃO (OVER CARTÕES)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateJogoQuente(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): JogoQuenteEvaluation {
  if (!config.enableJogoQuenteCards) {
    return { qualified: false, intensity: 'moderada', foulsPerMin: 0, totalYellows: 0, recentFoulsStreak: 0, scoreGap: 0 };
  }

  const min = Math.max(1, match.minute || 1);
  const totalFouls = (match.stats.fouls.home || 0) + (match.stats.fouls.away || 0);
  const totalYellows = (match.stats.yellowCards.home || 0) + (match.stats.yellowCards.away || 0);
  const foulsPerMin = Number((totalFouls / min).toFixed(2));
  const scoreGap = Math.abs((match.score.home || 0) - (match.score.away || 0));

  // Friction logic: high fouls frequency (>= 0.35 fouls/min) + tight score gap (<= 1) + min >= 25
  const isHighFriction = foulsPerMin >= 0.38 && scoreGap <= 1 && min >= 25;
  const isExtremeFriction = (foulsPerMin >= 0.45 && min >= 40) || (totalYellows >= 3 && min >= 50 && scoreGap <= 1);

  const qualified = isHighFriction || isExtremeFriction;
  const intensity = isExtremeFriction ? 'extrema' : isHighFriction ? 'alta' : 'moderada';
  const targetLine = totalYellows + 1.5;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const prob = isExtremeFriction ? 84 : 76;
    bettingTip = generateBettingTip({
      marketCode: "JOGO_QUENTE_CARTOES",
      marketName: `Over Cartões (${targetLine})`,
      targetSelection: `Mais de ${targetLine} Cartões Amarelos / Próximo Cartão`,
      probabilityPct: prob,
      confidence: isExtremeFriction ? 'extrema' : 'alta',
      reasoning: `Partida de alta fricção tática (${totalFouls} faltas, ${foulsPerMin} faltas/min) e placar parelho (${match.score.home}-${match.score.away}).`,
      actionText: `Entrada em Over Cartões ou Próximo Cartão Amarelo na partida`,
      match,
    });
  }

  return {
    qualified,
    intensity,
    foulsPerMin,
    totalYellows,
    recentFoulsStreak: Math.min(5, Math.round(foulsPerMin * 6)),
    scoreGap,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 10. RISCO DE EXPULSÃO (CARTÃO VERMELHO NA PARTIDA)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateRiscoExpulsao(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): RiscoExpulsaoEvaluation {
  if (!config.enableRiscoExpulsao) {
    return { qualified: false, riskLevel: 'alto', targetTeam: "", targetSide: 'home', yellowsOnTeam: 0, foulPressure: 0 };
  }

  const hYellows = match.stats.yellowCards.home || 0;
  const aYellows = match.stats.yellowCards.away || 0;
  const hFouls = match.stats.fouls.home || 0;
  const aFouls = match.stats.fouls.away || 0;
  const hPress = match.stats.pressureIndex.home || 0;
  const aPress = match.stats.pressureIndex.away || 0;

  // Check if home or away team is under severe defensive risk with multiple yellows
  let targetSide: 'home' | 'away' = 'home';
  let yellowsOnTeam = hYellows;
  let foulPressure = hFouls;
  let oppPress = aPress;
  let targetTeam = match.homeTeam.name;

  if (aYellows > hYellows || (aYellows === hYellows && hPress > aPress)) {
    targetSide = 'away';
    yellowsOnTeam = aYellows;
    foulPressure = aFouls;
    oppPress = hPress;
    targetTeam = match.awayTeam.name;
  }

  const min = match.minute || 0;
  const qualified =
    (yellowsOnTeam >= 3 && min >= 45 && oppPress >= 65) ||
    (yellowsOnTeam >= 4 && min >= 60);

  const riskLevel = yellowsOnTeam >= 4 ? 'critico' : 'alto';

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    // Red cards typically have odds between 3.00 and 4.50. A 48-58% estimate is massively +EV!
    const prob = yellowsOnTeam >= 4 ? 58 : 46;
    bettingTip = generateBettingTip({
      marketCode: "RISCO_EXPULSAO",
      marketName: `Cartão Vermelho na Partida: SIM`,
      targetSelection: `Haverá Expulsão / Cartão Vermelho: SIM`,
      probabilityPct: prob,
      confidence: riskLevel === 'critico' ? 'extrema' : 'alta',
      reasoning: `${targetTeam} acumulou ${yellowsOnTeam} cartões amarelos e está sob pressão de ${oppPress}% do adversário no minuto ${min}'.`,
      actionText: `Entrada de altíssimo valor em Cartão Vermelho: SIM (Odds de mercado muito desajustadas)`,
      match,
    });
  }

  return {
    qualified,
    riskLevel,
    targetTeam,
    targetSide,
    yellowsOnTeam,
    foulPressure,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 11. AMBAS MARCAM (BTTS: SIM) - AVALIAÇÃO DOS ÚLTIMOS 10 MINUTOS
// ──────────────────────────────────────────────────────────────────────────
export function evaluateAmbasMarcam(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): AmbasMarcamEvaluation {
  if (!config.enableAmbasMarcamBTTS) {
    return { qualified: false, homeXg: 0, awayXg: 0, homeSot: 0, awaySot: 0, currentScore: "" };
  }

  const min = match.minute || 0;
  const hG = match.score.home || 0;
  const aG = match.score.away || 0;
  const currentScore = `${hG}-${aG}`;

  // Se ambos os times já marcaram, BTTS já bateu
  if (hG > 0 && aG > 0) {
    return { qualified: false, homeXg: match.stats.xG.home, awayXg: match.stats.xG.away, homeSot: match.stats.shotsOnTarget.home, awaySot: match.stats.shotsOnTarget.away, currentScore };
  }

  // Análise estrita da produção ofensiva dos ÚLTIMOS 10 MINUTOS
  const curMin = Math.max(1, min);
  const minStart10 = Math.max(1, curMin - 10);
  const last10Points = (match.momentumTimeline || []).filter(
    (pt) => pt.minute > minStart10 && pt.minute <= curMin
  );

  const homeAttacks10m = match.stats.dangerousAttacksLast10?.home || 0;
  const awayAttacks10m = match.stats.dangerousAttacksLast10?.away || 0;

  const homeShots10m = last10Points.filter((pt) => pt.homeShot).length;
  const awayShots10m = last10Points.filter((pt) => pt.awayShot).length;

  const homeDangPoints10m = last10Points.filter((pt) => pt.homeDangerousAttack).length;
  const awayDangPoints10m = last10Points.filter((pt) => pt.awayDangerousAttack).length;

  const homeEffectiveDang10m = Math.max(homeAttacks10m, homeDangPoints10m);
  const awayEffectiveDang10m = Math.max(awayAttacks10m, awayDangPoints10m);

  const homeAvgPress10m = last10Points.length > 0
    ? Math.round(last10Points.reduce((acc, p) => acc + p.homePressure, 0) / last10Points.length)
    : match.stats.pressureIndex.home;
  const awayAvgPress10m = last10Points.length > 0
    ? Math.round(last10Points.reduce((acc, p) => acc + p.awayPressure, 0) / last10Points.length)
    : match.stats.pressureIndex.away;

  // Critério focado exclusivamente na produção bilateral dos últimos 10 minutos
  const homeActive10m = (homeEffectiveDang10m >= 3 || homeShots10m >= 1 || homeAvgPress10m >= 52);
  const awayActive10m = (awayEffectiveDang10m >= 3 || awayShots10m >= 1 || awayAvgPress10m >= 52);
  const combinedActive10m = (homeEffectiveDang10m + awayEffectiveDang10m >= 6) || (homeShots10m >= 1 && awayShots10m >= 1) || (homeAvgPress10m + awayAvgPress10m >= 110);

  const qualified =
    min >= 18 &&
    min <= 86 &&
    homeActive10m &&
    awayActive10m &&
    combinedActive10m;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const rawProb = 68 + Math.min(22, (homeEffectiveDang10m + awayEffectiveDang10m) * 1.5 + (homeShots10m + awayShots10m) * 4);
    const prob = Math.min(92, Math.max(70, Math.round(rawProb)));

    const minProb = config.minAlertProbabilityPct ?? 50;
    const maxProb = config.maxAlertProbabilityPct ?? 100;
    const isWithinProbRange = prob >= minProb && prob <= maxProb;

    if (isWithinProbRange) {
      bettingTip = generateBettingTip({
        marketCode: "BTTS_YES",
        marketName: `Ambas as Equipes Marcam (BTTS: SIM)`,
        targetSelection: `Ambas Marcam: SIM`,
        probabilityPct: prob,
        confidence: prob >= 82 ? 'extrema' : 'alta',
        reasoning: `Produção bilateral dos últimos 10 minutos: Mandante (${homeEffectiveDang10m} ataques perigosos, ${homeShots10m} chutes no alvo) x Visitante (${awayEffectiveDang10m} ataques perigosos, ${awayShots10m} chutes no alvo) no placar ${currentScore}.`,
        actionText: `Entrada em Ambas Marcam: SIM (Volume ofensivo mútuo nos últimos 10')`,
        match,
        config,
      });
    }
  }

  return {
    qualified: qualified && (bettingTip !== undefined || !config.minAlertProbabilityPct),
    homeXg: Number(match.stats.xG.home.toFixed(2)),
    awayXg: Number(match.stats.xG.away.toFixed(2)),
    homeSot: match.stats.shotsOnTarget.home,
    awaySot: match.stats.shotsOnTarget.away,
    currentScore,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 12. UNDER VALUE & DESACELERAÇÃO (JOGO MORTO / FECHAMENTO DE OVER)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateUnderValue(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): UnderValueEvaluation {
  if (!config.enableUnderValue) {
    return { qualified: false, reason: "", totalXg: 0, variationPct10m: 0, targetMarket: "" };
  }

  const min = match.minute || 0;
  const totalGoals = (match.score.home || 0) + (match.score.away || 0);
  const totalXg = (match.stats.xG.home || 0) + (match.stats.xG.away || 0);
  const totalSot = (match.stats.shotsOnTarget.home || 0) + (match.stats.shotsOnTarget.away || 0);

  // Intervalo de tempo e limiares configuráveis
  const minMinute = config.underValueMinMinute ?? 25;
  const maxMinute = config.underValueMaxMinute ?? 78;
  const maxXg = config.underValueMaxXg ?? 0.60;
  const maxSot = config.underValueMaxSot ?? 2;

  // Critérios: tempo dentro da janela configurada, baixa produção ofensiva (xG baixo > 0 e poucos chutes a gol)
  // xG DEVE ser maior que 0.05 (elimina falsos positivos com xG 0 ou ausência de dados de xG na 1ª varredura)
  const qualified =
    min >= minMinute &&
    min <= maxMinute &&
    totalGoals <= 1 &&
    totalXg >= 0.05 &&
    totalXg <= maxXg &&
    totalSot <= maxSot;

  const targetLine = totalGoals + 1.5;
  const targetMarket = `Under ${targetLine} Gols / Lay Próximo Gol`;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const prob = Math.min(92, Math.max(74, 76 + Math.round((maxXg - totalXg) * 25)));
    bettingTip = generateBettingTip({
      marketCode: "UNDER_VALUE",
      marketName: `Under Value (${targetMarket})`,
      targetSelection: `Menos de ${targetLine} Gols`,
      probabilityPct: prob,
      confidence: 'alta',
      reasoning: `Partida travada no meio-campo com ritmo lento (xG Total: ${totalXg.toFixed(2)} ≤ teto ${maxXg}, apenas ${totalSot} finalizações certas no intervalo configurado de ${minMinute}'-${maxMinute}').`,
      actionText: `Entrada defensiva em Under Gols ou Lay ao Próximo Gol`,
      match,
      config,
    });
  }

  return {
    qualified: qualified && (bettingTip !== undefined || !config.minAlertProbabilityPct),
    reason: qualified ? `Baixa produção ofensiva aos ${min}' (xG: ${totalXg.toFixed(2)}, Chutes no Alvo: ${totalSot}) na janela ${minMinute}'-${maxMinute}'` : "Ritmo normal",
    totalXg: Number(totalXg.toFixed(2)),
    variationPct10m: -40,
    targetMarket,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 13. VIRADA IMPROVÁVEL (LAY ZEBRA / DNB FAVORITO)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateViradaImprovavel(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): ViradaImprovavelEvaluation {
  if (!config.enableViradaImprovavel) {
    return { qualified: false, underdogTeam: "", favoriteTeam: "", favoriteSide: 'home', score: "", favoritePressure: 0, favoriteXg: 0 };
  }

  const min = match.minute || 0;
  const hG = match.score.home || 0;
  const aG = match.score.away || 0;
  const hXg = match.stats.xG.home || 0;
  const aXg = match.stats.xG.away || 0;
  const hPress = match.stats.pressureIndex.home || 0;
  const aPress = match.stats.pressureIndex.away || 0;

  // Case A: Home is favorite trailing by 1 (e.g. 0-1 or 1-2) with crushing pressure
  const homeFavoriteTrailing =
    hG < aG &&
    aG - hG === 1 &&
    hPress >= 72 &&
    hXg >= 1.2 &&
    aXg < 0.6 &&
    min >= 40 &&
    min <= 82;

  // Case B: Away is favorite trailing by 1
  const awayFavoriteTrailing =
    aG < hG &&
    hG - aG === 1 &&
    aPress >= 72 &&
    aXg >= 1.2 &&
    hXg < 0.6 &&
    min >= 40 &&
    min <= 82;

  const qualified = homeFavoriteTrailing || awayFavoriteTrailing;
  const favoriteSide: 'home' | 'away' = homeFavoriteTrailing ? 'home' : 'away';
  const favoriteTeam = favoriteSide === 'home' ? match.homeTeam.name : match.awayTeam.name;
  const underdogTeam = favoriteSide === 'home' ? match.awayTeam.name : match.homeTeam.name;
  const favoritePressure = favoriteSide === 'home' ? hPress : aPress;
  const favoriteXg = favoriteSide === 'home' ? hXg : aXg;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const prob = 74;
    bettingTip = generateBettingTip({
      marketCode: "VIRADA_IMPROVAVEL",
      marketName: `Virada / Reação de ${favoriteTeam}`,
      targetSelection: `Empate Anula (DNB) ${favoriteTeam} / Lay ${underdogTeam}`,
      probabilityPct: prob,
      confidence: 'alta',
      reasoning: `${favoriteTeam} perde por 1 gol injustamente sob forte domínio (Pressão: ${favoritePressure}%, xG: ${favoriteXg.toFixed(2)} vs ${underdogTeam} xG: ${(favoriteSide === 'home' ? aXg : hXg).toFixed(2)}).`,
      actionText: `Entrar em Empate Anula (DNB) ${favoriteTeam} ou Lay à Zebra (${underdogTeam})`,
      match,
    });
  }

  return {
    qualified,
    underdogTeam,
    favoriteTeam,
    favoriteSide,
    score: `${hG}-${aG}`,
    favoritePressure,
    favoriteXg: Number(favoriteXg.toFixed(2)),
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// 14. CASHOUT PROATIVO (SINAL DE PROTEÇÃO / FECHAMENTO DE POSIÇÃO)
// ──────────────────────────────────────────────────────────────────────────
export function evaluateCashoutProativo(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): CashoutProativoEvaluation {
  if (!config.enableCashoutProativo) {
    return { qualified: false, leadingTeam: "", leadingSide: 'home', pressureDropPct: 0, opponentPressureRecent: 0, minute: 0, score: "" };
  }

  const min = match.minute || 0;
  const hG = match.score.home || 0;
  const aG = match.score.away || 0;
  const hPress = match.stats.pressureIndex.home || 0;
  const aPress = match.stats.pressureIndex.away || 0;

  // Only relevant in late game (70'+) when one team leads by 1 goal
  const isLate = min >= 70 && min <= 90;
  const scoreDiff = Math.abs(hG - aG);

  if (!isLate || scoreDiff !== 1) {
    return { qualified: false, leadingTeam: "", leadingSide: 'home', pressureDropPct: 0, opponentPressureRecent: 0, minute: min, score: `${hG}-${aG}` };
  }

  const leadingSide: 'home' | 'away' = hG > aG ? 'home' : 'away';
  const leadingTeam = leadingSide === 'home' ? match.homeTeam.name : match.awayTeam.name;
  const opponentTeam = leadingSide === 'home' ? match.awayTeam.name : match.homeTeam.name;
  const leaderPress = leadingSide === 'home' ? hPress : aPress;
  const oppPress = leadingSide === 'home' ? aPress : hPress;

  // Trigger when leader pressure dropped low (< 35) and opponent is surging (oppPress >= 70)
  const qualified = leaderPress < 35 && oppPress >= 70;

  let bettingTip: BettingTipData | undefined = undefined;
  if (qualified) {
    const prob = 82; // 82% risk of pressure / goal
    bettingTip = generateBettingTip({
      marketCode: "CASHOUT_PROATIVO",
      marketName: `Sinal de Cashout / Hedge (${leadingTeam})`,
      targetSelection: `Encerrar Aposta / Cashout de ${leadingTeam}`,
      probabilityPct: prob,
      confidence: 'extrema',
      reasoning: `${leadingTeam} vencia por ${hG}-${aG}, mas perdeu completamente o controle do jogo (pressão caiu para ${leaderPress}% enquanto ${opponentTeam} pressiona a ${oppPress}%).`,
      actionText: `Realizar Cashout imediato ou Hedge defensivo no empate/gol de ${opponentTeam}`,
      match,
    });
  }

  return {
    qualified,
    leadingTeam,
    leadingSide,
    pressureDropPct: Math.round(100 - leaderPress),
    opponentPressureRecent: oppPress,
    minute: min,
    score: `${hG}-${aG}`,
    bettingTip,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// MASTER AGGREGATOR: EVALUATE ALL RULES FOR A MATCH
// ──────────────────────────────────────────────────────────────────────────
export function evaluateAllMatchRules(
  match: Match,
  config: OperationalRulesConfig = DEFAULT_RULES_CONFIG
): MatchRulesAnalysis {
  // Check if match is within the configured minute window for alerts
  const minMin = Number(config.minMinuteAlert ?? 0);
  const maxMin = Number(config.maxMinuteAlert ?? 90);
  const curMin = Number(match.minute ?? 0);
  const isFinished = match.status === "FT" || match.status === "FINISHED" || match.status === "ENCERRADO" || curMin >= 90;

  if (isFinished || curMin < minMin || curMin > maxMin) {
    const reasonText = isFinished ? "Partida encerrada" : `Fora da Janela de Minutos (${minMin}'-${maxMin}')`;
    return {
      matchId: match.id,
      ratioConfigured: config.chancesPerGoalRatio,
      codigo31: {
        alertType: null,
        shouldAlert: false,
        reason: reasonText,
        level: null,
        market: null,
        bucket: 0,
        totalCc: 0,
        homeCc: 0,
        awayCc: 0,
        totalGoals: 0,
        homeScore: match.score.home,
        awayScore: match.score.away,
        ccRate: 0,
        expectedGoalsByCc: 0,
        isDevendoGol: false,
        saldoGolsDevidos: 0,
        ratioUsed: config.chancesPerGoalRatio,
        dominantTeam: null,
        dominantName: "",
        dominantCc: 0,
        oppCc: 0,
        ccDiff: 0,
        expectedDominantGoalsByCc: 0,
        isDominantDevendoGol: false,
        saldoGolsDominante: 0,
        isDominantTrailing: false,
        dominantLead: 0,
        title: "",
        emoji: "",
        motivo: reasonText,
        leitura: "",
        formattedTelegram: "",
      },
      tripleDebt: {
        tripleDebtFormed: false,
        scope: "none",
        scopeSide: null,
        debtorTeamName: undefined,
        ccInScope: 0,
        xgInScope: 0,
        xgotInScope: 0,
        goalsInScope: 0,
        expectedGoalsByCc: 0,
        ccDebt: false,
        xgDebt: false,
        xgotDebt: false,
        failedReasons: [reasonText],
        blockReason: reasonText,
        wouldBlockSignal: false,
        statusBadge: "Sem Débito",
      },
      pressaoVendavel: {
        qualified: false,
        side: null,
        team: "",
        minute: curMin,
        score: `${match.score.home} - ${match.score.away}`,
        tese: "",
        fails: [reasonText],
        metrics: {
          cc: 0,
          xg: 0,
          xgot: 0,
          shots: 0,
          sot: 0,
          sotPct: 0,
          posse: 50,
          toquesArea: 0,
          oppXg: 0,
        },
      },
      dominantTrailing: {
        dominantSide: null,
        dominantScore: 0,
        opponentScore: 0,
        dominantIsTrailing: false,
        dominantTrailingBy: 0,
        dominantReactionConfirmed: false,
        livePressureStatus: "neutro",
        entryAllowed: false,
        blockReason: reasonText,
        status: "NOT_TRAILING",
      },
      imminentGoal: {
        isImminent: false,
        intensity: "nenhuma",
        variationPct5m: 0,
        totalChancesLast5: 0,
        totalChancesPrev5: 0,
        homeChancesLast5: 0,
        awayChancesLast5: 0,
        effectiveDebt: 0,
        targetMarket: null,
        beneficiaryTeam: undefined,
        triggerReason: reasonText,
        confidenceScore: 0,
        title: "",
        actionText: "",
      },
      funilCantos: {
        qualified: false,
        phase: null,
        minute: curMin,
        currentCorners: (match.stats.corners.home + match.stats.corners.away),
        targetLine: "",
        attacksPerMinLast10: 0,
        blockedShotsLast10: 0,
      },
      raceToCorners: {
        qualified: false,
        targetRace: 5,
        leaderTeam: match.homeTeam.name,
        leaderSide: "home",
        leaderCorners: match.stats.corners.home,
        oppCorners: match.stats.corners.away,
        paceMinPerCorner: 0,
      },
      jogoQuente: {
        qualified: false,
        intensity: "moderada",
        foulsPerMin: 0,
        totalYellows: (match.stats.yellowCards.home + match.stats.yellowCards.away),
        recentFoulsStreak: 0,
        scoreGap: Math.abs(match.score.home - match.score.away),
      },
      riscoExpulsao: {
        qualified: false,
        riskLevel: "alto",
        targetTeam: match.homeTeam.name,
        targetSide: "home",
        yellowsOnTeam: match.stats.yellowCards.home,
        foulPressure: 0,
      },
      ambasMarcam: {
        qualified: false,
        homeXg: match.stats.xG.home,
        awayXg: match.stats.xG.away,
        homeSot: match.stats.shotsOnTarget.home,
        awaySot: match.stats.shotsOnTarget.away,
        currentScore: `${match.score.home} - ${match.score.away}`,
      },
      underValue: {
        qualified: false,
        reason: reasonText,
        totalXg: (match.stats.xG.home + match.stats.xG.away),
        variationPct10m: 0,
        targetMarket: "Under Gols",
      },
      viradaImprovavel: {
        qualified: false,
        underdogTeam: match.awayTeam.name,
        favoriteTeam: match.homeTeam.name,
        favoriteSide: "home",
        score: `${match.score.home} - ${match.score.away}`,
        favoritePressure: 0,
        favoriteXg: 0,
      },
      cashoutProativo: {
        qualified: false,
        leadingTeam: "",
        leadingSide: "home",
        pressureDropPct: 0,
        opponentPressureRecent: 0,
        minute: curMin,
        score: `${match.score.home} - ${match.score.away}`,
      },
      traditionalSignals: [],
      hasActiveOperationalAlert: false,
      primaryAlertBadge: undefined,
      activeTips: [],
    };
  }

  const codigo31 = evaluateCodigo31(match, config);
  const tripleDebt = evaluateTripleDebt(match, config);
  const pressaoVendavel = evaluatePressaoVendavel(match, config);
  const dominantTrailing = evaluateDominantTrailing(match, config);
  const imminentGoal = evaluateImminentGoal(match, config);
  const funilCantos = evaluateFunilCantos(match, config);
  const raceToCorners = evaluateRaceToCorners(match, config);
  const jogoQuente = evaluateJogoQuente(match, config);
  const riscoExpulsao = evaluateRiscoExpulsao(match, config);
  const ambasMarcam = evaluateAmbasMarcam(match, config);
  const underValue = evaluateUnderValue(match, config);
  const viradaImprovavel = evaluateViradaImprovavel(match, config);
  const cashoutProativo = evaluateCashoutProativo(match, config);
  const traditionalSignals = evaluateTraditionalSignals(match, config);

  // Collect all active betting tips with their probability and bookmaker odds
  const activeTips: BettingTipData[] = [];
  if (codigo31.shouldAlert && codigo31.bettingTip) activeTips.push(codigo31.bettingTip);
  if (tripleDebt.tripleDebtFormed && tripleDebt.bettingTip) activeTips.push(tripleDebt.bettingTip);
  if (pressaoVendavel.qualified && pressaoVendavel.bettingTip) activeTips.push(pressaoVendavel.bettingTip);
  if (imminentGoal.isImminent && imminentGoal.bettingTip) activeTips.push(imminentGoal.bettingTip);
  if (funilCantos.qualified && funilCantos.bettingTip) activeTips.push(funilCantos.bettingTip);
  if (raceToCorners.qualified && raceToCorners.bettingTip) activeTips.push(raceToCorners.bettingTip);
  if (jogoQuente.qualified && jogoQuente.bettingTip) activeTips.push(jogoQuente.bettingTip);
  if (riscoExpulsao.qualified && riscoExpulsao.bettingTip) activeTips.push(riscoExpulsao.bettingTip);
  if (ambasMarcam.qualified && ambasMarcam.bettingTip) activeTips.push(ambasMarcam.bettingTip);
  if (underValue.qualified && underValue.bettingTip) activeTips.push(underValue.bettingTip);
  if (viradaImprovavel.qualified && viradaImprovavel.bettingTip) activeTips.push(viradaImprovavel.bettingTip);
  if (cashoutProativo.qualified && cashoutProativo.bettingTip) activeTips.push(cashoutProativo.bettingTip);

  const hasActiveOperationalAlert =
    codigo31.shouldAlert ||
    tripleDebt.tripleDebtFormed ||
    pressaoVendavel.qualified ||
    (config.enableImminentGoal && imminentGoal.isImminent && (imminentGoal.intensity === 'extrema' || imminentGoal.intensity === 'alta')) ||
    funilCantos.qualified ||
    raceToCorners.qualified ||
    jogoQuente.qualified ||
    riscoExpulsao.qualified ||
    ambasMarcam.qualified ||
    underValue.qualified ||
    viradaImprovavel.qualified ||
    cashoutProativo.qualified;

  let primaryAlertBadge: MatchRulesAnalysis["primaryAlertBadge"] = undefined;
  
  if (config.enableImminentGoal && imminentGoal.isImminent && imminentGoal.intensity === 'extrema') {
    primaryAlertBadge = {
      emoji: "🚨",
      label: `GOL IMINENTE (+${imminentGoal.variationPct5m}% em 5')`,
      level: "premium",
      market: imminentGoal.targetMarket === "BACK_DOMINANTE" ? "back" : "over",
    };
  } else if (codigo31.shouldAlert && codigo31.level && codigo31.market) {
    primaryAlertBadge = {
      emoji: codigo31.emoji,
      label: codigo31.title,
      level: codigo31.level,
      market: codigo31.market,
    };
  } else if (tripleDebt.tripleDebtFormed) {
    const debtorLabel = tripleDebt.scope === "unilateral" && tripleDebt.debtorTeamName
      ? `TRINCA DE DÍVIDAS (${tripleDebt.debtorTeamName})`
      : `TRINCA DE DÍVIDAS (${tripleDebt.scope.toUpperCase()})`;
    primaryAlertBadge = {
      emoji: "💎",
      label: debtorLabel,
      level: "premium",
      market: tripleDebt.scope === "unilateral" ? "back" : "over",
    };
  } else if (funilCantos.qualified) {
    primaryAlertBadge = {
      emoji: "🚩",
      label: `FUNIL DE CANTOS (${funilCantos.phase === 'HT_LIMITE' ? 'HT' : 'FT'})`,
      level: "forte",
      market: "corners",
    };
  } else if (config.enableImminentGoal && imminentGoal.isImminent && imminentGoal.intensity === 'alta') {
    primaryAlertBadge = {
      emoji: "🚨",
      label: `GOL IMINENTE (+${imminentGoal.variationPct5m}%)`,
      level: "forte",
      market: "over",
    };
  } else if (pressaoVendavel.qualified) {
    primaryAlertBadge = {
      emoji: "⚡",
      label: `PRESSÃO VENDÁVEL (${pressaoVendavel.team})`,
      level: "forte",
      market: "back",
    };
  } else if (riscoExpulsao.qualified) {
    primaryAlertBadge = {
      emoji: "🟥",
      label: `RISCO DE EXPULSÃO (${riscoExpulsao.targetTeam})`,
      level: "premium",
      market: "cards",
    };
  } else if (ambasMarcam.qualified) {
    primaryAlertBadge = {
      emoji: "🎯",
      label: "AMBAS MARCAM (BTTS: SIM)",
      level: "forte",
      market: "btts",
    };
  } else if (cashoutProativo.qualified) {
    primaryAlertBadge = {
      emoji: "🛡️",
      label: `SINAL DE CASHOUT (${cashoutProativo.leadingTeam})`,
      level: "premium",
      market: "under",
    };
  }

  return {
    matchId: match.id,
    ratioConfigured: config.chancesPerGoalRatio,
    codigo31,
    tripleDebt,
    pressaoVendavel,
    dominantTrailing,
    imminentGoal,
    funilCantos,
    raceToCorners,
    jogoQuente,
    riscoExpulsao,
    ambasMarcam,
    underValue,
    viradaImprovavel,
    cashoutProativo,
    traditionalSignals,
    hasActiveOperationalAlert,
    primaryAlertBadge,
    activeTips,
  };
}
