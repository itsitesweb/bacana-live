import fs from "fs";
import path from "path";
import { OperationalRulesConfig, AlertRule, CustomWebhookEndpoint, AVAILABLE_BOOKMAKERS, DEFAULT_BOOKMAKER_CREDENTIALS } from "../src/types";
import { DEFAULT_RULES_CONFIG } from "./rulesEngine";

export interface LocalConfigFile {
  version: string;
  savedAt: string;
  userProfile: {
    displayName: string;
    role: "admin";
    status: "approved";
    crawlerToken: string;
    mode: "local_standalone";
  };
  preferences: {
    viewMode: "grid" | "carousel" | "compact";
    sortOption: string;
    soundEnabled: boolean;
    customMatchOrder: string[];
    leagueFilter: string;
  };
  noiseReduction?: {
    hideFinishedMatches: boolean;
    mutedMatchIds: Record<string, boolean>;
    enabledCategories: Record<string, boolean>;
    selectedMatchFilter: string;
  };
  operationalConfig: OperationalRulesConfig;
  alertRules: AlertRule[];
  customWebhooks: CustomWebhookEndpoint[];
  customUserSettings: Record<string, any>;
}

const DATA_DIR = path.join(process.cwd(), "data");
const CONFIG_FILE_PATH = path.join(DATA_DIR, "bacanalive_config.json");

// Default initial clean rules
export const DEFAULT_LOCAL_ALERT_RULES: AlertRule[] = [
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
    triggerCount: 0,
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
    triggerCount: 0,
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
    triggerCount: 0,
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
    messageTemplate: "📊 xG DIVERGENTE: {dominantTeam} com superioridade técnica maciça ({higherXg} x {lowerXg} xG, dif. +{xgDiff}) aos {minute}', empurrando as linhas e sufocando o {underdogTeam}.",
    triggerCount: 0,
  },
];

export const DEFAULT_LOCAL_WEBHOOKS: CustomWebhookEndpoint[] = [
  {
    id: "wh-flashscore-live",
    name: "FlashScore Live Crawler BR",
    slug: "flashscore-live",
    secretToken: "sec_flashscore_982a17f",
    description: "Recepção assíncrona minuto a minuto do crawler FlashScore / Playwright (xG, xGOT, Chutes, Big Chances).",
    active: true,
    asyncMode: true,
    autoTriggerAlerts: true,
    autoComputeMomentum: true,
    targetLeague: "Brasileirão Série A / Libertadores / Premier League",
    createdAt: new Date().toISOString(),
    totalCalls: 0,
    lastStatus: "ok",
  },
];

export class LocalConfigManager {
  private currentConfig: LocalConfigFile;

  constructor() {
    this.ensureDataDir();
    this.currentConfig = this.loadFromDisk();
  }

  private ensureDataDir(): void {
    try {
      if (!fs.existsSync(DATA_DIR)) {
        fs.mkdirSync(DATA_DIR, { recursive: true });
      }
    } catch (err) {
      console.error("Erro ao criar pasta data/:", err);
    }
  }

  public getDefaultConfig(): LocalConfigFile {
    return {
      version: "2.5.0-standalone-local",
      savedAt: new Date().toISOString(),
      userProfile: {
        displayName: "Trader Local Pro",
        role: "admin",
        status: "approved",
        crawlerToken: "footstats-crawler-live-key-99",
        mode: "local_standalone",
      },
      preferences: {
        viewMode: "carousel",
        sortOption: "debt_desc",
        soundEnabled: true,
        customMatchOrder: [],
        leagueFilter: "all",
      },
      noiseReduction: {
        hideFinishedMatches: true,
        mutedMatchIds: {},
        enabledCategories: {
          imminent_goal: true,
          back_dominant: true,
          triple_debt: true,
          goal_debt_over: true,
          corners: true,
          cards: true,
          btts_ambas: true,
          under_value: true,
          virada_turnaround: true,
          cashout: true,
          pressao_blitz: true,
        },
        selectedMatchFilter: "all",
      },
      operationalConfig: {
        ...DEFAULT_RULES_CONFIG,
        bookmakerCredentials: { ...DEFAULT_BOOKMAKER_CREDENTIALS },
        enabledBookmakers: ['bet365', 'betfair', 'pinnacle', 'betano', 'esportivabet', 'sportingbet', 'kto', 'superbet', '1xbet'],
      },
      alertRules: [...DEFAULT_LOCAL_ALERT_RULES],
      customWebhooks: [...DEFAULT_LOCAL_WEBHOOKS],
      customUserSettings: {},
    };
  }

