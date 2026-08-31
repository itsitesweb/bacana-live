export type MatchStatus = '1H' | 'HT' | '2H' | 'FT' | 'LIVE' | 'SCHEDULED' | 'FINISHED' | 'ENCERRADO';

export interface TeamInfo {
  name: string;
  shortName: string;
  logo: string;
  color: string;
  form?: ('W' | 'D' | 'L')[];
}

export interface MatchScore {
  home: number;
  away: number;
  htHome?: number;
  htAway?: number;
}

export interface MatchStats {
  possession: { home: number; away: number };
  dangerousAttacks: { home: number; away: number };
  attacks: { home: number; away: number };
  shotsOnTarget: { home: number; away: number };
  shotsOffTarget: { home: number; away: number };
  blockedShots: { home: number; away: number };
  corners: { home: number; away: number };
  xG: { home: number; away: number };
  yellowCards: { home: number; away: number };
  redCards: { home: number; away: number };
  fouls: { home: number; away: number };
  passAccuracy: { home: number; away: number };
  saves: { home: number; away: number };
  pressureIndex: { home: number; away: number }; // 0 to 100 live momentum
  dangerousAttacksLast10: { home: number; away: number };
  apmLast10?: { home: number; away: number }; // Attacks per minute last 10m
  bigChances?: { home: number; away: number }; // Chances Claras (CC / BC)
  xGOT?: { home: number; away: number }; // Expected Goals on Target
  boxTouches?: { home: number; away: number }; // Toques na Área Adversária
}

export interface MomentumPoint {
  minute: number;
  homePressure: number; // 0 to 100
  awayPressure: number; // 0 to 100
  diff: number; // homePressure - awayPressure (-100 to 100)
  homeDangerousAttack?: boolean;
  awayDangerousAttack?: boolean;
  homeShot?: boolean;
  awayShot?: boolean;
  event?: string;
}

export interface MatchEvent {
  id: string;
  minute: number;
  extraMinute?: number;
  type: 'goal' | 'yellow_card' | 'red_card' | 'sub' | 'var' | 'corner' | 'penalty_missed' | 'penalty_scored' | 'dangerous_attack';
  team: 'home' | 'away';
  player?: string;
  assistPlayer?: string;
  detail?: string;
  score?: string;
}

export interface MatchOdds {
  homeWin: number;
  draw: number;
  awayWin: number;
  over25: number;
  under25: number;
  bttsYes: number;
  bttsNo: number;
  cornerOver95: number;
}

export interface HeadToHeadMatch {
  id: string;
  date: string;
  competition: string;
  homeTeamName: string;
  awayTeamName: string;
  homeScore: number;
  awayScore: number;
  winner: 'home' | 'away' | 'draw';
  totalCorners?: number;
  totalCards?: number;
  stadium?: string;
}

export interface HeadToHeadSummary {
  totalMatches: number;
  homeWins: number;
  draws: number;
  awayWins: number;
  avgGoalsPerGame: number;
  bttsPercentage: number; // % both teams scored
  over25Percentage: number; // % games > 2.5 goals
  avgCornersPerGame: number;
  avgCardsPerGame: number;
  dominantTrendInsight: string;
}

export interface Match {
  id: string;
  league: string;
  country?: string;
  leagueCountry?: string;
  startDate?: string;
  startTime?: string;
  stadium?: string;
  homeTeam: TeamInfo;
  awayTeam: TeamInfo;
  score: MatchScore;
  minute: number;
  status: MatchStatus;
  stats: MatchStats;
  momentumTimeline: MomentumPoint[];
  events: MatchEvent[];
  odds: MatchOdds;
  source: 'crawler' | 'simulator' | 'manual';
  url?: string;
  lastUpdated: string;
  crawlerSourceId?: string;
  notes?: string;
  h2h?: {
    summary: HeadToHeadSummary;
    matches: HeadToHeadMatch[];
  };
}

export type AlertMetric =
  | 'minute'
  | 'pressureHome'
  | 'pressureAway'
  | 'pressureDiff'
  | 'xgDiff'
  | 'totalXg'
  | 'dangerousAttacksLast10Home'
  | 'dangerousAttacksLast10Away'
  | 'chancesVariation5m'
  | 'cornersCombined'
  | 'cornersHome'
  | 'cornersAway'
  | 'shotsOnTargetHome'
  | 'shotsOnTargetAway'
  | 'shotsOnTargetDiff'
  | 'goalLeadDiff'
  | 'possessionHome'
  | 'possessionAway'
  | 'redCardHome'
  | 'redCardAway';

