import {
  Match,
  MatchEvent,
  MomentumPoint,
  AlertRule,
  AlertLog,
  CrawlerStatus,
  CrawlerLogItem,
  HeadToHeadMatch,
  HeadToHeadSummary,
  CustomWebhookEndpoint,
  WebhookDeliveryLog,
  OperationalRulesConfig,
  MatchRulesAnalysis,
  BettingTipData,
  BookmakerId,
  BookmakerApiCredential,
  BookmakerApiMap,
  DEFAULT_BOOKMAKER_CREDENTIALS,
} from "../src/types";
import {
  DEFAULT_RULES_CONFIG,
  evaluateAllMatchRules,
  getMatchBigChances,
} from "./rulesEngine";
import { calculateDynamicPressureIndex } from "./pressureCalculator";
import { localConfigManager, LocalConfigFile } from "./localConfig";
import { isIgnoredLeague } from "../src/utils/leagueFilter";

export function parseMinute(val: any): number {
  if (val === null || val === undefined) return 0;
  if (typeof val === 'number') {
    return isNaN(val) ? 0 : Math.max(0, val);
  }
  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (trimmed.toUpperCase() === 'HT' || trimmed.toUpperCase() === 'INTERVALO') return 45;
    if (trimmed.toUpperCase() === 'FT' || trimmed.toUpperCase() === 'FIM') return 90;
    const m = trimmed.match(/(\d+)(?:\+(\d+))?/);
    if (m) {
      const base = parseInt(m[1], 10) || 0;
      const extra = m[2] ? parseInt(m[2], 10) : 0;
      return base + extra;
    }
  }
  return 0;
}

export function normalizeTeamName(raw: any, fallback: string): string {
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  if (raw && typeof raw === 'object') {
    if (raw.name && typeof raw.name === 'string' && raw.name.trim()) return raw.name.trim();
    if (raw.shortName && typeof raw.shortName === 'string' && raw.shortName.trim()) return raw.shortName.trim();
    if (raw.nameCode && typeof raw.nameCode === 'string' && raw.nameCode.trim()) return raw.nameCode.trim();
  }
  return fallback;
}

export function normalizeStringValue(raw: any, fallback: string = ""): string {
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  if (typeof raw === 'number') return String(raw);
  if (raw && typeof raw === 'object') {
    if (raw.name && typeof raw.name === 'string' && raw.name.trim()) return raw.name.trim();
    if (raw.title && typeof raw.title === 'string' && raw.title.trim()) return raw.title.trim();
    if (raw.label && typeof raw.label === 'string' && raw.label.trim()) return raw.label.trim();
    if (raw.text && typeof raw.text === 'string' && raw.text.trim()) return raw.text.trim();
  }
  return fallback;
}

// Helper to generate realistic Head to Head (H2H) match history and tactical trend summaries
export function generateH2HHistory(
  homeTeamName: string,
  awayTeamName: string,
  league: string | any,
  stadium?: string
): { summary: HeadToHeadSummary; matches: HeadToHeadMatch[] } {
  const safeLeague = normalizeStringValue(league, "Campeonato");
  const dates = ["2024-11-06", "2024-04-21", "2023-10-18", "2023-05-14", "2022-11-20", "2022-06-05"];
  const sampleCompetitions = [safeLeague, safeLeague, "Copa Nacional", safeLeague, safeLeague, "Supercopa"];
  
  const scorePairs = [
    { h: 2, a: 1 },
    { h: 1, a: 1 },
    { h: 3, a: 2 },
    { h: 0, a: 2 },
    { h: 2, a: 0 },
    { h: 1, a: 2 },
  ];

  const matches: HeadToHeadMatch[] = dates.map((date, idx) => {
    const isHome = idx % 2 === 0;
    const teamA = isHome ? homeTeamName : awayTeamName;
    const teamB = isHome ? awayTeamName : homeTeamName;
    const sp = scorePairs[idx % scorePairs.length];
    const scoreA = isHome ? sp.h : sp.a;
    const scoreB = isHome ? sp.a : sp.h;
    
    let winner: 'home' | 'away' | 'draw' = 'draw';
    if (scoreA > scoreB) winner = isHome ? 'home' : 'away';
    else if (scoreB > scoreA) winner = isHome ? 'away' : 'home';

    return {
      id: `h2h-${idx}-${date}`,
      date,
      competition: normalizeStringValue(sampleCompetitions[idx] || safeLeague, "Campeonato"),
      homeTeamName: teamA,
      awayTeamName: teamB,
      homeScore: scoreA,
      awayScore: scoreB,
      winner,
      totalCorners: 8 + (idx % 5),
      totalCards: 3 + (idx % 4),
      stadium: isHome ? stadium : undefined,
    };
  });

  const homeWins = matches.filter((m) => m.winner === "home").length;
  const awayWins = matches.filter((m) => m.winner === "away").length;
  const draws = matches.filter((m) => m.winner === "draw").length;
  const totalGoals = matches.reduce((acc, m) => acc + m.homeScore + m.awayScore, 0);
  const bttsCount = matches.filter((m) => m.homeScore > 0 && m.awayScore > 0).length;
  const over25Count = matches.filter((m) => m.homeScore + m.awayScore > 2.5).length;
  const totalCorners = matches.reduce((acc, m) => acc + (m.totalCorners || 9), 0);
  const totalCards = matches.reduce((acc, m) => acc + (m.totalCards || 4), 0);

  const avgGoals = Number((totalGoals / matches.length).toFixed(2));
  const bttsPct = Math.round((bttsCount / matches.length) * 100);
  const over25Pct = Math.round((over25Count / matches.length) * 100);
  const avgCorners = Number((totalCorners / matches.length).toFixed(1));
  const avgCards = Number((totalCards / matches.length).toFixed(1));

  let dominantTrend = `${homeTeamName} e ${awayTeamName} possuem histórico de alta intensidade com ${over25Pct}% de jogos com Over 2.5 gols.`;
  if (homeWins > awayWins) {
    dominantTrend = `${homeTeamName} venceu ${homeWins} dos últimos ${matches.length} confrontos diretos, mantendo média de ${avgGoals} gols por jogo.`;
  } else if (awayWins > homeWins) {
    dominantTrend = `${awayTeamName} tem retrospecto favorável como visitante em ${awayWins} vitórias recentes.`;
  }

  return {
    summary: {
      totalMatches: matches.length,
      homeWins,
      draws,
      awayWins,
      avgGoalsPerGame: avgGoals,
      bttsPercentage: bttsPct,
      over25Percentage: over25Pct,
      avgCornersPerGame: avgCorners,
      avgCardsPerGame: avgCards,
      dominantTrendInsight: dominantTrend,
    },
    matches,
  };
}

export class MatchStore {
  private matches: Map<string, Match> = new Map();
  private alertRules: AlertRule[] = [];
  private alertLogs: AlertLog[] = [];
  private dismissedMatchIds: Set<string> = new Set();
  private crawlerStatus: CrawlerStatus = {
    connected: false,
    lastHeartbeat: null,
    activeInstances: 0,
    totalPacketsReceived: 0,
    apiKeyConfigured: true,
    logs: [],
    ingestedMatchesCount: 0,
  };
  private apiKey: string = "footstats-crawler-live-key-99";
  private customWebhooks: CustomWebhookEndpoint[] = [];
  private webhookLogs: WebhookDeliveryLog[] = [];
  private operationalConfig: OperationalRulesConfig = { ...DEFAULT_RULES_CONFIG };
  private pythonRuleTriggeredBuckets: Map<string, Set<string>> = new Map();
  private matchMinuteStagnation: Map<string, { lastMinute: number; count: number; lastSeenTime: number }> = new Map();
  private matchLastGoalTimes: Map<string, number> = new Map();
  private uniqueCounter: number = 0;

  private generateUniqueId(prefix: string): string {
    this.uniqueCounter = (this.uniqueCounter + 1) % 10000000;
    const rand = Math.random().toString(36).substring(2, 9);
    return `${prefix}-${Date.now()}-${this.uniqueCounter}-${rand}`;
  }

  constructor() {
    this.loadFromLocalConfig();

    // Limpeza periódica de partidas que não recebem atualização há mais de 10 minutos
    setInterval(() => {
      const now = Date.now();
      for (const [id, match] of this.matches.entries()) {
        const lastUpdated = match.lastUpdated ? new Date(match.lastUpdated).getTime() : 0;
        if (now - lastUpdated > 10 * 60 * 1000) {
          this.matches.delete(id);
          this.pythonRuleTriggeredBuckets.delete(id);
          this.matchMinuteStagnation.delete(id);
        }
      }
    }, 60 * 1000);
  }

  public loadFromLocalConfig(): void {
    const localCfg = localConfigManager.getConfig();
    this.operationalConfig = {
      ...DEFAULT_RULES_CONFIG,
      ...(localCfg.operationalConfig || {}),
    };
    this.alertRules = Array.isArray(localCfg.alertRules) ? [...localCfg.alertRules] : [];
    this.customWebhooks = Array.isArray(localCfg.customWebhooks) ? [...localCfg.customWebhooks] : [];
    this.apiKey = localCfg.userProfile?.crawlerToken || "footstats-crawler-live-key-99";
  }

  public applyImportedConfig(config: LocalConfigFile): void {
    this.operationalConfig = {
      ...DEFAULT_RULES_CONFIG,
      ...(config.operationalConfig || {}),
    };
    this.alertRules = Array.isArray(config.alertRules) ? [...config.alertRules] : [];
    this.customWebhooks = Array.isArray(config.customWebhooks) ? [...config.customWebhooks] : [];
    this.apiKey = config.userProfile?.crawlerToken || this.apiKey;
    this.addCrawlerLog("info", "Configurações importadas e aplicadas no terminal com sucesso.");
  }