  private loadFromDisk(): LocalConfigFile {
    try {
      if (fs.existsSync(CONFIG_FILE_PATH)) {
        const raw = fs.readFileSync(CONFIG_FILE_PATH, "utf-8");
        const parsed = JSON.parse(raw);
        console.log("💾 [LOCAL CONFIG] Configurações carregadas com sucesso de:", CONFIG_FILE_PATH);
        const defaults = this.getDefaultConfig();
        return {
          ...defaults,
          ...parsed,
          userProfile: {
            ...defaults.userProfile,
            ...(parsed.userProfile || {}),
          },
          preferences: {
            ...defaults.preferences,
            ...(parsed.preferences || {}),
          },
          noiseReduction: {
            ...defaults.noiseReduction!,
            ...(parsed.noiseReduction || {}),
          },
          operationalConfig: {
            ...defaults.operationalConfig,
            ...(parsed.operationalConfig || {}),
            bookmakerCredentials: {
              ...(defaults.operationalConfig.bookmakerCredentials || DEFAULT_BOOKMAKER_CREDENTIALS),
              ...(parsed.operationalConfig?.bookmakerCredentials || {}),
            } as any,
          },
          alertRules: Array.isArray(parsed.alertRules) ? parsed.alertRules : defaults.alertRules,
          customWebhooks: Array.isArray(parsed.customWebhooks) ? parsed.customWebhooks : defaults.customWebhooks,
        };
      }
    } catch (err) {
      console.error("⚠️ [LOCAL CONFIG] Falha ao ler arquivo de configuração local, inicializando padrão:", err);
    }

    const defaultCfg = this.getDefaultConfig();
    this.saveToDisk(defaultCfg);
    return defaultCfg;
  }

  public saveToDisk(config?: Partial<LocalConfigFile>): LocalConfigFile {
    try {
      this.ensureDataDir();
      if (config) {
        this.currentConfig = {
          ...this.currentConfig,
          ...config,
          userProfile: config.userProfile
            ? { ...this.currentConfig.userProfile, ...config.userProfile }
            : this.currentConfig.userProfile,
          preferences: config.preferences
            ? { ...this.currentConfig.preferences, ...config.preferences }
            : this.currentConfig.preferences,
          noiseReduction: config.noiseReduction
            ? { ...(this.currentConfig.noiseReduction || {}), ...config.noiseReduction }
            : this.currentConfig.noiseReduction,
          operationalConfig: config.operationalConfig
            ? ({
                ...this.currentConfig.operationalConfig,
                ...config.operationalConfig,
                bookmakerCredentials: {
                  ...(this.currentConfig.operationalConfig?.bookmakerCredentials || DEFAULT_BOOKMAKER_CREDENTIALS),
                  ...(config.operationalConfig.bookmakerCredentials || {}),
                },
              } as any)
            : this.currentConfig.operationalConfig,
          alertRules: Array.isArray(config.alertRules)
            ? config.alertRules
            : this.currentConfig.alertRules,
          customWebhooks: Array.isArray(config.customWebhooks)
            ? config.customWebhooks
            : this.currentConfig.customWebhooks,
          customUserSettings: config.customUserSettings
            ? { ...(this.currentConfig.customUserSettings || {}), ...config.customUserSettings }
            : this.currentConfig.customUserSettings,
          savedAt: new Date().toISOString(),
        };
      } else {
        this.currentConfig.savedAt = new Date().toISOString();
      }

      fs.writeFileSync(CONFIG_FILE_PATH, JSON.stringify(this.currentConfig, null, 2), "utf-8");
      console.log(`💾 [LOCAL CONFIG] Arquivo salvo em ${CONFIG_FILE_PATH} (${new Date().toISOString()})`);
      return this.currentConfig;
    } catch (err) {
      console.error("❌ [LOCAL CONFIG] Erro ao gravar arquivo local:", err);
      return this.currentConfig;
    }
  }

  public getConfig(): LocalConfigFile {
    return this.currentConfig;
  }

  public getFilePath(): string {
    return CONFIG_FILE_PATH;
  }

  public importConfig(newConfigData: any): { success: boolean; message: string; config?: LocalConfigFile } {
    try {
      if (!newConfigData || typeof newConfigData !== "object") {
        return { success: false, message: "JSON inválido ou vazio." };
      }

      const merged: LocalConfigFile = {
        ...this.getDefaultConfig(),
        ...newConfigData,
        savedAt: new Date().toISOString(),
      };

      this.currentConfig = merged;
      this.saveToDisk(this.currentConfig);

      return {
        success: true,
        message: "Configurações importadas e salvas no disco com sucesso!",
        config: this.currentConfig,
      };
    } catch (err: any) {
      return {
        success: false,
        message: `Falha ao importar configuração: ${err?.message || "Erro desconhecido"}`,
      };
    }
  }
}

export const localConfigManager = new LocalConfigManager();