export type AlertOperator = '>' | '>=' | '<' | '<=' | '==' | '!=';
export type AlertSeverity = 'info' | 'warning' | 'opportunity' | 'critical';

export interface AlertCondition {
  metric: AlertMetric;
  operator: AlertOperator;
  value: number;
}

export interface AlertRule {
  id: string;
  name: string;
  description?: string;
  matchId: string; // 'all' for all matches or specific match id
  enabled: boolean;
  conditions: AlertCondition[];
  logic: 'AND' | 'OR';
  severity: AlertSeverity;
  soundEnabled: boolean;
  browserNotification: boolean;
  messageTemplate: string;
  lastTriggered?: string;
  triggerCount: number;
}

export interface AlertLog {
  id: string;
  ruleId: string;
  ruleName: string;
  matchId: string;
  matchTitle: string;
  league?: string;
  country?: string;
  leagueCountry?: string;
  minute: number;
  score: string;
  severity: AlertSeverity;
  message: string;
  timestamp: string;
  read: boolean;
  url?: string;
  category?: string;
  bettingTip?: BettingTipData;
}

export interface CrawlerLogItem {
  timestamp: string;
  level: 'info' | 'success' | 'warn' | 'error';
  message: string;
}

export interface CrawlerStatus {
  connected: boolean;
  lastHeartbeat: string | null;
  activeInstances: number;
  totalPacketsReceived: number;
  crawlerIp?: string;
  apiKey?: string;
  apiKeyConfigured: boolean;
  logs: CrawlerLogItem[];
  ingestedMatchesCount: number;
}

export interface WebhookDeliveryLog {
  id: string;
  webhookId: string;
  webhookSlug: string;
  timestamp: string;
  sourceIp: string;
  matchId?: string;
  matchTitle?: string;
  status: 'success' | 'warning' | 'error';
  statusCode: number;
  processingTimeMs: number;
  payloadSummary: string;
  asyncProcessed: boolean;
}

export interface CustomWebhookEndpoint {
  id: string;
  name: string;
  slug: string;
  secretToken: string;
  description: string;
  active: boolean;
  asyncMode: boolean;
  autoTriggerAlerts: boolean;
  autoComputeMomentum: boolean;
  targetLeague?: string;
  createdAt: string;
  totalCalls: number;
  lastCallTimestamp?: string | null;
  lastSourceIp?: string | null;
  lastStatus?: 'ok' | 'error';
}

export interface TacticalAnalysis {
  matchId: string;
  summary: string;
  momentumVerdict: 'home_dominant' | 'away_dominant' | 'balanced' | 'end_to_end';
  likelyNextEvent: string;
  nextGoalProbability: {
    home: number;
    away: number;
    noGoal: number;
  };
  keyInsights: string[];
  cornerPressureScore: number; // 0-100
  cardRiskScore: number; // 0-100
  tradingAngles: string[];
  analyzedAt: string;
}

// ==========================================
// Bookmakers & Trading Odds Types
// ==========================================

export type BookmakerId =
  | 'bet365'
  | 'betfair'
  | 'pinnacle'
  | 'betano'
  | 'esportivabet'
  | 'sportingbet'
  | 'kto'
  | 'superbet'
  | '1xbet';

export interface BookmakerInfo {
  id: BookmakerId;
  name: string;
  shortName: string;
  tagColor: string;
  badgeBg: string;
  type: 'sportsbook' | 'exchange' | 'sharp';
  marginPct: number; // Margem média da casa em %
}