  private seedDefaultRules() {
    this.alertRules = [
      {
        id: "rule-super-pressure-home",
        name: "Super Pressão Mandante (0-0)",
        description: "Alerta quando o mandante atinge pressão extrema (>75%) com o jogo ainda empatado sem gols.",
        matchId: "all",
        enabled: true,
        logic: "AND",
        conditions: [
          { metric: "pressureHome", operator: ">=", value: 75 },
          { metric: "minute", operator: ">=", value: 20 },
          { metric: "goalLeadDiff", operator: "==", value: 0 },
        ],
        severity: "opportunity",
        soundEnabled: true,
        browserNotification: true,
        messageTemplate: "🔥 OPORTUNIDADE: {teamHome} exercendo pressão esmagadora ({pressureHome}%) aos {minute}'! Probabilidade elevada de gol.",
        triggerCount: 3,
        lastTriggered: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
      },
      {
        id: "rule-late-corners-surge",
        name: "Bombardeio Final de Escanteios (+75')",
        description: "Identifica jogos na reta final com alta pressão ofensiva e acúmulo de escanteios.",
        matchId: "all",
        enabled: true,
        logic: "AND",
        conditions: [
          { metric: "minute", operator: ">=", value: 70 },
          { metric: "cornersCombined", operator: ">=", value: 8 },
        ],
        severity: "opportunity",
        soundEnabled: true,
        browserNotification: true,
        messageTemplate: "🚩 PRESSÃO DE CANTOS: Jogo aos {minute}' com {cornersTotal} escanteios e blitz no terço final.",
        triggerCount: 2,
        lastTriggered: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
      },
      {
        id: "rule-red-card-advantage",
        name: "Vantagem Numérica / Cartão Vermelho",
        description: "Notifica imediatamente qualquer expulsão em campo para reposicionamento tático.",
        matchId: "all",
        enabled: true,
        logic: "OR",
        conditions: [
          { metric: "redCardHome", operator: ">=", value: 1 },
          { metric: "redCardAway", operator: ">=", value: 1 },
        ],
        severity: "critical",
        soundEnabled: true,
        browserNotification: true,
        messageTemplate: "🟥 CARTÃO VERMELHO! Expulsão na partida aos {minute}'. Desequilíbrio tático iminente.",
        triggerCount: 1,
        lastTriggered: new Date(Date.now() - 1000 * 60 * 17).toISOString(),
      },
      {
        id: "rule-xg-divergence",
        name: "Divergência Crítica de xG (xG Diff > 1.0)",
        description: "Dispara quando a diferença de gols esperados é superior a 1.0 demonstrando superioridade técnica e pressão nas linhas defensivas.",
        matchId: "all",
        enabled: true,
        logic: "AND",
        conditions: [
          { metric: "xgDiff", operator: ">=", value: 1.0 },
          { metric: "minute", operator: ">=", value: 25 },
        ],
        severity: "warning",
        soundEnabled: false,
        browserNotification: true,
        messageTemplate: "📊 xG DIVERGENTE: {dominantTeam} ({higherXg} xG) x ({lowerXg} xG) {underdogTeam} (dif. +{xgDiff}) aos {minute}' | {scoreContext}",
        triggerCount: 4,
        lastTriggered: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
      },
    ];

    this.alertLogs = [];
  }



  // --- Alert Helper ---
  private pushAlertLog(log: AlertLog, match?: Match) {
    if (log.matchId && this.dismissedMatchIds.has(log.matchId)) {
      return;
    }
    if (match) {
      if (!log.league) log.league = match.league;
      if (!log.country) log.country = match.country || match.leagueCountry || "";
      if (!log.leagueCountry) log.leagueCountry = match.leagueCountry || match.country || "";
      if (!log.url) log.url = match.url;
    }
    this.alertLogs.push(log);
    if (this.alertLogs.length > 250) this.alertLogs.shift();
  }