export const AVAILABLE_BOOKMAKERS: BookmakerInfo[] = [
  { id: 'bet365', name: 'Bet365', shortName: 'B365', tagColor: 'text-emerald-400', badgeBg: 'bg-emerald-950/70 border-emerald-500/40', type: 'sportsbook', marginPct: 5.5 },
  { id: 'betfair', name: 'Betfair Exchange', shortName: 'BFAIR', tagColor: 'text-amber-400', badgeBg: 'bg-amber-950/70 border-amber-500/40', type: 'exchange', marginPct: 2.0 },
  { id: 'pinnacle', name: 'Pinnacle', shortName: 'PINN', tagColor: 'text-orange-400', badgeBg: 'bg-orange-950/70 border-orange-500/40', type: 'sharp', marginPct: 2.5 },
  { id: 'betano', name: 'Betano', shortName: 'BETA', tagColor: 'text-orange-300', badgeBg: 'bg-orange-950/50 border-orange-400/30', type: 'sportsbook', marginPct: 5.0 },
  { id: 'esportivabet', name: 'Esportiva Bet', shortName: 'ESPB', tagColor: 'text-emerald-400', badgeBg: 'bg-emerald-950/60 border-emerald-400/40', type: 'sportsbook', marginPct: 5.2 },
  { id: 'sportingbet', name: 'Sportingbet', shortName: 'SBET', tagColor: 'text-blue-400', badgeBg: 'bg-blue-950/70 border-blue-500/40', type: 'sportsbook', marginPct: 6.0 },
  { id: 'kto', name: 'KTO', shortName: 'KTO', tagColor: 'text-rose-400', badgeBg: 'bg-rose-950/70 border-rose-500/40', type: 'sportsbook', marginPct: 5.5 },
  { id: 'superbet', name: 'Superbet', shortName: 'SUPB', tagColor: 'text-red-400', badgeBg: 'bg-red-950/70 border-red-500/40', type: 'sportsbook', marginPct: 4.8 },
  { id: '1xbet', name: '1xBet', shortName: '1XB', tagColor: 'text-cyan-400', badgeBg: 'bg-cyan-950/70 border-cyan-500/40', type: 'sportsbook', marginPct: 4.0 },
];

export interface BookmakerApiCredential {
  bookmakerId: BookmakerId;
  name: string;
  enabled: boolean;
  apiKey: string;
  apiSecret?: string;
  environment?: 'production' | 'sandbox';
  syncIntervalSeconds?: number;
  lastTested?: string | null;
  connectionStatus?: 'connected' | 'unconfigured' | 'error' | 'testing';
  latencyMs?: number;
  customEndpoint?: string;
  accountUsername?: string;
  notes?: string;
}

export type BookmakerApiMap = Record<BookmakerId, BookmakerApiCredential>;

export const DEFAULT_BOOKMAKER_CREDENTIALS: BookmakerApiMap = {
  bet365: {
    bookmakerId: 'bet365',
    name: 'Bet365',
    enabled: true,
    apiKey: 'b365_live_api_99a8b7c6d5e4f3a2',
    environment: 'production',
    connectionStatus: 'connected',
    lastTested: '2026-08-21T09:15:00.000Z',
    latencyMs: 38,
    notes: 'API Sportsbook Live & Mercados Asiáticos',
  },
  betfair: {
    bookmakerId: 'betfair',
    name: 'Betfair Exchange',
    enabled: true,
    apiKey: 'bfair_app_key_88f9e0a1b2c3d4e5',
    apiSecret: 'bfair_session_token_live',
    environment: 'production',
    connectionStatus: 'connected',
    lastTested: '2026-08-21T09:15:00.000Z',
    latencyMs: 42,
    notes: 'Bolsa Esportiva & Liquidez Back/Lay em tempo real',
  },
  pinnacle: {
    bookmakerId: 'pinnacle',
    name: 'Pinnacle',
    enabled: true,
    apiKey: 'pinn_sharp_key_77e6d5c4b3a2f1e0',
    environment: 'production',
    connectionStatus: 'connected',
    lastTested: '2026-08-21T09:15:00.000Z',
    latencyMs: 29,
    notes: 'Sharp Bookmaker com menor margem e maiores limites',
  },
  betano: {
    bookmakerId: 'betano',
    name: 'Betano',
    enabled: true,
    apiKey: 'beta_live_feed_66d5c4b3a2f1e099',
    environment: 'production',
    connectionStatus: 'connected',
    lastTested: '2026-08-21T09:15:00.000Z',
    latencyMs: 51,
    notes: 'SuperOdds & Mercados Especiais de Estatísticas',
  },
  esportivabet: {
    bookmakerId: 'esportivabet',
    name: 'Esportiva Bet',
    enabled: true,
    apiKey: 'espb_live_api_44a3b2c1d0',
    environment: 'production',
    connectionStatus: 'connected',
    lastTested: '2026-08-21T09:20:00.000Z',
    latencyMs: 44,
    notes: 'Casa nacional com saques rápidos via PIX, odds turbinadas e mercados ao vivo',
  },
  sportingbet: {
    bookmakerId: 'sportingbet',
    name: 'Sportingbet',
    enabled: false,
    apiKey: '',
    environment: 'sandbox',
    connectionStatus: 'unconfigured',
    notes: 'Sportsbook Tradicional com Mercados de Gols',
  },
  kto: {
    bookmakerId: 'kto',
    name: 'KTO',
    enabled: false,
    apiKey: '',
    environment: 'sandbox',
    connectionStatus: 'unconfigured',
    notes: 'Mercados Brasileiros e Rápidos',
  },
  superbet: {
    bookmakerId: 'superbet',
    name: 'Superbet',
    enabled: false,
    apiKey: '',
    environment: 'sandbox',
    connectionStatus: 'unconfigured',
    notes: 'SuperPlacar e Cotações Turbinadas',
  },
  '1xbet': {
    bookmakerId: '1xbet',
    name: '1xBet',
    enabled: false,
    apiKey: '',
    environment: 'sandbox',
    connectionStatus: 'unconfigured',
    notes: 'Ampla cobertura de ligas alternativas',
  },
};

export interface BookmakerOdd {
  bookmakerId: BookmakerId;
  name: string;
  shortName: string;
  odd: number;
  marketLabel?: string;
  isBest?: boolean;
}

export interface BettingTipData {
  marketCode: string; // Ex: "OVER_GOL_LIMITE", "FUNIL_CANTOS", "BTTS_YES", "JOGO_QUENTE_CARTOES", "RISCO_EXPULSAO", "UNDER_VALUE", "VIRADA_IMPROVAVEL", "CASHOUT_PROATIVO"
  marketName: string; // Ex: "Over Gol Limite FT (> 1.5)", "Funil de Cantos HT (> 4.5)", "Ambas Marcam: SIM"
  targetSelection: string; // Ex: "Mais de 1.5 Gols", "Back Arsenal", "Próximo Cartão Amarelo"
  probabilityPct: number; // Probabilidade calculada do mercado acontecer (0 a 100%)
  fairOdd: number; // Odd Justa teórica (100 / probabilidade)
  confidence: 'extrema' | 'alta' | 'moderada';
  evStatus: '+EV' | 'NEUTRO' | 'ALERTA';
  edgePct: number; // Vantagem percentual sobre a média das casas
  bookmakerOdds: BookmakerOdd[];
  reasoning: string;
  actionText: string;
}

// ==========================================
// Regras e Alertas Python (Diagnóstico & Turbo)
// ==========================================

export interface OperationalRulesConfig {
  chancesPerGoalRatio: number; // Padrão: 3.0 (3 chances claras para 1 gol). Ajustável pelo usuário!
  ccRateMaxMinutes: number; // Padrão: 15.0 min/CC
  ccRateForteMaxMinutes: number; // Padrão: 12.0 min/CC
  debtMarginXG: number; // Padrão: 1.0
  imminentGoalThresholdPct?: number; // Limiar percentual configurável de variação 5m (Padrão: 50%)
  
  // Regras de Gols & Back
  enableCodigo31: boolean;
  enableTripleDebt: boolean;
  enablePressaoVendavel: boolean;
  enableDominantTrailing: boolean;
  enableV12OverBack: boolean;
  enableImminentGoal: boolean; // Alerta de Gol Iminente (Surto 5m)

  // NOVAS ESTRATÉGIAS DE TRADE ESPORTIVO
  enableFunilCantos: boolean; // Funil de Cantos (Cantos Limite HT/FT)
  enableRaceToCorners: boolean; // Race to Corners (3, 5, 7, 9)
  enableJogoQuenteCards: boolean; // Clima de Cartão / Jogo Quente
  enableRiscoExpulsao: boolean; // Risco de Expulsão (Cartão Vermelho)
  enableAmbasMarcamBTTS: boolean; // Ambas Marcam (BTTS Sim)
  enableUnderValue: boolean; // Under Value / Desaceleração / Fechamento Over
  enableViradaImprovavel: boolean; // Virada Improvável (Lay Zebra / DNB Favorito)
  enableCashoutProativo: boolean; // Sinal de Fechamento de Posição / Cashout