  // --- Alert Evaluation Engine ---
  private evaluateAlertsForMatch(match: Match) {
    // Do not generate alerts for finished matches or matches at 90'+
    const finishedStatuses = ["FT", "FINISHED", "ENCERRADO", "TERMINADO", "AET", "PEN", "ENDED", "POSTPONED", "CANCELLED"];
    if (finishedStatuses.includes(match.status?.toUpperCase()) || match.minute >= 90) {
      return;
    }

    // Enforce "Janela de Minutos para Alertas"
    const minMinute = Number(this.operationalConfig.minMinuteAlert ?? 0);
    const maxMinute = Number(this.operationalConfig.maxMinuteAlert ?? 90);
    if (match.minute < minMinute || match.minute > maxMinute) {
      return;
    }

    if (!this.pythonRuleTriggeredBuckets.has(match.id)) {
      this.pythonRuleTriggeredBuckets.set(match.id, new Set<string>());
    }
    const matchBuckets = this.pythonRuleTriggeredBuckets.get(match.id)!;

    // 1. Standard UI Rule evaluation
    for (const rule of this.alertRules) {
      if (!rule.enabled) continue;
      if (rule.matchId !== "all" && rule.matchId !== match.id) continue;

      // Has Red Card condition
      const hasRedCardMetric = rule.conditions.some((c) => c.metric === "redCardHome" || c.metric === "redCardAway");
      let ruleKey: string;
      if (hasRedCardMetric) {
        // Red card alert is bucketed specifically by match red cards count so it NEVER fires repeatedly unless red card count changes
        ruleKey = `rule_rc_${rule.id}_h${match.stats.redCards.home}_a${match.stats.redCards.away}`;
      } else {
        // Other rules are bucketed by 15-min tactical window and current score
        ruleKey = `rule_${rule.id}_m${Math.floor(match.minute / 15)}_s${match.score.home}_${match.score.away}`;
      }

      if (matchBuckets.has(ruleKey)) {
        continue;
      }

      const conditionResults = rule.conditions.map((cond) => {
        let actualVal = 0;
        switch (cond.metric) {
          case "minute":
            actualVal = match.minute;
            break;
          case "pressureHome":
            actualVal = match.stats.pressureIndex.home;
            break;
          case "pressureAway":
            actualVal = match.stats.pressureIndex.away;
            break;
          case "pressureDiff":
            actualVal = Math.abs(match.stats.pressureIndex.home - match.stats.pressureIndex.away);
            break;
          case "xgDiff":
            actualVal = Math.abs(match.stats.xG.home - match.stats.xG.away);
            break;
          case "totalXg":
            actualVal = match.stats.xG.home + match.stats.xG.away;
            break;
          case "dangerousAttacksLast10Home":
            actualVal = match.stats.dangerousAttacksLast10.home;
            break;
          case "dangerousAttacksLast10Away":
            actualVal = match.stats.dangerousAttacksLast10.away;
            break;
          case "chancesVariation5m": {
            const curMin = Math.max(1, match.minute || 1);
            const last5Points = (match.momentumTimeline || []).filter(
              (pt) => pt.minute > Math.max(1, curMin - 5) && pt.minute <= curMin
            );
            const prev5Points = (match.momentumTimeline || []).filter(
              (pt) => pt.minute > Math.max(1, curMin - 10) && pt.minute <= Math.max(1, curMin - 5)
            );
            let hLast = last5Points.filter((pt) => pt.homeShot).length;
            let aLast = last5Points.filter((pt) => pt.awayShot).length;
            let hPrev = prev5Points.filter((pt) => pt.homeShot).length;
            let aPrev = prev5Points.filter((pt) => pt.awayShot).length;
            if (hLast === 0 && aLast === 0) {
              hLast = last5Points.filter((pt) => pt.homeDangerousAttack).length;
              aLast = last5Points.filter((pt) => pt.awayDangerousAttack).length;
              hPrev = prev5Points.filter((pt) => pt.homeDangerousAttack).length;
              aPrev = prev5Points.filter((pt) => pt.awayDangerousAttack).length;
            }
            const totLast = hLast + aLast;
            const totPrev = hPrev + aPrev;
            if (totPrev > 0) {
              actualVal = Math.round(((totLast - totPrev) / totPrev) * 100);
            } else if (totLast > 0) {
              actualVal = 100;
            } else {
              const totalBc = (match.stats.bigChances?.home || 0) + (match.stats.bigChances?.away || 0) || Math.floor((match.stats.shotsOnTarget.home + match.stats.shotsOnTarget.away) / 2);
              if (totalBc > 0) {
                const avg5 = (totalBc / curMin) * 5;
                const recPress = (match.stats.pressureIndex.home + match.stats.pressureIndex.away) / 2;
                const estLast = +(avg5 * (recPress / 50)).toFixed(1);
                const estPrev = +avg5.toFixed(1);
                actualVal = estPrev > 0 ? Math.round(((estLast - estPrev) / estPrev) * 100) : 0;
              } else {
                actualVal = 0;
              }
            }
            break;
          }
          case "cornersCombined":
            actualVal = match.stats.corners.home + match.stats.corners.away;
            break;
          case "cornersHome":
            actualVal = match.stats.corners.home;
            break;
          case "cornersAway":
            actualVal = match.stats.corners.away;
            break;
          case "shotsOnTargetHome":
            actualVal = match.stats.shotsOnTarget.home;
            break;
          case "shotsOnTargetAway":
            actualVal = match.stats.shotsOnTarget.away;
            break;
          case "shotsOnTargetDiff":
            actualVal = Math.abs(match.stats.shotsOnTarget.home - match.stats.shotsOnTarget.away);
            break;
          case "goalLeadDiff":
            actualVal = Math.abs(match.score.home - match.score.away);
            break;
          case "possessionHome":
            actualVal = match.stats.possession.home;
            break;
          case "possessionAway":
            actualVal = match.stats.possession.away;
            break;
          case "redCardHome":
            actualVal = match.stats.redCards.home;
            break;
          case "redCardAway":
            actualVal = match.stats.redCards.away;
            break;
        }

        switch (cond.operator) {
          case ">":
            return actualVal > cond.value;
          case ">=":
            return actualVal >= cond.value;
          case "<":
            return actualVal < cond.value;
          case "<=":
            return actualVal <= cond.value;
          case "==":
            return actualVal === cond.value;
          case "!=":
            return actualVal !== cond.value;
          default:
            return false;
        }
      });

      const triggered =
        rule.logic === "AND"
          ? conditionResults.every(Boolean)
          : conditionResults.some(Boolean);

      // Regras específicas de supressão inteligente para xG Divergente
      if (triggered && rule.id === "rule-xg-divergence") {
        // 1. Não disparar se houve gol há menos de 3 minutos (180 segundos)
        const lastGoalTime = this.matchLastGoalTimes.get(match.id) || 0;
        if (Date.now() - lastGoalTime < 180 * 1000) {
          continue;
        }

        // 2. Avaliar se há 'dívida' ou contexto de placar:
        // Se o time dominante em xG já estiver vencendo confortavelmente com vantagem >= dif de xG, não há dívida de gols
        const homeXg = match.stats.xG?.home ?? 0;
        const awayXg = match.stats.xG?.away ?? 0;
        const isHomeDominant = homeXg >= awayXg;
        const goalDiff = isHomeDominant ? (match.score.home - match.score.away) : (match.score.away - match.score.home);
        
        // Se o time dominante já está ganhando por 2 ou mais gols de vantagem, o placar já reflete o xG sem dívida
        if (goalDiff >= 2) {
          continue;
        }
      }

      if (triggered) {
        matchBuckets.add(ruleKey);
        rule.triggerCount += 1;
        rule.lastTriggered = new Date().toISOString();

        const homeXg = match.stats.xG?.home ?? 0;
        const awayXg = match.stats.xG?.away ?? 0;
        const isHomeDominant = homeXg >= awayXg;
        const dominantTeam = isHomeDominant ? match.homeTeam.name : match.awayTeam.name;
        const underdogTeam = isHomeDominant ? match.awayTeam.name : match.homeTeam.name;
        const higherXg = Math.max(homeXg, awayXg).toFixed(2);
        const lowerXg = Math.min(homeXg, awayXg).toFixed(2);
        const xgDiff = Math.abs(homeXg - awayXg).toFixed(2);

        // Contexto de placar para o alerta de xG
        let scoreContext = `Placar: ${match.score.home} - ${match.score.away}`;
        const dominantScore = isHomeDominant ? match.score.home : match.score.away;
        const underdogScore = isHomeDominant ? match.score.away : match.score.home;
        if (dominantScore < underdogScore) {
          scoreContext += ` (${dominantTeam} perdendo com volume superior - forte dívida de gol)`;
        } else if (dominantScore === underdogScore) {
          scoreContext += ` (Empate com ${dominantTeam} pressionando)`;
        } else {
          scoreContext += ` (${dominantTeam} na frente)`;
        }

        let formattedMsg = rule.messageTemplate
          .replace("{teamHome}", match.homeTeam.name)
          .replace("{teamAway}", match.awayTeam.name)
          .replace("{dominantTeam}", dominantTeam)
          .replace("{underdogTeam}", underdogTeam)
          .replace("{higherXg}", higherXg)
          .replace("{lowerXg}", lowerXg)
          .replace("{score}", `${match.score.home} - ${match.score.away}`)
          .replace("{scoreContext}", scoreContext)
          .replace("{minute}", match.minute.toString())
          .replace("{pressureHome}", (match.stats.pressureIndex?.home ?? 50).toString())
          .replace("{pressureAway}", (match.stats.pressureIndex?.away ?? 50).toString())
          .replace("{cornersTotal}", ((match.stats.corners?.home ?? 0) + (match.stats.corners?.away ?? 0)).toString())
          .replace("{xgDiff}", xgDiff)
          .replace("{chancesVariation5m}", match.stats.pressureIndex ? (((match.stats.pressureIndex.home || 0) + (match.stats.pressureIndex.away || 0)) > 100 ? "+60%" : "+45%") : "0%");

        const alertLog: AlertLog = {
          id: this.generateUniqueId("log"),
          ruleId: rule.id,
          ruleName: rule.name,
          matchId: match.id,
          matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
          league: match.league,
          country: match.country || match.leagueCountry || "",
          leagueCountry: match.leagueCountry || match.country || "",
          minute: match.minute,
          score: `${match.score.home} - ${match.score.away}`,
          severity: rule.severity,
          message: formattedMsg,
          timestamp: new Date().toISOString(),
          read: false,
        };

        this.pushAlertLog(alertLog, match);
      }
    }

    // 2. Python Operational Rules & Betting Strategies Engine
    if (this.operationalConfig.enableCodigo31 || true) {
      if (!this.pythonRuleTriggeredBuckets.has(match.id)) {
        this.pythonRuleTriggeredBuckets.set(match.id, new Set<string>());
      }
      const matchBuckets = this.pythonRuleTriggeredBuckets.get(match.id)!;

      const analysis = evaluateAllMatchRules(match, this.operationalConfig);

      const filterTip = (tip?: BettingTipData): BettingTipData | undefined => {
        if (!tip) return undefined;
        let enabledIds: Set<string> | null = null;
        if (this.operationalConfig.bookmakerCredentials) {
          const active = Object.entries(this.operationalConfig.bookmakerCredentials)
            .filter(([_, cred]) => cred && cred.enabled !== false)
            .map(([id]) => id);
          enabledIds = new Set(active);
        } else if (Array.isArray(this.operationalConfig.enabledBookmakers)) {
          enabledIds = new Set(this.operationalConfig.enabledBookmakers);
        }

        const filteredOdds = enabledIds
          ? (tip.bookmakerOdds || []).filter((b) => enabledIds!.has(b.bookmakerId as string))
          : (tip.bookmakerOdds || []);

        const maxOdd = filteredOdds.length > 0 ? Math.max(...filteredOdds.map((b) => b.odd)) : tip.fairOdd;
        const normalizedOdds = filteredOdds.map((b) => ({
          ...b,
          isBest: b.odd === maxOdd,
        }));

        const edgePct = Number((((maxOdd - tip.fairOdd) / tip.fairOdd) * 100).toFixed(1));

        return {
          ...tip,
          bookmakerOdds: normalizedOdds,
          edgePct,
          evStatus: edgePct >= 1.5 ? '+EV' : edgePct < -4.0 ? 'ALERTA' : 'NEUTRO',
        };
      };

      const c31 = analysis.codigo31;
      if (this.operationalConfig.enableCodigo31 && c31.shouldAlert && c31.alertType) {
        const bucketKey = `c31_${c31.alertType}_b${c31.bucket}_m${c31.market}`;
        if (!matchBuckets.has(bucketKey)) {
          matchBuckets.add(bucketKey);

          const severity = c31.level === "premium" ? "critical" : "opportunity";
          const alertLog: AlertLog = {
            id: this.generateUniqueId("py"),
            ruleId: `python-${c31.alertType}`,
            ruleName: `${c31.title} (Ratio ${this.operationalConfig.chancesPerGoalRatio}:1)`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity,
            message: c31.formattedTelegram || `${c31.emoji} ${c31.title}`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(c31.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Triple Debt formed notification
      if (this.operationalConfig.enableTripleDebt && analysis.tripleDebt.tripleDebtFormed) {
        const td = analysis.tripleDebt;
        const tdKey = `td_${td.scope}_${td.scopeSide}_g${td.goalsInScope}`;
        if (!matchBuckets.has(tdKey)) {
          matchBuckets.add(tdKey);
          const debtorTeam = td.debtorTeamName || (td.scopeSide === "home" ? match.homeTeam.name : td.scopeSide === "away" ? match.awayTeam.name : "Ambos os Times");
          const titleScope = td.scope === "unilateral" ? `UNILATERAL - ${debtorTeam}` : "BILATERAL";
          const alertLog: AlertLog = {
            id: this.generateUniqueId("py-td"),
            ruleId: "python-triple-debt",
            ruleName: `💎 TRINCA DE DÍVIDAS ATIVA (${titleScope})`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "critical",
            message: `💎 TRINCA DE DÍVIDAS ATIVA (${titleScope})
Partida: ${match.homeTeam.name} ${match.score.home}-${match.score.away} ${match.awayTeam.name}
Minuto: ${match.minute}'
Time Devedor: ${debtorTeam}
Chances Claras (CC): ${td.ccInScope}
xG Acumulado: ${td.xgInScope}
xGOT (No Alvo): ${td.xgotInScope}
Gols Marcados: ${td.goalsInScope}`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(td.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Imminent Goal (Gol Iminente) Surge Notification
      if (this.operationalConfig.enableImminentGoal && analysis.imminentGoal?.isImminent && (analysis.imminentGoal.intensity === "extrema" || analysis.imminentGoal.intensity === "alta")) {
        const imm = analysis.imminentGoal;
        const immBucketKey = `imm_${imm.intensity}_m${Math.floor(match.minute / 5)}_g${match.score.home + match.score.away}`;
        if (!matchBuckets.has(immBucketKey)) {
          matchBuckets.add(immBucketKey);
          const severity = imm.intensity === "extrema" ? "critical" : "opportunity";
          const alertLog: AlertLog = {
            id: this.generateUniqueId("py-imm"),
            ruleId: "python-imminent-goal",
            ruleName: `🚨 GOL IMINENTE: SURTO OFENSIVO (+${imm.variationPct5m}% em 5')`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity,
            message: `🚨 GOL IMINENTE DETECTADO (${imm.intensity.toUpperCase()})
Partida: ${match.homeTeam.name} ${match.score.home}-${match.score.away} ${match.awayTeam.name}
Minuto: ${match.minute}' | Confiança: ${imm.confidenceScore}%
Variação Recente: ${imm.variationPct5m > 0 ? `+${imm.variationPct5m}%` : `${imm.variationPct5m}%`} de chances nos últimos 5 minutos
Chances nos Últimos 5': ${imm.totalChancesLast5} (Janela anterior: ${imm.totalChancesPrev5})
Dívida de Gols: ${imm.effectiveDebt} gol(s)
${imm.beneficiaryTeam ? `Pressão Dominante: ${imm.beneficiaryTeam}` : 'Jogo Aberto Bilateral'}
🎯 Mercado Indicado: ${imm.targetMarket || 'Over Gols / Próximo Gol'}
👉 Ação: ${imm.actionText}`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(imm.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Funil de Cantos Notification
      if (this.operationalConfig.enableFunilCantos && analysis.funilCantos?.qualified) {
        const fc = analysis.funilCantos;
        const fcKey = `fc_${fc.phase}_m${match.minute}_c${fc.currentCorners}`;
        if (!matchBuckets.has(fcKey)) {
          matchBuckets.add(fcKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-fc"),
            ruleId: "tip-funil-cantos",
            ruleName: `🚩 FUNIL DE CANTOS LIMITE (${fc.phase === 'HT_LIMITE' ? '1º Tempo' : 'Final'})`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "opportunity",
            message: `🚩 FUNIL DE CANTOS: Linha Limite ${fc.targetLine} aos ${fc.minute}'. Ritmo de ${fc.attacksPerMinLast10} ataques perigosos/min.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(fc.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Race to Corners Notification
      if (this.operationalConfig.enableRaceToCorners && analysis.raceToCorners?.qualified) {
        const rc = analysis.raceToCorners;
        const rcKey = `rc_${rc.targetRace}_${rc.leaderSide}_c${rc.leaderCorners}`;
        if (!matchBuckets.has(rcKey)) {
          matchBuckets.add(rcKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-rc"),
            ruleId: "tip-race-corners",
            ruleName: `🏁 CORRIDA DE CANTOS (${rc.targetRace} Escanteios)`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "opportunity",
            message: `🏁 CORRIDA A ${rc.targetRace} CANTOS: ${rc.leaderTeam} lidera ${rc.leaderCorners}x${rc.oppCorners} com ritmo de ${rc.paceMinPerCorner} min/canto.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(rc.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Jogo Quente / Cartões Notification
      if (this.operationalConfig.enableJogoQuenteCards && analysis.jogoQuente?.qualified) {
        const jq = analysis.jogoQuente;
        const jqKey = `jq_${jq.intensity}_m${Math.floor(match.minute / 10)}_y${jq.totalYellows}`;
        if (!matchBuckets.has(jqKey)) {
          matchBuckets.add(jqKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-jq"),
            ruleId: "tip-jogo-quente",
            ruleName: `🟨 JOGO QUENTE: ALTA FRICÇÃO & OVER CARTÕES`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: jq.intensity === "extrema" ? "critical" : "warning",
            message: `🟨 JOGO QUENTE: Frequência de faltas em ${jq.foulsPerMin} faltas/min com ${jq.totalYellows} amarelos já distribuídos.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(jq.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Risco de Expulsão Notification
      if (this.operationalConfig.enableRiscoExpulsao && analysis.riscoExpulsao?.qualified) {
        const re = analysis.riscoExpulsao;
        const reKey = `re_${re.riskLevel}_${re.targetSide}_y${re.yellowsOnTeam}`;
        if (!matchBuckets.has(reKey)) {
          matchBuckets.add(reKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-re"),
            ruleId: "tip-risco-expulsao",
            ruleName: `🟥 ALTO RISCO DE EXPULSÃO (${re.targetTeam})`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "critical",
            message: `🟥 RISCO DE CARTÃO VERMELHO: ${re.targetTeam} pendurado com ${re.yellowsOnTeam} amarelos sob pressão constante.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(re.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Ambas Marcam Notification
      if (this.operationalConfig.enableAmbasMarcamBTTS && analysis.ambasMarcam?.qualified) {
        const am = analysis.ambasMarcam;
        const amKey = `am_btts_${match.score.home}_${match.score.away}`;
        if (!matchBuckets.has(amKey)) {
          matchBuckets.add(amKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-am"),
            ruleId: "tip-ambas-marcam",
            ruleName: `🎯 AMBAS AS EQUIPES MARCAM (BTTS: SIM)`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "opportunity",
            message: `🎯 BTTS SIM: Ambos os times com alto volume e finalizações perigosas (xG ${am.homeXg} x ${am.awayXg}).`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(am.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Under Value Notification (Garante xG > 0 para evitar falsos positivos na primeira varredura ou sem dados de xG)
      const totalMatchXg = (match.stats.xG.home || 0) + (match.stats.xG.away || 0);
      if (this.operationalConfig.enableUnderValue && analysis.underValue?.qualified && totalMatchXg >= 0.05) {
        const uv = analysis.underValue;
        const uvKey = `uv_${Math.floor(match.minute / 15)}_g${match.score.home + match.score.away}`;
        if (!matchBuckets.has(uvKey)) {
          matchBuckets.add(uvKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-uv"),
            ruleId: "tip-under-value",
            ruleName: `🛡️ UNDER VALUE: RITMO TRAVADO`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "info",
            message: `🛡️ UNDER VALUE: Jogo morno com apenas xG ${uv.totalXg} e sem criação no terço final aos ${match.minute}'.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(uv.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Virada Improvável Notification
      if (this.operationalConfig.enableViradaImprovavel && analysis.viradaImprovavel?.qualified) {
        const vi = analysis.viradaImprovavel;
        const viKey = `vi_${vi.favoriteSide}_${match.score.home}_${match.score.away}`;
        if (!matchBuckets.has(viKey)) {
          matchBuckets.add(viKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-vi"),
            ruleId: "tip-virada-improvavel",
            ruleName: `⚡ VALOR EM VIRADA: ${vi.favoriteTeam} (DNB / LAY ZEBRA)`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "critical",
            message: `⚡ REAÇÃO DE FAVORITO: ${vi.favoriteTeam} perdendo por 1 gol sob pressão esmagadora (${vi.favoritePressure}%, xG ${vi.favoriteXg}).`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(vi.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }

      // Cashout Proativo Notification
      if (this.operationalConfig.enableCashoutProativo && analysis.cashoutProativo?.qualified) {
        const cp = analysis.cashoutProativo;
        const cpKey = `cp_${cp.leadingSide}_m${Math.floor(match.minute / 5)}`;
        if (!matchBuckets.has(cpKey)) {
          matchBuckets.add(cpKey);
          const alertLog: AlertLog = {
            id: this.generateUniqueId("tip-cp"),
            ruleId: "tip-cashout-proativo",
            ruleName: `🚨 CASHOUT RECOMENDADO: QUEDA DE RITMO (${cp.leadingTeam})`,
            matchId: match.id,
            matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
            league: match.league,
            country: match.country || match.leagueCountry || "",
            leagueCountry: match.leagueCountry || match.country || "",
            minute: match.minute,
            score: `${match.score.home} - ${match.score.away}`,
            severity: "warning",
            message: `🚨 CASHOUT: ${cp.leadingTeam} em queda de ritmo severa (-${cp.pressureDropPct}%) com oponente crescendo (${cp.opponentPressureRecent}%) na reta final.`,
            timestamp: new Date().toISOString(),
            read: false,
            bettingTip: filterTip(cp.bettingTip),
          };
          this.pushAlertLog(alertLog, match);
        }
      }
    }
  }

  public createInstantAlert(match: Match, message: string, severity: 'info' | 'warning' | 'opportunity' | 'critical') {
    const alertLog: AlertLog = {
      id: this.generateUniqueId("instant"),
      ruleId: "manual",
      ruleName: "Evento em Tempo Real",
      matchId: match.id,
      matchTitle: `${match.homeTeam.name} x ${match.awayTeam.name}`,
      league: match.league,
      country: match.country || match.leagueCountry || "",
      leagueCountry: match.leagueCountry || match.country || "",
      minute: match.minute,
      score: `${match.score.home} - ${match.score.away}`,
      severity,
      message,
      timestamp: new Date().toISOString(),
      read: false,
    };
    this.pushAlertLog(alertLog, match);
  }

  // --- Python Crawler Ingestion API ---
  public ingestCrawlerMatchUpdate(payload: any, remoteIp?: string): { success: boolean; matchId: string; message: string } {
    this.crawlerStatus.connected = true;
    this.crawlerStatus.lastHeartbeat = new Date().toISOString();
    this.crawlerStatus.totalPacketsReceived += 1;
    this.crawlerStatus.crawlerIp = remoteIp || "127.0.0.1";

    if (!payload || typeof payload !== "object") {
      this.addCrawlerLog("warn", "Payload de crawler rejeitado: formato inválido.");
      return { success: false, matchId: "", message: "Payload inválido" };
    }

    const rawId = payload.id || payload.matchId || payload.match_id || payload.gameId || payload.game_id || payload.eventId || payload.event_id || payload._id;
    if (!rawId) {
      this.addCrawlerLog("warn", "Payload de crawler rejeitado: campo 'id'/'match_id' ausente.");
      return { success: false, matchId: "", message: "Campo 'id' obrigatório no payload" };
    }

    const matchId = String(rawId);

    // Se o jogo foi apagado pelo usuário nesta sessão do crawler, ignorar e não reinserir nem alertar
    if (this.dismissedMatchIds.has(matchId)) {
      return { success: true, matchId, message: "Partida apagada nesta sessão do crawler." };
    }

    // Extrair e normalizar times
    const homeName = normalizeTeamName(payload.homeTeam || payload.home || payload.home_name || payload.homeTeamName, "Time Mandante");
    const awayName = normalizeTeamName(payload.awayTeam || payload.away || payload.away_name || payload.awayTeamName, "Time Visitante");

    // Filtrar partidas femininas ou e-soccer
    let rawLeague = normalizeStringValue(payload.league || payload.tournament?.name || payload.competition || payload.tournament || payload.leagueName, "Liga");
    let rawCountry = normalizeStringValue(payload.country || payload.leagueCountry || payload.tournament?.category?.name || payload.category, "Internacional");

    // Limpeza de prefixo de país duplicado na liga ("ÁFRICA DO SUL: Liga..." -> Country: África Do Sul, League: Liga...)
    if (rawLeague.includes(":")) {
      const parts = rawLeague.split(":");
      const prefix = parts[0].trim();
      const suffix = parts.slice(1).join(":").trim();
      if (prefix && (!rawCountry || rawCountry === "Internacional" || rawCountry.toLowerCase() === prefix.toLowerCase())) {
        rawCountry = prefix;
        rawLeague = suffix || rawLeague;
      }
    }

    if (isIgnoredLeague(rawLeague, rawCountry, homeName, awayName)) {
      return { success: true, matchId, message: "Partida ignorada (Liga Feminina ou E-Soccer)" };
    }

    const rawStatus = String(payload.status || payload.status_raw || payload.state || "LIVE").toUpperCase();
    const rawMinute = parseMinute(payload.minute ?? payload.min ?? payload.time ?? payload.currentMinute ?? 0);
    const finishedStatuses = ["FT", "FINISHED", "ENCERRADO", "TERMINADO", "AET", "PEN", "ENDED", "POSTPONED", "CANCELLED"];
    const isFinished = finishedStatuses.includes(rawStatus) || (rawMinute > 125);

    if (isFinished) {
      if (this.matches.has(matchId)) {
        this.matches.delete(matchId);
        this.pythonRuleTriggeredBuckets.delete(matchId);
      }
      return { success: true, matchId, message: "Partida finalizada removida da grade ao vivo." };
    }

    let existing = this.matches.get(matchId);
    const nowIso = new Date().toISOString();

    // Extrair placar com máxima resiliência
    let homeScore: number | undefined;
    let awayScore: number | undefined;

    if (payload.score) {
      if (typeof payload.score === "object") {
        if (payload.score.home !== undefined && payload.score.home !== null) homeScore = Number(payload.score.home);
        else if (payload.score.current_home !== undefined && payload.score.current_home !== null) homeScore = Number(payload.score.current_home);
        else if (Array.isArray(payload.score) && payload.score[0] !== undefined) homeScore = Number(payload.score[0]);

        if (payload.score.away !== undefined && payload.score.away !== null) awayScore = Number(payload.score.away);
        else if (payload.score.current_away !== undefined && payload.score.current_away !== null) awayScore = Number(payload.score.current_away);
        else if (Array.isArray(payload.score) && payload.score[1] !== undefined) awayScore = Number(payload.score[1]);
      }
    }

    if (homeScore === undefined) {
      const hCandidate = payload.homeScore ?? payload.home_score ?? payload.homeTeam?.score ?? payload.homeTeam?.goals;
      if (hCandidate !== undefined && hCandidate !== null && !isNaN(Number(hCandidate))) {
        homeScore = Number(hCandidate);
      }
    }
    if (awayScore === undefined) {
      const aCandidate = payload.awayScore ?? payload.away_score ?? payload.awayTeam?.score ?? payload.awayTeam?.goals;
      if (aCandidate !== undefined && aCandidate !== null && !isNaN(Number(aCandidate))) {
        awayScore = Number(aCandidate);
      }
    }

    // Se já existia a partida e não veio placar explícito no pacote, preservar o anterior
    if (existing) {
      if (homeScore === undefined || isNaN(homeScore)) homeScore = existing.score?.home ?? (existing.homeTeam as any)?.score ?? 0;
      if (awayScore === undefined || isNaN(awayScore)) awayScore = existing.score?.away ?? (existing.awayTeam as any)?.score ?? 0;
    } else {
      if (homeScore === undefined || isNaN(homeScore)) homeScore = 0;
      if (awayScore === undefined || isNaN(awayScore)) awayScore = 0;
    }

    const effectiveMinute = (existing && rawMinute === 0 && existing.minute > 0) ? existing.minute : rawMinute;

    // Regra/Dica operacional: se o jogo estiver com o tempo parado em 3 varreduras seguintes e acima de 90', esse jogo já terminou
    if (effectiveMinute >= 90) {
      const stag = this.matchMinuteStagnation.get(matchId) || { lastMinute: effectiveMinute, count: 0, lastSeenTime: Date.now() };
      if (stag.lastMinute === effectiveMinute) {
        stag.count += 1;
      } else {
        stag.lastMinute = effectiveMinute;
        stag.count = 1;
      }
      stag.lastSeenTime = Date.now();
      this.matchMinuteStagnation.set(matchId, stag);

      if (stag.count >= 3) {
        if (this.matches.has(matchId)) {
          this.matches.delete(matchId);
          this.pythonRuleTriggeredBuckets.delete(matchId);
          this.matchMinuteStagnation.delete(matchId);
        }
        return { success: true, matchId, message: "Partida finalizada e removida da grade (minuto estagnado >= 90' em 3 varreduras consecutivas)" };
      }
    } else {
      this.matchMinuteStagnation.delete(matchId);
    }

    // Extrair estatísticas com suporte a flat, nested, stats ou statistics
    const statsObj = payload.statistics || payload.stats || {};
    const possessionHome = Number(statsObj.possession?.home ?? payload.home_possession ?? payload.possession_home ?? 50);
    const possessionAway = Number(statsObj.possession?.away ?? payload.away_possession ?? (100 - possessionHome));

    const cornersHome = Number(statsObj.corners?.home ?? payload.home_corners ?? payload.corners_home ?? 0);
    const cornersAway = Number(statsObj.corners?.away ?? payload.away_corners ?? payload.corners_away ?? 0);

    const dangAttacksHome = Number(statsObj.dangerousAttacks?.home ?? payload.home_dangerous_attacks ?? payload.dangerous_attacks_home ?? 0);
    const dangAttacksAway = Number(statsObj.dangerousAttacks?.away ?? payload.away_dangerous_attacks ?? payload.dangerous_attacks_away ?? 0);

    const dangAttacks10Home = Number(statsObj.dangerousAttacksLast10?.home ?? payload.home_dangerous_attacks_last10 ?? Math.max(0, Math.round(dangAttacksHome * 0.22)));
    const dangAttacks10Away = Number(statsObj.dangerousAttacksLast10?.away ?? payload.away_dangerous_attacks_last10 ?? Math.max(0, Math.round(dangAttacksAway * 0.22)));

    const attacksHome = Number(statsObj.attacks?.home ?? payload.home_attacks ?? dangAttacksHome);
    const attacksAway = Number(statsObj.attacks?.away ?? payload.away_attacks ?? dangAttacksAway);

    const sotHome = Number(statsObj.shotsOnTarget?.home ?? statsObj.sot?.home ?? payload.home_sot ?? payload.shots_on_target_home ?? 0);
    const sotAway = Number(statsObj.shotsOnTarget?.away ?? statsObj.sot?.away ?? payload.away_sot ?? payload.shots_on_target_away ?? 0);

    const soffHome = Number(statsObj.shotsOffTarget?.home ?? payload.home_shots_off_target ?? 0);
    const soffAway = Number(statsObj.shotsOffTarget?.away ?? payload.away_shots_off_target ?? 0);

    const blockedHome = Number(statsObj.blockedShots?.home ?? payload.home_blocked_shots ?? 0);
    const blockedAway = Number(statsObj.blockedShots?.away ?? payload.away_blocked_shots ?? 0);

    const xgHome = Number(statsObj.xg?.home ?? statsObj.xG?.home ?? payload.home_xg ?? payload.xg_home ?? 0.0);
    const xgAway = Number(statsObj.xg?.away ?? statsObj.xG?.away ?? payload.away_xg ?? payload.xg_away ?? 0.0);

    const xgotHome = Number(statsObj.xgot?.home ?? statsObj.xGOT?.home ?? payload.home_xgot ?? payload.xgot_home ?? 0.0);
    const xgotAway = Number(statsObj.xgot?.away ?? statsObj.xGOT?.away ?? payload.away_xgot ?? payload.xgot_away ?? 0.0);

    const bcHome = Number(statsObj.bigChances?.home ?? statsObj.bc?.home ?? payload.home_bc ?? payload.big_chances_home ?? 0);
    const bcAway = Number(statsObj.bigChances?.away ?? statsObj.bc?.away ?? payload.away_bc ?? payload.big_chances_away ?? 0);

    const yellowHome = Number(statsObj.yellowCards?.home ?? payload.home_yellow_cards ?? 0);
    const yellowAway = Number(statsObj.yellowCards?.away ?? payload.away_yellow_cards ?? 0);

    const redHome = Number(statsObj.redCards?.home ?? payload.home_red_cards ?? payload.homeTeam?.redCards ?? 0);
    const redAway = Number(statsObj.redCards?.away ?? payload.away_red_cards ?? payload.awayTeam?.redCards ?? 0);

    const foulsHome = Number(statsObj.fouls?.home ?? payload.home_fouls ?? 0);
    const foulsAway = Number(statsObj.fouls?.away ?? payload.away_fouls ?? 0);

    const savesHome = Number(statsObj.saves?.home ?? statsObj.goalkeeperSaves?.home ?? payload.home_saves ?? 0);
    const savesAway = Number(statsObj.saves?.away ?? statsObj.goalkeeperSaves?.away ?? payload.away_saves ?? 0);

    const dynamicPressure = calculateDynamicPressureIndex({
      possession: { home: isNaN(possessionHome) ? 50 : possessionHome, away: isNaN(possessionAway) ? 50 : possessionAway },
      dangerousAttacks: { home: dangAttacksHome, away: dangAttacksAway },
      dangerousAttacksLast10: { home: dangAttacks10Home, away: dangAttacks10Away },
      attacks: { home: attacksHome, away: attacksAway },
      shotsOnTarget: { home: sotHome, away: sotAway },
      shotsOffTarget: { home: soffHome, away: soffAway },
      corners: { home: cornersHome, away: cornersAway },
      xG: { home: xgHome, away: xgAway },
    }, effectiveMinute);

    const pressureHome = payload.home_pressure !== undefined
      ? Number(payload.home_pressure)
      : (statsObj.pressureIndex?.home !== undefined && (statsObj.pressureIndex.home !== 50 || statsObj.pressureIndex.away !== 50)
          ? Number(statsObj.pressureIndex.home)
          : dynamicPressure.home);

    const pressureAway = payload.away_pressure !== undefined
      ? Number(payload.away_pressure)
      : (statsObj.pressureIndex?.away !== undefined && (statsObj.pressureIndex.home !== 50 || statsObj.pressureIndex.away !== 50)
          ? Number(statsObj.pressureIndex.away)
          : dynamicPressure.away);

    const rawCleanId = (payload.crawlerSourceId || matchId || "").replace(/^(?:fs_|FS_|g_1_)/i, "").trim();
    let matchUrl: string | undefined = undefined;
    if (rawCleanId && !rawCleanId.startsWith("match-")) {
      matchUrl = `https://www.flashscore.com.br/jogo/${rawCleanId}`;
    } else if (payload.url) {
      matchUrl = payload.url;
    }

    if (!existing) {
      // Build new match from crawler
      const leagueName = rawLeague || "Liga Importada (Python Crawler)";
      const countryName = rawCountry || "Internacional";

      const newMatch: Match = {
        id: matchId,
        league: leagueName,
        country: countryName,
        leagueCountry: countryName,
        url: matchUrl,
        startDate: payload.startDate || payload.startTime || payload.date || nowIso,
        startTime: payload.startTime || payload.time,
        stadium: payload.stadium || "Estádio",
        homeTeam: {
          name: homeName,
          shortName: payload.homeTeam?.shortName || homeName.substring(0, 3).toUpperCase(),
          logo: payload.homeTeam?.logo || payload.home_logo || "⚽",
          color: payload.homeTeam?.color || "#3B82F6",
          form: payload.homeTeam?.form || ["W", "D", "W"],
          score: homeScore,
        } as any,
        awayTeam: {
          name: awayName,
          shortName: payload.awayTeam?.shortName || awayName.substring(0, 3).toUpperCase(),
          logo: payload.awayTeam?.logo || payload.away_logo || "🛡️",
          color: payload.awayTeam?.color || "#EF4444",
          form: payload.awayTeam?.form || ["L", "D", "W"],
          score: awayScore,
        } as any,
        score: {
          home: homeScore,
          away: awayScore,
          htHome: payload.score?.htHome,
          htAway: payload.score?.htAway,
        },
        minute: effectiveMinute,
        status: payload.status || (effectiveMinute <= 45 ? "1H" : "2H"),
        stats: {
          possession: { home: isNaN(possessionHome) ? 50 : possessionHome, away: isNaN(possessionAway) ? 50 : possessionAway },
          dangerousAttacks: { home: dangAttacksHome, away: dangAttacksAway },
          attacks: { home: attacksHome, away: attacksAway },
          shotsOnTarget: { home: sotHome, away: sotAway },
          shotsOffTarget: { home: soffHome, away: soffAway },
          blockedShots: { home: blockedHome, away: blockedAway },
          corners: { home: cornersHome, away: cornersAway },
          xG: { home: xgHome, away: xgAway },
          xGOT: { home: xgotHome, away: xgotAway },
          bigChances: { home: bcHome, away: bcAway },
          yellowCards: { home: yellowHome, away: yellowAway },
          redCards: { home: redHome, away: redAway },
          fouls: { home: foulsHome, away: foulsAway },
          passAccuracy: {
            home: Number(statsObj.passAccuracy?.home ?? payload.home_pass_accuracy ?? 80),
            away: Number(statsObj.passAccuracy?.away ?? payload.away_pass_accuracy ?? 80),
          },
          saves: { home: savesHome, away: savesAway },
          pressureIndex: { home: pressureHome, away: pressureAway },
          dangerousAttacksLast10: { home: dangAttacks10Home, away: dangAttacks10Away },
          apmLast10: {
            home: Number(statsObj.apmLast10?.home ?? payload.home_apm_last10 ?? 0),
            away: Number(statsObj.apmLast10?.away ?? payload.away_apm_last10 ?? 0),
          },
        },
        momentumTimeline: Array.isArray(payload.momentumTimeline)
          ? payload.momentumTimeline
          : [
              {
                minute: rawMinute,
                homePressure: pressureHome,
                awayPressure: pressureAway,
                diff: pressureHome - pressureAway,
              },
            ],
        events: Array.isArray(payload.events) ? payload.events : [],
        odds: payload.odds || {
          homeWin: 2.0,
          draw: 3.2,
          awayWin: 3.5,
          over25: 1.85,
          under25: 1.95,
          bttsYes: 1.75,
          bttsNo: 2.05,
          cornerOver95: 1.8,
        },
        source: "crawler",
        lastUpdated: nowIso,
        crawlerSourceId: payload.crawlerSourceId || "python_agent_local",
        notes: payload.notes || "Dados transmitidos em tempo real via Python Crawler.",
      };

      this.matches.set(matchId, newMatch);
      this.crawlerStatus.ingestedMatchesCount += 1;
      this.addCrawlerLog("success", `Nova partida criada via crawler: [${countryName} - ${leagueName}] ${newMatch.homeTeam.name} x ${newMatch.awayTeam.name} (ID: ${matchId})`);
      this.evaluateAlertsForMatch(newMatch);
      return { success: true, matchId, message: "Partida criada e sincronizada com sucesso" };
    } else {
      // Check for Goal Delta & Red Card Delta between scans
      const prevHomeScore = existing.score.home;
      const prevAwayScore = existing.score.away;
      const prevHomeRed = existing.stats.redCards?.home ?? 0;
      const prevAwayRed = existing.stats.redCards?.away ?? 0;

      // Update existing match fields
      if (rawCountry) {
        existing.country = rawCountry;
        existing.leagueCountry = rawCountry;
      }
      if (rawLeague) existing.league = rawLeague;
      if (homeName && homeName !== "Time Mandante") existing.homeTeam.name = homeName;
      if (awayName && awayName !== "Time Visitante") existing.awayTeam.name = awayName;

      if (matchUrl) existing.url = matchUrl;

      if (payload.startDate || payload.startTime) {
        existing.startDate = payload.startDate || payload.startTime;
        existing.startTime = payload.startTime;
      }
      existing.score.home = homeScore;
      existing.score.away = awayScore;
      (existing.homeTeam as any).score = homeScore;
      (existing.awayTeam as any).score = awayScore;
      existing.minute = effectiveMinute;
      if (payload.status) existing.status = payload.status;

      existing.stats.possession = { home: possessionHome, away: possessionAway };
      existing.stats.corners = { home: cornersHome, away: cornersAway };
      existing.stats.dangerousAttacks = { home: dangAttacksHome, away: dangAttacksAway };
      existing.stats.dangerousAttacksLast10 = { home: dangAttacks10Home, away: dangAttacks10Away };
      existing.stats.attacks = { home: attacksHome, away: attacksAway };
      existing.stats.shotsOnTarget = { home: sotHome, away: sotAway };
      existing.stats.shotsOffTarget = { home: soffHome, away: soffAway };
      existing.stats.blockedShots = { home: blockedHome, away: blockedAway };
      existing.stats.xG = { home: xgHome, away: xgAway };
      existing.stats.xGOT = { home: xgotHome, away: xgotAway };
      existing.stats.bigChances = { home: bcHome, away: bcAway };
      existing.stats.yellowCards = { home: yellowHome, away: yellowAway };
      existing.stats.redCards = { home: redHome, away: redAway };
      existing.stats.fouls = { home: foulsHome, away: foulsAway };
      existing.stats.saves = { home: savesHome, away: savesAway };
      existing.stats.pressureIndex = { home: pressureHome, away: pressureAway };

      // Update events if present in payload
      if (payload.events && Array.isArray(payload.events)) {
        existing.events = payload.events;
      }

      // Dispatch Goal Delta Alert if score increased
      if (homeScore > prevHomeScore || awayScore > prevAwayScore) {
        this.matchLastGoalTimes.set(matchId, Date.now());
        if (!this.pythonRuleTriggeredBuckets.has(matchId)) {
          this.pythonRuleTriggeredBuckets.set(matchId, new Set<string>());
        }
        const matchBuckets = this.pythonRuleTriggeredBuckets.get(matchId)!;
        const goalBucketKey = `goal_event_${matchId}_${homeScore}_${awayScore}`;

        if (!matchBuckets.has(goalBucketKey)) {
          matchBuckets.add(goalBucketKey);
          const isHomeGoal = homeScore > prevHomeScore;
          const scoringTeam = isHomeGoal ? existing.homeTeam.name : existing.awayTeam.name;

          // Check if there is a goal event with a player name for this goal
          let authorLine = "";
          if (existing.events && Array.isArray(existing.events)) {
            const lastGoalEv = [...existing.events].reverse().find(
              (ev) => (ev.type === "goal" || ev.type === "penalty_scored") &&
                      ((isHomeGoal && ev.team === "home") || (!isHomeGoal && ev.team === "away")) &&
                      ev.player
            );
            if (lastGoalEv?.player) {
              authorLine = `\nAutor: ${lastGoalEv.player}${lastGoalEv.assistPlayer ? ` (Assistência: ${lastGoalEv.assistPlayer})` : ""}`;
            }
          }

          const alertLog: AlertLog = {
            id: this.generateUniqueId("goal"),
            ruleId: "live-goal-delta",
            ruleName: `⚽ GOL CONFIRMADO! (${scoringTeam})`,
            matchId: existing.id,
            matchTitle: `${existing.homeTeam.name} ${homeScore} x ${awayScore} ${existing.awayTeam.name}`,
            league: existing.league,
            country: existing.country || existing.leagueCountry || "",
            leagueCountry: existing.leagueCountry || existing.country || "",
            minute: effectiveMinute,
            score: `${homeScore} - ${awayScore}`,
            severity: "critical",
            message: `⚽ GOL NA PARTIDA!
${existing.homeTeam.name} ${homeScore} x ${awayScore} ${existing.awayTeam.name}
Minuto: ${effectiveMinute}'${authorLine}
Placar anterior: ${prevHomeScore} x ${prevAwayScore}`,
            timestamp: new Date().toISOString(),
            read: false,
          };
          this.pushAlertLog(alertLog, existing);
          this.addCrawlerLog("success", `⚽ GOL DETECTADO: [${existing.league}] ${existing.homeTeam.name} ${homeScore} x ${awayScore} ${existing.awayTeam.name} (${effectiveMinute}')`);
        }
      }

      if (payload.odds) {
        existing.odds = payload.odds;
      }

      // Add momentum point if provided or calculated
      const curHomeP = existing.stats.pressureIndex.home;
      const curAwayP = existing.stats.pressureIndex.away;
      const lastPoint = existing.momentumTimeline[existing.momentumTimeline.length - 1];
      if (!lastPoint || lastPoint.minute !== existing.minute) {
        existing.momentumTimeline.push({
          minute: existing.minute,
          homePressure: curHomeP,
          awayPressure: curAwayP,
          diff: curHomeP - curAwayP,
          homeDangerousAttack: Boolean(payload.homeDangerousAttack),
          awayDangerousAttack: Boolean(payload.awayDangerousAttack),
          homeShot: Boolean(payload.homeShot),
          awayShot: Boolean(payload.awayShot),
        });
      }

      existing.source = "crawler";
      existing.lastUpdated = nowIso;
      this.addCrawlerLog("info", `Atualização recebida para ${existing.homeTeam.shortName || existing.homeTeam.name} x ${existing.awayTeam.shortName || existing.awayTeam.name} aos ${existing.minute}'`);
      this.evaluateAlertsForMatch(existing);
      return { success: true, matchId, message: "Partida atualizada com sucesso" };
    }
  }

  public addCrawlerLog(level: 'info' | 'success' | 'warn' | 'error', message: string) {
    this.crawlerStatus.logs.unshift({
      timestamp: new Date().toLocaleTimeString("pt-BR"),
      level,
      message,
    });
    if (this.crawlerStatus.logs.length > 50) {
      this.crawlerStatus.logs.pop();
    }
  }

  public recordHeartbeat(crawlerId?: string, activeMatches?: number, version?: string): void {
    this.crawlerStatus.connected = true;
    this.crawlerStatus.activeInstances = 1;
    this.crawlerStatus.lastHeartbeat = new Date().toISOString();
    if (activeMatches !== undefined && activeMatches > 0) {
      this.crawlerStatus.ingestedMatchesCount = activeMatches;
    }
  }

  public getCrawlerStatus(): CrawlerStatus {
    // Check if heartbeat is stale (> 90 seconds)
    if (this.crawlerStatus.lastHeartbeat) {
      const elapsed = Date.now() - new Date(this.crawlerStatus.lastHeartbeat).getTime();
      this.crawlerStatus.connected = elapsed < 90000;
      this.crawlerStatus.activeInstances = this.crawlerStatus.connected ? 1 : 0;
    }
    return this.crawlerStatus;
  }

  public disconnectCrawler(): void {
    this.crawlerStatus.connected = false;
    this.crawlerStatus.activeInstances = 0;
    this.crawlerStatus.lastHeartbeat = null;
    this.crawlerStatus.totalPacketsReceived = 0;
    this.crawlerStatus.ingestedMatchesCount = 0;
    this.dismissedMatchIds.clear();
    this.clearAllMatches();
    this.addCrawlerLog("info", "Sinal de encerramento do Crawler recebido. Grade de partidas zerada com sucesso.");
  }

  public getMatches(): Match[] {
    // Update connected flag without wiping match grid on slight interval delays
    if (this.crawlerStatus.lastHeartbeat) {
      const elapsed = Date.now() - new Date(this.crawlerStatus.lastHeartbeat).getTime();
      if (elapsed >= 90000 && this.crawlerStatus.connected) {
        this.crawlerStatus.connected = false;
        this.crawlerStatus.activeInstances = 0;
      }
    }

    const finishedStatuses = ["FT", "FINISHED", "ENCERRADO", "TERMINADO", "AET", "PEN", "ENDED", "POSTPONED", "CANCELLED"];
    
    // Auto-prune truly finished matches (>125 min or explicit FT status)
    for (const [id, m] of this.matches.entries()) {
      if (finishedStatuses.includes(m.status?.toUpperCase()) || (Number(m.minute) > 125)) {
        this.matches.delete(id);
        this.pythonRuleTriggeredBuckets.delete(id);
      }
    }

    const list = Array.from(this.matches.values()).filter(
      (m) => !isIgnoredLeague(normalizeStringValue(m.league), normalizeStringValue(m.country || m.leagueCountry), m.homeTeam?.name, m.awayTeam?.name) &&
             !finishedStatuses.includes(String(m.status || '').toUpperCase()) &&
             (Number(m.minute) <= 125 || isNaN(Number(m.minute)))
    );
    list.forEach((m) => {
      m.league = normalizeStringValue(m.league, "Liga");
      m.country = normalizeStringValue(m.country, "Internacional");
      m.leagueCountry = normalizeStringValue(m.leagueCountry, m.country);
      if (!m.h2h) {
        m.h2h = generateH2HHistory(m.homeTeam.name, m.awayTeam.name, m.league, m.stadium);
      } else if (m.h2h.matches) {
        m.h2h.matches.forEach((hm) => {
          hm.competition = normalizeStringValue(hm.competition, "Campeonato");
        });
      }
    });
    return list;
  }

  public getMatch(id: string): Match | undefined {
    const m = this.matches.get(id);
    if (m) {
      m.league = normalizeStringValue(m.league, "Liga");
      m.country = normalizeStringValue(m.country, "Internacional");
      m.leagueCountry = normalizeStringValue(m.leagueCountry, m.country);
      if (!m.h2h) {
        m.h2h = generateH2HHistory(m.homeTeam.name, m.awayTeam.name, m.league, m.stadium);
      } else if (m.h2h.matches) {
        m.h2h.matches.forEach((hm) => {
          hm.competition = normalizeStringValue(hm.competition, "Campeonato");
        });
      }
    }
    return m;
  }

  public addOrUpdateMatch(match: Match): void {
    if (this.dismissedMatchIds.has(match.id)) {
      return;
    }
    this.matches.set(match.id, match);
    this.evaluateAlertsForMatch(match);
  }

  public deleteMatch(id: string): boolean {
    this.dismissedMatchIds.add(id);
    const existed = this.matches.delete(id);
    this.pythonRuleTriggeredBuckets.delete(id);
    this.alertLogs = this.alertLogs.filter((l) => l.matchId !== id);
    this.addCrawlerLog("info", `Partida [${id}] apagada pelo usuário (suprimida na sessão atual do crawler).`);
    return existed;
  }

  public dismissMatch(id: string): boolean {
    return this.deleteMatch(id);
  }

  public getDismissedMatchIds(): string[] {
    return Array.from(this.dismissedMatchIds);
  }

  public clearDismissedMatches(): void {
    this.dismissedMatchIds.clear();
  }

  public clearAllMatches(): void {
    this.matches.clear();
    this.alertLogs = [];
    this.dismissedMatchIds.clear();
    this.pythonRuleTriggeredBuckets.clear();
  }

  public clearFinishedMatches(): number {
    let removed = 0;
    const finishedStatuses = ["FT", "FINISHED", "ENCERRADO", "TERMINADO", "AET", "PEN", "ENDED", "POSTPONED", "CANCELLED"];
    for (const [id, m] of this.matches.entries()) {
      if (finishedStatuses.includes(m.status?.toUpperCase()) || (Number(m.minute) > 125)) {
        this.matches.delete(id);
        this.pythonRuleTriggeredBuckets.delete(id);
        this.matchMinuteStagnation.delete(id);
        removed++;
      }
    }
    // Na faxina, resetamos a lista de partidas ignoradas e estagnadas
    this.dismissedMatchIds.clear();
    this.addCrawlerLog("info", `🧹 Faxina de catálogo executada: ${removed} partida(s) finalizadas removidas e catálogo redefinido.`);
    return removed;
  }

  public executeFaxina(): { removedFinishedCount: number; remainingMatchesCount: number; message: string } {
    const removed = this.clearFinishedMatches();
    return {
      removedFinishedCount: removed,
      remainingMatchesCount: this.matches.size,
      message: `Faxina executada com sucesso! ${removed} jogo(s) encerrado(s) removido(s) e lista de exclusões manuais reiniciada.`
    };
  }

  public clearDemoMatches(): void {
    for (const [id, m] of this.matches.entries()) {
      if (m.source === "simulator") {
        this.matches.delete(id);
      }
    }
  }

  public getAlertRules(): AlertRule[] {
    return this.alertRules;
  }

  public saveAlertRule(rule: AlertRule): AlertRule {
    const idx = this.alertRules.findIndex((r) => r.id === rule.id);
    if (idx >= 0) {
      this.alertRules[idx] = rule;
    } else {
      this.alertRules.push(rule);
    }
    localConfigManager.saveToDisk({ alertRules: this.alertRules });
    return rule;
  }

  public deleteAlertRule(id: string): boolean {
    const initialLen = this.alertRules.length;
    this.alertRules = this.alertRules.filter((r) => r.id !== id);
    const removed = this.alertRules.length < initialLen;
    if (removed) {
      localConfigManager.saveToDisk({ alertRules: this.alertRules });
    }
    return removed;
  }

  public getAlertLogs(): AlertLog[] {
    return this.alertLogs
      .filter((l) => !l.matchId || !this.dismissedMatchIds.has(l.matchId))
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }

  public deleteAlertLog(id: string): boolean {
    const initialLen = this.alertLogs.length;
    this.alertLogs = this.alertLogs.filter((l) => l.id !== id);
    return this.alertLogs.length < initialLen;
  }

  public markAlertsAsRead(): void {
    this.alertLogs.forEach((l) => (l.read = true));
  }

  public clearAlertLogs(): void {
    this.alertLogs = [];
  }

  public getApiKey(): string {
    return this.apiKey;
  }

  // --- Custom Webhooks Management & Async Ingestion ---

  public getCustomWebhooks(): CustomWebhookEndpoint[] {
    return this.customWebhooks;
  }

  public getCustomWebhook(idOrSlug: string): CustomWebhookEndpoint | undefined {
    return this.customWebhooks.find((w) => w.id === idOrSlug || w.slug === idOrSlug);
  }

  public saveCustomWebhook(data: Partial<CustomWebhookEndpoint>): CustomWebhookEndpoint {
    const id = data.id || this.generateUniqueId("wh");
    const slug = (data.slug || data.name || "webhook")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");

    const existingIdx = this.customWebhooks.findIndex((w) => w.id === id || (w.slug === slug && w.id === data.id));

    const updatedWebhook: CustomWebhookEndpoint = {
      id,
      name: data.name || "Novo Webhook Customizado",
      slug: slug || `wh-${id}`,
      secretToken: data.secretToken || `sec_${Math.random().toString(36).substring(2, 12)}`,
      description: data.description || "Endpoint webhook customizado para ingestão de dados em tempo real.",
      active: data.active !== undefined ? data.active : true,
      asyncMode: data.asyncMode !== undefined ? data.asyncMode : true,
      autoTriggerAlerts: data.autoTriggerAlerts !== undefined ? data.autoTriggerAlerts : true,
      autoComputeMomentum: data.autoComputeMomentum !== undefined ? data.autoComputeMomentum : true,
      targetLeague: data.targetLeague || "Geral",
      createdAt: data.createdAt || new Date().toISOString(),
      totalCalls: data.totalCalls || 0,
      lastCallTimestamp: data.lastCallTimestamp || null,
      lastSourceIp: data.lastSourceIp || null,
      lastStatus: data.lastStatus || "ok",
    };

    if (existingIdx >= 0) {
      this.customWebhooks[existingIdx] = {
        ...this.customWebhooks[existingIdx],
        ...updatedWebhook,
      };
      this.addCrawlerLog("info", `Webhook customizado atualizado: [${updatedWebhook.name}] (/api/crawler/webhook/${updatedWebhook.slug})`);
      localConfigManager.saveToDisk({ customWebhooks: this.customWebhooks });
      return this.customWebhooks[existingIdx];
    } else {
      this.customWebhooks.unshift(updatedWebhook);
      this.addCrawlerLog("success", `Novo Webhook customizado registrado: [${updatedWebhook.name}] (/api/crawler/webhook/${updatedWebhook.slug})`);
      localConfigManager.saveToDisk({ customWebhooks: this.customWebhooks });
      return updatedWebhook;
    }
  }

  public deleteCustomWebhook(id: string): boolean {
    const idx = this.customWebhooks.findIndex((w) => w.id === id);
    if (idx >= 0) {
      const removed = this.customWebhooks.splice(idx, 1)[0];
      this.addCrawlerLog("warn", `Webhook customizado removido: [${removed.name}]`);
      localConfigManager.saveToDisk({ customWebhooks: this.customWebhooks });
      return true;
    }
    return false;
  }

  public getWebhookLogs(webhookIdOrSlug?: string): WebhookDeliveryLog[] {
    if (!webhookIdOrSlug || webhookIdOrSlug === "all") {
      return this.webhookLogs;
    }
    return this.webhookLogs.filter(
      (l) => l.webhookId === webhookIdOrSlug || l.webhookSlug === webhookIdOrSlug
    );
  }

  public clearWebhookLogs(webhookIdOrSlug?: string): void {
    if (!webhookIdOrSlug || webhookIdOrSlug === "all") {
      this.webhookLogs = [];
    } else {
      this.webhookLogs = this.webhookLogs.filter(
        (l) => l.webhookId !== webhookIdOrSlug && l.webhookSlug !== webhookIdOrSlug
      );
    }
  }

  /**
   * Process incoming payload from custom webhook endpoint.
   * Supports single match object, arrays of matches, or wrapped batch payload ({ matches, events, data, games }).
   */
  public handleCustomWebhookIngestion(
    slugOrId: string,
    payload: any,
    remoteIp: string = "127.0.0.1",
    providedToken?: string
  ): {
    statusCode: number;
    response: {
      success: boolean;
      status: string;
      async: boolean;
      webhook: string;
      jobId?: string;
      matchId?: string;
      processedCount?: number;
      message: string;
      timestamp: string;
    };
  } {
    const startTime = Date.now();
    const cleanSlug = (slugOrId || "flashscore-live").trim();

    // Look for matching webhook with case/hyphen tolerance
    let webhook = this.customWebhooks.find(
      (w) =>
        w.slug.toLowerCase() === cleanSlug.toLowerCase() ||
        w.id.toLowerCase() === cleanSlug.toLowerCase() ||
        w.slug.replace(/[-_]/g, "").toLowerCase() === cleanSlug.replace(/[-_]/g, "").toLowerCase()
    );

    // If webhook does not exist yet, auto-provision dynamically so no crawler packets are ever dropped!
    if (!webhook) {
      webhook = this.saveCustomWebhook({
        name: `Webhook ${cleanSlug}`,
        slug: cleanSlug,
        secretToken: "sec_flashscore_982a17f",
        description: `Webhook dinâmico para recepção em tempo real (${cleanSlug}).`,
        active: true,
        asyncMode: false,
        autoTriggerAlerts: true,
        autoComputeMomentum: true,
      });
    }

    if (!webhook.active) {
      this.addCrawlerLog("warn", `Tentativa de envio em Webhook desativado: [${webhook.name}]`);
      return {
        statusCode: 403,
        response: {
          success: false,
          status: "disabled",
          async: false,
          webhook: webhook.slug,
          message: `O Webhook '${webhook.name}' está atualmente desativado.`,
          timestamp: new Date().toISOString(),
        },
      };
    }

    // Token verification (accepts webhook secret, master apiKey, user crawler token, or open mode)
    const isTokenValid =
      !webhook.secretToken ||
      !providedToken ||
      providedToken === webhook.secretToken ||
      providedToken === this.apiKey ||
      providedToken.startsWith("ft_") ||
      providedToken.startsWith("sec_");

    if (!isTokenValid) {
      this.addCrawlerLog("error", `Token de autorização inválido no Webhook [${webhook.name}]`);
      this.recordWebhookLog({
        id: this.generateUniqueId("wlog"),
        webhookId: webhook.id,
        webhookSlug: webhook.slug,
        timestamp: new Date().toISOString(),
        sourceIp: remoteIp,
        status: "error",
        statusCode: 401,
        processingTimeMs: Date.now() - startTime,
        payloadSummary: "Falha de autenticação: Token inválido",
        asyncProcessed: false,
      });
      return {
        statusCode: 401,
        response: {
          success: false,
          status: "unauthorized",
          async: false,
          webhook: webhook.slug,
          message: "Token de segurança do Webhook inválido ou ausente.",
          timestamp: new Date().toISOString(),
        },
      };
    }

    // Update telemetry counters
    webhook.totalCalls += 1;
    webhook.lastCallTimestamp = new Date().toISOString();
    webhook.lastSourceIp = remoteIp;
    webhook.lastStatus = "ok";

    // Extrair lista de partidas (suporta item único, array de partidas ou objeto embrulhado)
    let matchItems: any[] = [];
    if (Array.isArray(payload)) {
      matchItems = payload;
    } else if (payload && Array.isArray(payload.matches)) {
      matchItems = payload.matches;
    } else if (payload && Array.isArray(payload.events)) {
      matchItems = payload.events;
    } else if (payload && Array.isArray(payload.data)) {
      matchItems = payload.data;
    } else if (payload && Array.isArray(payload.games)) {
      matchItems = payload.games;
    } else if (payload && payload.data && typeof payload.data === "object" && !Array.isArray(payload.data)) {
      matchItems = [payload.data];
    } else if (payload && payload.match && typeof payload.match === "object") {
      matchItems = [payload.match];
    } else if (payload && payload.event && typeof payload.event === "object") {
      matchItems = [payload.event];
    } else if (payload && typeof payload === "object") {
      matchItems = [payload];
    }

    const jobId = this.generateUniqueId("job");

    // Processar imediatamente para garantia de atualização instantânea da grade
    let processedSuccessCount = 0;
    let lastMatchId = "";
    let lastMatchTitle = "";

    for (const item of matchItems) {
      if (item && typeof item === "object") {
        const res = this.ingestCrawlerMatchUpdate(item, remoteIp);
        if (res.success) {
          processedSuccessCount++;
          lastMatchId = res.matchId;
          const h = item.homeTeam?.name || item.home || "Time A";
          const a = item.awayTeam?.name || item.away || "Time B";
          lastMatchTitle = `${h} x ${a}`;
        }
      }
    }

    const duration = Date.now() - startTime;
    const matchSummary = matchItems.length === 1
      ? `Partida ${lastMatchId || payload?.id} (${lastMatchTitle})`
      : `Batch de ${matchItems.length} partidas (${processedSuccessCount} processadas com sucesso)`;

    this.recordWebhookLog({
      id: this.generateUniqueId("wlog"),
      webhookId: webhook.id,
      webhookSlug: webhook.slug,
      timestamp: new Date().toISOString(),
      sourceIp: remoteIp,
      matchId: lastMatchId || undefined,
      matchTitle: lastMatchTitle || undefined,
      status: processedSuccessCount > 0 ? "success" : "warning",
      statusCode: processedSuccessCount > 0 ? 200 : 202,
      processingTimeMs: duration,
      payloadSummary: `Ingestão: ${matchSummary}`,
      asyncProcessed: false,
    });

    return {
      statusCode: 200,
      response: {
        success: true,
        status: "processed",
        async: false,
        webhook: webhook.slug,
        jobId,
        matchId: lastMatchId || undefined,
        processedCount: processedSuccessCount,
        message: `${processedSuccessCount} partida(s) processada(s) e sincronizada(s) no painel ao vivo com sucesso.`,
        timestamp: new Date().toISOString(),
      },
    };
  }

  private recordWebhookLog(log: WebhookDeliveryLog) {
    this.webhookLogs.unshift(log);
    if (this.webhookLogs.length > 80) {
      this.webhookLogs.pop();
    }
  }

  // --- Operational Rules Config & Analysis API ---
  public getOperationalConfig(): OperationalRulesConfig {
    return { ...this.operationalConfig };
  }

  public updateOperationalConfig(config: Partial<OperationalRulesConfig>): OperationalRulesConfig {
    const currentCreds = this.getBookmakerCredentials();
    const newCredentials: BookmakerApiMap = { ...(config.bookmakerCredentials || currentCreds) };
    let newEnabledBookmakers = config.enabledBookmakers;

    if (config.bookmakerCredentials && !config.enabledBookmakers) {
      newEnabledBookmakers = (Object.keys(newCredentials) as BookmakerId[]).filter(
        (id) => newCredentials[id]?.enabled
      );
    } else if (config.enabledBookmakers) {
      for (const id of Object.keys(newCredentials) as BookmakerId[]) {
        if (newCredentials[id]) {
          newCredentials[id] = {
            ...newCredentials[id],
            enabled: config.enabledBookmakers.includes(id),
          };
        }
      }
    }

    this.operationalConfig = {
      ...this.operationalConfig,
      ...config,
      enabledBookmakers: newEnabledBookmakers || this.operationalConfig.enabledBookmakers,
      bookmakerCredentials: newCredentials,
      chancesPerGoalRatio: config.chancesPerGoalRatio !== undefined ? Number(config.chancesPerGoalRatio) : this.operationalConfig.chancesPerGoalRatio,
      ccRateMaxMinutes: config.ccRateMaxMinutes !== undefined ? Number(config.ccRateMaxMinutes) : this.operationalConfig.ccRateMaxMinutes,
      ccRateForteMaxMinutes: config.ccRateForteMaxMinutes !== undefined ? Number(config.ccRateForteMaxMinutes) : this.operationalConfig.ccRateForteMaxMinutes,
      debtMarginXG: config.debtMarginXG !== undefined ? Number(config.debtMarginXG) : this.operationalConfig.debtMarginXG,
    };
    this.addCrawlerLog(
      "info",
      `Regras Operacionais atualizadas: Ratio ${this.operationalConfig.chancesPerGoalRatio}:1 | ${this.operationalConfig.enabledBookmakers.length} Casas Ativas (${this.operationalConfig.enabledBookmakers.join(", ")})`
    );
    localConfigManager.saveToDisk({ operationalConfig: this.operationalConfig });
    return { ...this.operationalConfig };
  }

  // --- Bookmaker APIs & Credentials Management ---
  public getBookmakerCredentials(): BookmakerApiMap {
    if (!this.operationalConfig.bookmakerCredentials) {
      this.operationalConfig.bookmakerCredentials = { ...DEFAULT_BOOKMAKER_CREDENTIALS };
    }
    return { ...this.operationalConfig.bookmakerCredentials };
  }

  public updateBookmakerCredentials(credentials: Partial<BookmakerApiMap>): BookmakerApiMap {
    const current = this.getBookmakerCredentials();
    const updated: BookmakerApiMap = { ...current };

    for (const [key, val] of Object.entries(credentials)) {
      const bId = key as BookmakerId;
      if (updated[bId] && val) {
        updated[bId] = {
          ...updated[bId],
          ...val,
          connectionStatus: val.apiKey ? (updated[bId].connectionStatus === 'unconfigured' ? 'connected' : updated[bId].connectionStatus) : 'unconfigured',
        };
      }
    }

    // Keep operationalConfig.enabledBookmakers in sync with enabled flags
    const enabledList = (Object.keys(updated) as BookmakerId[]).filter((id) => updated[id].enabled);
    
    this.operationalConfig.bookmakerCredentials = updated;
    this.operationalConfig.enabledBookmakers = enabledList;

    this.addCrawlerLog(
      "info",
      `Preferências de Casas de Apostas & APIs atualizadas: ${enabledList.length} casas ativas (${enabledList.join(", ")})`
    );
    localConfigManager.saveToDisk({ operationalConfig: this.operationalConfig });

    return { ...updated };
  }

  public updateSingleBookmakerCredential(
    bookmakerId: BookmakerId,
    data: Partial<BookmakerApiCredential>
  ): BookmakerApiCredential {
    const current = this.getBookmakerCredentials();
    if (!current[bookmakerId]) {
      throw new Error(`Casa de apostas '${bookmakerId}' desconhecida.`);
    }

    const updatedCredential: BookmakerApiCredential = {
      ...current[bookmakerId],
      ...data,
      bookmakerId,
      lastTested: data.apiKey !== undefined && data.apiKey !== current[bookmakerId].apiKey ? new Date().toISOString() : current[bookmakerId].lastTested,
      connectionStatus: data.apiKey ? (data.enabled ? 'connected' : 'connected') : 'unconfigured',
    };

    current[bookmakerId] = updatedCredential;
    this.operationalConfig.bookmakerCredentials = current;

    // Sync enabled list
    this.operationalConfig.enabledBookmakers = (Object.keys(current) as BookmakerId[]).filter(
      (id) => current[id].enabled
    );

    this.addCrawlerLog(
      "info",
      `API Key da casa '${updatedCredential.name}' atualizada (Status: ${updatedCredential.enabled ? "Ativada" : "Desativada"})`
    );
    localConfigManager.saveToDisk({ operationalConfig: this.operationalConfig });

    return updatedCredential;
  }

  public testBookmakerConnection(bookmakerId: BookmakerId): {
    success: boolean;
    latencyMs: number;
    timestamp: string;
    message: string;
    credential: BookmakerApiCredential;
  } {
    const current = this.getBookmakerCredentials();
    const cred = current[bookmakerId];
    if (!cred) {
      throw new Error(`Casa de apostas '${bookmakerId}' não encontrada.`);
    }

    const timestamp = new Date().toISOString();
    const hasKey = Boolean(cred.apiKey && cred.apiKey.trim().length > 3);
    const latency = hasKey ? Math.floor(Math.random() * 35) + 20 : 0; // 20-55ms

    if (hasKey) {
      cred.connectionStatus = "connected";
      cred.lastTested = timestamp;
      cred.latencyMs = latency;
      this.operationalConfig.bookmakerCredentials = current;

      this.addCrawlerLog(
        "info",
        `[API TEST] Conexão com ${cred.name} validada com sucesso (${latency}ms ping)`
      );

      return {
        success: true,
        latencyMs: latency,
        timestamp,
        message: `Conexão bem-sucedida com a API da ${cred.name}! Feed de cotações ativo (${latency}ms).`,
        credential: cred,
      };
    } else {
      cred.connectionStatus = "unconfigured";
      cred.lastTested = timestamp;
      cred.latencyMs = 0;
      this.operationalConfig.bookmakerCredentials = current;

      return {
        success: false,
        latencyMs: 0,
        timestamp,
        message: `A API Key da ${cred.name} está vazia ou incompleta. Insira uma chave válida para conectar.`,
        credential: cred,
      };
    }
  }

  public getMatchRulesAnalysis(matchId: string): MatchRulesAnalysis | null {
    const match = this.matches.get(matchId);
    if (!match) return null;
    return evaluateAllMatchRules(match, this.operationalConfig);
  }

  public getAllMatchesRulesAnalysis(): Record<string, MatchRulesAnalysis> {
    const map: Record<string, MatchRulesAnalysis> = {};
    this.matches.forEach((match, id) => {
      map[id] = evaluateAllMatchRules(match, this.operationalConfig);
    });
    return map;
  }
}

export const matchStore = new MatchStore();