  // Configuração Específica da Regra UNDER VALUE (Intervalo de Tempo e Limiares)
  underValueMinMinute?: number; // Minuto inicial para avaliar Under (Padrão: 25')
  underValueMaxMinute?: number; // Minuto final para avaliar Under (Padrão: 78')
  underValueMaxXg?: number; // Teto de xG combinado (Padrão: 0.60)
  underValueMaxSot?: number; // Teto de chutes no alvo combinados (Padrão: 2)

  // Configuração Específica do FUNIL DE CANTOS (Contagem mínima de escanteios)
  funilCantosMinCornersHt?: number; // Mínimo de escanteios no 1T para HT Limite (Padrão: 2)
  funilCantosMinCornersFt?: number; // Mínimo de escanteios na partida para FT Limite (Padrão: 5)
  funilCantosMaxMinPerCorner?: number; // Ritmo máximo em min/canto (Padrão: 14)

  // Configuração de Faixa de Probabilidade dos Alertas (%)
  minAlertProbabilityPct?: number; // Padrão: 50%
  maxAlertProbabilityPct?: number; // Padrão: 100%

  // Configuração de Casas de Apostas Habilitadas & Chaves de API
  enabledBookmakers: BookmakerId[];
  bookmakerCredentials?: BookmakerApiMap;

  // MOTOR CRAWLER: CATÁLOGO, WATCHLIST & VELOCIDADE (Playwright / Discovery)
  crawlerConfig?: {
    maxWatchlistSize: number; // Padrão: 15 (Capacidade máxima de jogos escaneados por ciclo)
    tier3ReservedSlots: number; // Padrão: 2 (Slots mínimos garantidos para rotação round-robin Tier 3)
    discoveryIntervalSeconds: number; // Padrão: 180 (Varredura do catálogo ao vivo a cada 3 minutos)
    concurrentWorkers: number; // Padrão: 4 (Páginas Playwright abertas em paralelo)
    routeResourceBlock: boolean; // Padrão: true (Bloqueio de imagens, fontes e mídias no Playwright)
    enableBackgroundDiscovery: boolean; // Padrão: true (Descoberta em thread paralela desacoplada)
    autoPruneMinutes: number; // Padrão: 30 (Faxina do catálogo para jogos sumidos)
    catalogPruneMinutes?: number; // Faxina customizável do catálogo
    noStatsBackoffMinutes: number; // Padrão: 10 (Cooldown para partidas sem estatísticas suportadas)
    minEntryMinute: number; // Padrão: 20 (Minuto mínimo para watchlist operacional)
    maxEntryMinute: number; // Padrão: 83 (Minuto máximo para watchlist operacional)
    antiSpamCooldownMinutes: number; // Padrão: 5 (Intervalo mínimo entre repetição de sinais no mesmo jogo)
    tierFilter: {
      enableTier0Signals: boolean; // Posições abertas & sinais recentes
      enableTier05PremiumLeagues: boolean; // Ligas Premium A/B/C
      enableTier12Window: boolean; // Jogos no range 20-83 min
      enableTier3Rotation: boolean; // Rodízio de ligas alternativas
    };
  };

  soundAlertsEnabled: boolean;
  minMinuteAlert: number;
  maxMinuteAlert: number;
}

export type Codigo31AlertType =
  | 'over_bilateral_premium'
  | 'over_premium_xg'
  | 'over_premium'
  | 'back_premium'
  | 'over_forte'
  | 'back_forte'
  | 'over_watch'
  | 'back_watch';

export interface Codigo31Evaluation {
  alertType: Codigo31AlertType | null;
  shouldAlert: boolean;
  reason: string;
  level: 'watch' | 'forte' | 'premium' | null;
  market: 'over' | 'back' | null;
  bucket: number;
  totalCc: number;
  homeCc: number;
  awayCc: number;
  totalGoals: number;
  homeScore: number;
  awayScore: number;
  ccRate: number;
  expectedGoalsByCc: number;
  isDevendoGol: boolean;
  saldoGolsDevidos: number;
  ratioUsed: number;
  dominantTeam: 'home' | 'away' | null;
  dominantName: string;
  dominantCc: number;
  oppCc: number;
  ccDiff: number;
  expectedDominantGoalsByCc: number;
  isDominantDevendoGol: boolean;
  saldoGolsDominante: number;
  isDominantTrailing: boolean;
  dominantLead: number;
  debtorTeamName?: string;
  debtorTeamSide?: 'home' | 'away' | 'both' | null;
  title: string;
  emoji: string;
  motivo: string;
  leitura: string;
  formattedTelegram: string;
  bettingTip?: BettingTipData;
}

export interface TripleDebtEvaluation {
  tripleDebtFormed: boolean;
  scope: 'unilateral' | 'bilateral' | 'none';
  scopeSide: 'home' | 'away' | 'total' | null;
  debtorTeamName?: string;
  ccInScope: number;
  xgInScope: number;
  xgotInScope: number;
  goalsInScope: number;
  expectedGoalsByCc: number;
  ccDebt: boolean;
  xgDebt: boolean;
  xgotDebt: boolean;
  failedReasons: string[];
  blockReason: string | null;
  wouldBlockSignal: boolean;
  statusBadge: string;
  bettingTip?: BettingTipData;
}

export interface PressaoVendavelEvaluation {
  qualified: boolean;
  side: 'home' | 'away' | null;
  team: string;
  minute: number;
  score: string;
  tese: string;
  fairOdd?: number;
  minRecommendedOdd?: number;
  probTarget?: number;
  fails: string[];
  metrics: {
    cc: number;
    xg: number;
    xgot: number;
    shots: number;
    sot: number;
    sotPct: number;
    posse: number;
    toquesArea: number;
    oppXg: number;
  };
  bettingTip?: BettingTipData;
}

export interface DominantTrailingEvaluation {
  dominantSide: 'home' | 'away' | null;
  dominantScore: number;
  opponentScore: number;
  dominantIsTrailing: boolean;
  dominantTrailingBy: number;
  dominantReactionConfirmed: boolean;
  livePressureStatus: 'brutal' | 'forte' | 'neutro' | 'dead';
  entryAllowed: boolean;
  blockReason: string;
  status: 'GOAL_DEBT_ALIVE' | 'GOAL_DEBT_DEAD' | 'DOMINANT_TRAILING_TRAP' | 'DOMINANT_REACTION_CONFIRMED' | 'NOT_TRAILING';
  blockMessage?: string;
}

export interface TraditionalRuleSignal {
  ruleName: string;
  marketTarget: string;
  confidenceTier: string;
  recommendedAction: string;
  trace: string;
}

export interface ImminentGoalEvaluation {
  isImminent: boolean;
  intensity: 'alta' | 'extrema' | 'moderada' | 'nenhuma';
  variationPct5m: number;
  totalChancesLast5: number;
  totalChancesPrev5: number;
  homeChancesLast5: number;
  awayChancesLast5: number;
  effectiveDebt: number;
  targetMarket: 'OVER_GOL_LIMITE' | 'PROXIMO_GOL' | 'BACK_DOMINANTE' | null;
  beneficiaryTeam?: string;
  triggerReason: string;
  confidenceScore: number; // 0-100
  title: string;
  actionText: string;
  bettingTip?: BettingTipData;
}

// ──────────────────────────────────────────
// Interfaces para as Novas Estratégias
// ──────────────────────────────────────────

export interface FunilCantosEvaluation {
  qualified: boolean;
  phase: 'HT_LIMITE' | 'FT_LIMITE' | null;
  minute: number;
  currentCorners: number;
  targetLine: string; // Ex: "Over 4.5 HT" ou "Over 9.5 FT"
  attackingTeam?: string;
  attacksPerMinLast10: number;
  blockedShotsLast10: number;
  bettingTip?: BettingTipData;
}

export interface RaceToCornersEvaluation {
  qualified: boolean;
  targetRace: 3 | 5 | 7 | 9;
  leaderTeam: string;
  leaderSide: 'home' | 'away';
  leaderCorners: number;
  oppCorners: number;
  paceMinPerCorner: number;
  bettingTip?: BettingTipData;
}

export interface JogoQuenteEvaluation {
  qualified: boolean;
  intensity: 'extrema' | 'alta' | 'moderada';
  foulsPerMin: number;
  totalYellows: number;
  recentFoulsStreak: number;
  scoreGap: number;
  bettingTip?: BettingTipData;
}

export interface RiscoExpulsaoEvaluation {
  qualified: boolean;
  riskLevel: 'critico' | 'alto';
  targetTeam: string;
  targetSide: 'home' | 'away';
  yellowsOnTeam: number;
  foulPressure: number;
  bettingTip?: BettingTipData;
}

export interface AmbasMarcamEvaluation {
  qualified: boolean;
  homeXg: number;
  awayXg: number;
  homeSot: number;
  awaySot: number;
  currentScore: string;
  bettingTip?: BettingTipData;
}

export interface UnderValueEvaluation {
  qualified: boolean;
  reason: string;
  totalXg: number;
  variationPct10m: number;
  targetMarket: string;
  bettingTip?: BettingTipData;
}

export interface ViradaImprovavelEvaluation {
  qualified: boolean;
  underdogTeam: string;
  favoriteTeam: string;
  favoriteSide: 'home' | 'away';
  score: string;
  favoritePressure: number;
  favoriteXg: number;
  bettingTip?: BettingTipData;
}

export interface CashoutProativoEvaluation {
  qualified: boolean;
  leadingTeam: string;
  leadingSide: 'home' | 'away';
  pressureDropPct: number;
  opponentPressureRecent: number;
  minute: number;
  score: string;
  bettingTip?: BettingTipData;
}

export interface MatchRulesAnalysis {
  matchId: string;
  ratioConfigured: number;
  codigo31: Codigo31Evaluation;
  tripleDebt: TripleDebtEvaluation;
  pressaoVendavel: PressaoVendavelEvaluation;
  dominantTrailing: DominantTrailingEvaluation;
  imminentGoal?: ImminentGoalEvaluation;
  funilCantos?: FunilCantosEvaluation;
  raceToCorners?: RaceToCornersEvaluation;
  jogoQuente?: JogoQuenteEvaluation;
  riscoExpulsao?: RiscoExpulsaoEvaluation;
  ambasMarcam?: AmbasMarcamEvaluation;
  underValue?: UnderValueEvaluation;
  viradaImprovavel?: ViradaImprovavelEvaluation;
  cashoutProativo?: CashoutProativoEvaluation;
  traditionalSignals: TraditionalRuleSignal[];
  hasActiveOperationalAlert: boolean;
  primaryAlertBadge?: {
    emoji: string;
    label: string;
    level: 'watch' | 'forte' | 'premium';
    market: 'over' | 'back' | 'corners' | 'cards' | 'btts' | 'under';
  };
  activeTips: BettingTipData[];
}

export type UserRole = 'admin' | 'user';
export type UserStatus = 'approved' | 'pending' | 'rejected' | 'blocked';

export interface UserProfile {
  uid: string;
  email: string;
  displayName: string;
  photoURL?: string;
  role: UserRole;
  status: UserStatus;
  crawlerToken: string;
  createdAt: string;
  lastLoginAt: string;
  approvedAt?: string;
  approvedBy?: string;
  rejectionReason?: string;
  notes?: string;
}

export interface UserCustomSettings {
  rulesConfig?: Partial<OperationalRulesConfig>;
  customMatchOrder?: string[];
  sortOption?: string;
  viewMode?: 'grid' | 'carousel' | 'compact';
  audioEnabled?: boolean;
  audioVolume?: number;
  bookmakerLinks?: {
    esportivaBetUrl?: string;
    bet365Url?: string;
    betanoUrl?: string;
    stakeUrl?: string;
  };
}

export const DEFAULT_MODAL_CONFIG: OperationalRulesConfig = {
  chancesPerGoalRatio: 3.0,
  ccRateMaxMinutes: 15.0,
  ccRateForteMaxMinutes: 12.0,
  debtMarginXG: 1.0,
  enableCodigo31: true,
  enableTripleDebt: true,
  enablePressaoVendavel: true,
  enableDominantTrailing: true,
  enableV12OverBack: true,
  enableImminentGoal: true,
  enableFunilCantos: true,
  enableRaceToCorners: true,
  enableJogoQuenteCards: true,
  enableRiscoExpulsao: true,
  enableAmbasMarcamBTTS: true,
  enableUnderValue: true,
  enableViradaImprovavel: true,
  enableCashoutProativo: true,
  underValueMinMinute: 25,
  underValueMaxMinute: 78,
  underValueMaxXg: 0.60,
  underValueMaxSot: 2,
  funilCantosMinCornersHt: 2,
  funilCantosMinCornersFt: 5,
  funilCantosMaxMinPerCorner: 14,
  enabledBookmakers: ['bet365', 'betfair', 'pinnacle', 'betano', 'sportingbet', 'kto', 'superbet', '1xbet'],
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
  minMinuteAlert: 10,
  maxMinuteAlert: 88,
};

export const DEFAULT_OPERATIONAL_CONFIG = DEFAULT_MODAL_CONFIG;



