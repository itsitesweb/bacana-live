import express from "express";
import path from "path";
import fs from "fs";
import { createServer as createViteServer } from "vite";
import { matchStore } from "./server/matchStore";
import { localConfigManager } from "./server/localConfig";
import { generateTacticalAnalysis } from "./server/geminiService";

async function startServer() {
  const app = express();
  const PORT = 3000;

  // CORS Middleware universal para requisições de crawlers externos e proxies
  app.use((req, res, next) => {
    res.header("Access-Control-Allow-Origin", "*");
    res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH");
    res.header("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept, Authorization, x-webhook-token, x-crawler-token, x-user-token, x-webhook-slug");
    if (req.method === "OPTIONS") {
      return res.status(200).end();
    }
    next();
  });

  // Middlewares com limites aumentados e fallback de parsing
  app.use(express.json({ limit: "25mb" }));
  app.use(express.urlencoded({ extended: true, limit: "25mb" }));
  app.use(express.text({ limit: "25mb", type: ["text/*", "application/javascript"] }));

  // Middleware para extrair JSON mesmo se enviado como string pura
  app.use((req, res, next) => {
    if (typeof req.body === "string" && req.body.trim().startsWith("{")) {
      try {
        req.body = JSON.parse(req.body);
      } catch (e) {}
    }
    next();
  });

  // --- REST API ROUTES ---

  // Health check
  app.get("/api/health", (req, res) => {
    res.json({
      status: "ok",
      serverTime: new Date().toISOString(),
      activeMatchesCount: matchStore.getMatches().length,
      totalPacketsReceived: matchStore.getCrawlerStatus().totalPacketsReceived,
    });
  });

  // Matches list
  app.get("/api/matches", (req, res) => {
    let matches = matchStore.getMatches();
    const includeFinished = req.query.includeFinished === "true" || req.query.all === "true";
    if (!includeFinished) {
      matches = matches.filter((m) => m.status !== "FT" && m.status !== "FINISHED" && m.status !== "ENCERRADO");
    }
    const leagueFilter = req.query.league as string;
    if (leagueFilter && leagueFilter !== "all") {
      matches = matches.filter((m) => m.league?.toLowerCase() === leagueFilter.toLowerCase());
    }
    res.json({ matches, count: matches.length });
  });

  // Refresh matches (purges finished matches and returns fresh live matches)
  app.post("/api/matches/refresh", (req, res) => {
    const cleanedCount = matchStore.clearFinishedMatches();
    const matches = matchStore.getMatches().filter((m) => m.status !== "FT" && m.status !== "FINISHED" && m.status !== "ENCERRADO");
    res.json({
      success: true,
      matches,
      count: matches.length,
      cleanedCount,
      timestamp: new Date().toISOString(),
    });
  });

  // Clear finished matches specifically
  app.delete("/api/matches/finished", (req, res) => {
    const cleanedCount = matchStore.clearFinishedMatches();
    const matches = matchStore.getMatches().filter((m) => m.status !== "FT" && m.status !== "FINISHED" && m.status !== "ENCERRADO");
    res.json({ success: true, cleanedCount, matches, count: matches.length });
  });

  // Single match
  app.get("/api/matches/:id", (req, res) => {
    const match = matchStore.getMatch(req.params.id);
    if (!match) {
      return res.status(404).json({ error: "Partida não encontrada" });
    }
    res.json({ match });
  });

  // Create / Update match manually
  app.post("/api/matches", (req, res) => {
    const match = req.body;
    if (!match || !match.id) {
      return res.status(400).json({ error: "Dados inválidos: campo 'id' obrigatório" });
    }
    matchStore.addOrUpdateMatch(match);
    res.json({ success: true, match });
  });

  // Delete match / Dismiss from current crawler session
  app.delete("/api/matches/:id", (req, res) => {
    if (req.params.id === "all") {
      matchStore.clearAllMatches();
      return res.json({ success: true, message: "Todas as partidas foram limpas." });
    }
    if (req.params.id === "demo") {
      matchStore.clearDemoMatches();
      return res.json({ success: true, message: "Jogos limpos." });
    }
    const success = matchStore.deleteMatch(req.params.id);
    res.json({ success, matchId: req.params.id });
  });

  // Explicit Dismiss Match endpoint (POST)
  app.post("/api/matches/:id/dismiss", (req, res) => {
    const success = matchStore.dismissMatch(req.params.id);
    res.json({ success, matchId: req.params.id, message: "Partida apagada desta sessão do crawler." });
  });

  app.post("/api/matches/dismiss", (req, res) => {
    const id = req.body?.id || req.body?.matchId;
    if (!id) {
      return res.status(400).json({ error: "Campo 'id' ou 'matchId' obrigatório" });
    }
    const success = matchStore.dismissMatch(String(id));
    res.json({ success, matchId: id, message: "Partida apagada desta sessão do crawler." });
  });

  // Get list of dismissed match IDs
  app.get("/api/matches/dismissed", (req, res) => {
    res.json({ dismissedMatchIds: matchStore.getDismissedMatchIds() });
  });

  // Faxina / Limpeza Completa de Catálogo e Jogos Encerrados
  const handleFaxina = (req: express.Request, res: express.Response) => {
    const result = matchStore.executeFaxina();
    res.json({
      success: true,
      ...result,
      timestamp: new Date().toISOString()
    });
  };

  app.post("/api/matches/faxina", handleFaxina);
  app.post("/api/crawler/faxina", handleFaxina);
  app.get("/api/matches/faxina", handleFaxina);
  app.get("/api/crawler/faxina", handleFaxina);

  // --- CUSTOM WEBHOOKS REST & ASYNC INGESTION ENDPOINTS ---

  // List all custom webhooks
  app.get("/api/crawler/webhooks", (req, res) => {
    const webhooks = matchStore.getCustomWebhooks();
    res.json({ webhooks, count: webhooks.length });
  });

  // Create new custom webhook
  app.post("/api/crawler/webhooks", (req, res) => {
    const webhook = matchStore.saveCustomWebhook(req.body);
    res.json({ success: true, webhook });
  });

  // Update existing custom webhook
  app.put("/api/crawler/webhooks/:id", (req, res) => {
    const webhook = matchStore.saveCustomWebhook({ ...req.body, id: req.params.id });
    res.json({ success: true, webhook });
  });

  // Delete custom webhook
  app.delete("/api/crawler/webhooks/:id", (req, res) => {
    const success = matchStore.deleteCustomWebhook(req.params.id);
    res.json({ success });
  });

  // Get webhook delivery logs
  app.get("/api/crawler/webhook-logs", (req, res) => {
    const webhookId = (req.query.webhookId as string) || (req.query.slug as string);
    const logs = matchStore.getWebhookLogs(webhookId);
    res.json({ logs, count: logs.length });
  });

  // Clear webhook delivery logs
  app.delete("/api/crawler/webhook-logs", (req, res) => {
    const webhookId = req.query.webhookId as string;
    matchStore.clearWebhookLogs(webhookId);
    res.json({ success: true });
  });

  // Test send to a webhook from dashboard
  app.post("/api/crawler/webhooks/:id/test", (req, res) => {
    const webhook = matchStore.getCustomWebhook(req.params.id);
    if (!webhook) {
      return res.status(404).json({ error: "Webhook não encontrado" });
    }
    const testPayload = req.body && Object.keys(req.body).length > 0 ? req.body : {
      id: "match-test-webhook",
      league: webhook.targetLeague || "Brasileirão Série A",
      homeTeam: { name: "Time Teste Mandante", shortName: "TTM", logo: "⚽", color: "#2563EB" },
      awayTeam: { name: "Time Teste Visitante", shortName: "TTV", logo: "🛡️", color: "#DC2626" },
      score: { home: 1, away: 0 },
      minute: 37,
      status: "1H",
      stats: {
        possession: { home: 62, away: 38 },
        dangerousAttacks: { home: 28, away: 12 },
        shotsOnTarget: { home: 4, away: 1 },
        corners: { home: 5, away: 1 },
        xG: { home: 1.15, away: 0.28 },
        pressureIndex: { home: 84, away: 32 },
        dangerousAttacksLast10: { home: 7, away: 1 },
      },
    };

    const remoteIp = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "127.0.0.1";
    const result = matchStore.handleCustomWebhookIngestion(webhook.slug, testPayload, remoteIp, webhook.secretToken);
    res.status(result.statusCode).json(result.response);
  });

  // GET handler for Webhook Status Check (allows users/browsers to ping the URL directly)
  const handleWebhookStatusGet = (req: express.Request, res: express.Response) => {
    const slug = req.params.slug || (req.query.slug as string) || "flashscore-live";
    const status = matchStore.getCrawlerStatus();
    res.json({
      status: "active",
      endpoint: req.originalUrl,
      slug,
      method: "POST required for data ingestion",
      matchesActive: matchStore.getMatches().length,
      totalPacketsReceived: status.totalPacketsReceived,
      lastHeartbeat: status.lastHeartbeat,
      message: "Webhook endpoint online e pronto para receber transmissões do crawler Python via POST.",
      timestamp: new Date().toISOString(),
    });
  };

  app.get("/api/crawler/webhook/:slug", handleWebhookStatusGet);
  app.get("/api/crawler/webhook", handleWebhookStatusGet);
  app.get("/api/webhook/:slug", handleWebhookStatusGet);
  app.get("/api/webhook", handleWebhookStatusGet);

  // Custom Webhook Ingestion Receiver (e.g. POST /api/crawler/webhook/flashscore-live)
  const handleWebhookPost = (req: express.Request, res: express.Response) => {
    const slug = (req.params.slug || req.query.slug || req.headers["x-webhook-slug"] || req.body?.webhookSlug || "flashscore-live") as string;
    const token = (req.headers["x-webhook-token"] || req.headers["x-crawler-token"] || req.headers["x-user-token"] || req.headers["authorization"]?.replace(/^Bearer\s+/i, '') || req.query.token) as string | undefined;
    const remoteIp = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "127.0.0.1";
    
    const result = matchStore.handleCustomWebhookIngestion(slug, req.body, remoteIp, token);
    res.status(result.statusCode).json(result.response);
  };

  // Route aliases with and without /api prefix
  app.get("/api/crawler/webhook/:slug", handleWebhookStatusGet);
  app.get("/api/crawler/webhook", handleWebhookStatusGet);
  app.get("/api/webhook/:slug", handleWebhookStatusGet);
  app.get("/api/webhook", handleWebhookStatusGet);
  app.get("/webhook/:slug", handleWebhookStatusGet);
  app.get("/webhook", handleWebhookStatusGet);

  app.post("/api/crawler/webhook/:slug", handleWebhookPost);
  app.post("/api/crawler/webhook", handleWebhookPost);
  app.post("/api/crawler/custom-webhook", handleWebhookPost);
  app.post("/api/webhook/:slug", handleWebhookPost);
  app.post("/api/webhook", handleWebhookPost);
  app.post("/webhook/:slug", handleWebhookPost);
  app.post("/webhook", handleWebhookPost);
  app.post("/crawler/webhook/:slug", handleWebhookPost);

  // --- PYTHON CRAWLER INGESTION ENDPOINTS ---

  // Crawler Match Update Webhook
  const handleDirectMatchUpdate = (req: express.Request, res: express.Response) => {
    const remoteIp = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "127.0.0.1";
    const result = matchStore.ingestCrawlerMatchUpdate(req.body, remoteIp);
    if (!result.success) {
      return res.status(400).json(result);
    }
    res.json(result);
  };

  app.get("/api/crawler/match-update", (req, res) => {
    res.json({
      status: "online",
      endpoint: "/api/crawler/match-update",
      method: "POST required",
      activeMatches: matchStore.getMatches().length,
    });
  });

  app.post("/api/crawler/match-update", handleDirectMatchUpdate);
  app.post("/api/crawler/match", handleDirectMatchUpdate);
  app.post("/api/crawler/matches", handleDirectMatchUpdate);
  app.post("/crawler/match-update", handleDirectMatchUpdate);

  // Crawler Batch Update
  app.post("/api/crawler/batch-update", (req, res) => {
    const matches = Array.isArray(req.body) ? req.body : req.body?.matches || req.body?.data || req.body?.events;
    const remoteIp = (req.headers["x-forwarded-for"] as string) || req.socket.remoteAddress || "127.0.0.1";

    if (!Array.isArray(matches)) {
      return res.status(400).json({ error: "Array de partidas 'matches' obrigatório" });
    }

    const results = matches.map((m) => matchStore.ingestCrawlerMatchUpdate(m, remoteIp));
    res.json({ success: true, processedCount: results.length, results });
  });

  // Crawler Heartbeat
  app.post("/api/crawler/heartbeat", (req, res) => {
    const { crawlerId, activeMatches, version } = req.body || {};
    matchStore.recordHeartbeat(crawlerId, activeMatches, version);
    res.json({
      status: "online",
      serverTime: new Date().toISOString(),
      activeMatchesCount: matchStore.getMatches().length,
    });
  });

  // Crawler Disconnect / Shutdown (Instantly clears live match grid)
  const handleCrawlerDisconnect = (req: express.Request, res: express.Response) => {
    matchStore.disconnectCrawler();
    res.json({
      success: true,
      status: "disconnected",
      message: "Crawler desconectado. Grade de partidas ao vivo zerada instantaneamente.",
      activeMatches: 0,
      timestamp: new Date().toISOString(),
    });
  };

  app.post("/api/crawler/disconnect", handleCrawlerDisconnect);
  app.post("/api/crawler/clear", handleCrawlerDisconnect);
  app.post("/api/crawler/shutdown", handleCrawlerDisconnect);
  app.get("/api/crawler/disconnect", handleCrawlerDisconnect);
  app.get("/api/crawler/clear", handleCrawlerDisconnect);

  // Crawler Status & Telemetry
  app.get("/api/crawler/status", (req, res) => {
    const status = matchStore.getCrawlerStatus();
    const apiKey = matchStore.getApiKey();
    res.json({
      ...status,
      apiKey,
      endpointUrl: "/api/crawler/match-update",
      heartbeatUrl: "/api/crawler/heartbeat",
    });
  });

  // Download / View ready-to-run Python script
  app.get("/api/crawler/script-python", (req, res) => {
    const pythonScript = `"""
BacanaLive - Python Crawler Agent
=================================
Este script extrai/recebe dados de futebol (ex: SofaScore, FlashScore, Bet365 ou APIs locais)
e envia em tempo real para o seu dashboard BacanaLive.

Instalação de dependências:
    pip install requests websocket-client urllib3

Execução:
    python crawler_agent.py
"""

import time
import json
import random
import requests
from datetime import datetime

# URL do seu servidor BacanaLive (Ajuste para sua URL ou http://localhost:3000)
SERVER_URL = "http://localhost:3000"
ENDPOINT_MATCH = f"{SERVER_URL}/api/crawler/match-update"
ENDPOINT_HEARTBEAT = f"{SERVER_URL}/api/crawler/heartbeat"
API_TOKEN = "bacanalive-crawler-live-key-99"

HEADERS = {
    "Content-Type": "application/json",
    "x-crawler-token": API_TOKEN,
    "User-Agent": "BacanaLive-Python-Crawler/1.0"
}

def send_heartbeat():
    try:
        payload = {
            "crawlerId": "py_crawler_sofascore_live",
            "version": "2.4.0",
            "activeMatches": 1,
            "timestamp": datetime.now().isoformat()
        }
        resp = requests.post(ENDPOINT_HEARTBEAT, json=payload, headers=HEADERS, timeout=5)
        print(f"[HEARTBEAT] Status: {resp.status_code} - Conectado ao BacanaLive Server")
    except Exception as e:
        print(f"[ERRO HEARTBEAT] {e}")

def push_match_update(match_data):
    try:
        resp = requests.post(ENDPOINT_MATCH, json=match_data, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            print(f"[SYNC OK] Partida {match_data.get('id')} sincronizada: {resp.json().get('message')}")
        else:
            print(f"[SYNC FALHA] {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERRO SYNC] {e}")

def run_crawler_loop():
    print("=" * 60)
    print("⚽ INICIANDO CRAWLER PYTHON FOOTSTATS LIVE")
    print(f"📡 Enviando dados para: {ENDPOINT_MATCH}")
    print("=" * 60)
    
    # Exemplo de estado de partida monitorada
    match_state = {
        "id": "py-match-gremio-inter",
        "league": "Brasileirão Série A",
        "leagueCountry": "Brasil",
        "stadium": "Arena do Grêmio, Porto Alegre",
        "homeTeam": {
            "name": "Grêmio",
            "shortName": "GRE",
            "logo": "🔵⚫⚪",
            "color": "#0D80BF",
            "form": ["W", "D", "W", "L", "W"]
        },
        "awayTeam": {
            "name": "Internacional",
            "shortName": "INT",
            "logo": "🔴⚪",
            "color": "#E52320",
            "form": ["W", "W", "D", "W", "L"]
        },
        "score": {"home": 0, "away": 0},
        "minute": 15,
        "status": "1H",
        "stats": {
            "possession": {"home": 52, "away": 48},
            "dangerousAttacks": {"home": 14, "away": 11},
            "attacks": {"home": 28, "away": 22},
            "shotsOnTarget": {"home": 2, "away": 1},
            "shotsOffTarget": {"home": 3, "away": 2},
            "blockedShots": {"home": 1, "away": 1},
            "corners": {"home": 3, "away": 1},
            "xG": {"home": 0.42, "away": 0.28},
            "yellowCards": {"home": 1, "away": 2},
            "redCards": {"home": 0, "away": 0},
            "fouls": {"home": 6, "away": 8},
            "passAccuracy": {"home": 83, "away": 81},
            "saves": {"home": 1, "away": 2},
            "pressureIndex": {"home": 68, "away": 42},
            "dangerousAttacksLast10": {"home": 5, "away": 2},
            "apmLast10": {"home": 0.5, "away": 0.2}
        },
        "events": [
            {"id": "ev-1", "minute": 8, "type": "yellow_card", "team": "away", "player": "Alan Patrick", "detail": "Entrada forte no meio-campo"}
        ],
        "odds": {
            "homeWin": 2.20,
            "draw": 3.10,
            "awayWin": 3.40,
            "over25": 2.05,
            "under25": 1.75,
            "bttsYes": 1.85,
            "bttsNo": 1.95,
            "cornerOver95": 1.80
        },
        "notes": "Gre-Nal ao vivo extraído via Python Crawler local."
    }

    loop_count = 0
    while True:
        loop_count += 1
        
        # Envia heartbeat a cada 5 iterações
        if loop_count % 5 == 1:
            send_heartbeat()
            
        # Simula evolução em tempo real do seu crawler
        match_state["minute"] += 1
        if match_state["minute"] > 90:
            match_state["status"] = "FT"
            
        # Flutuações de pressão e estatísticas capturadas
        home_press = min(98, max(15, match_state["stats"]["pressureIndex"]["home"] + random.randint(-12, 14)))
        away_press = min(98, max(15, match_state["stats"]["pressureIndex"]["away"] + random.randint(-12, 14)))
        match_state["stats"]["pressureIndex"]["home"] = home_press
        match_state["stats"]["pressureIndex"]["away"] = away_press
        
        if home_press > 75:
            match_state["stats"]["dangerousAttacks"]["home"] += 1
            match_state["stats"]["dangerousAttacksLast10"]["home"] += 1
            if random.random() > 0.7:
                match_state["stats"]["corners"]["home"] += 1
                match_state["stats"]["xG"]["home"] = round(match_state["stats"]["xG"]["home"] + 0.12, 2)
                
        # Envia pacote para o Dashboard Web
        push_match_update(match_state)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Minuto {match_state['minute']}' | Placar: {match_state['score']['home']} x {match_state['score']['away']} | Pressão: {home_press}% x {away_press}%")
        time.sleep(4)

if __name__ == "__main__":
    run_crawler_loop()
`;
    res.setHeader("Content-Type", "text/x-python");
    res.setHeader("Content-Disposition", 'attachment; filename="footstats_crawler_agent.py"');
    res.send(pythonScript);
  });

  // Download the optimized bridge_web.py with Tier Caching and Catalog Engine
  app.get("/api/crawler/download-bridge", (req, res) => {
    const bridgePath = path.join(process.cwd(), "bridge_web.py");
    if (fs.existsSync(bridgePath)) {
      res.setHeader("Content-Type", "text/x-python");
      res.setHeader("Content-Disposition", 'attachment; filename="bridge_web.py"');
      res.sendFile(bridgePath);
    } else {
      res.status(404).json({ error: "bridge_web.py not found" });
    }
  });

  // --- OPERATIONAL RULES & CÓDIGO 3:1 ENDPOINTS ---

  // Get operational rules config (ratio 3:1, triple debt, etc.)
  app.get("/api/rules/config", (req, res) => {
    res.json({ config: matchStore.getOperationalConfig() });
  });

  // Update operational rules config (dynamic chancesPerGoalRatio, etc.)
  app.post("/api/rules/config", (req, res) => {
    const updated = matchStore.updateOperationalConfig(req.body);
    res.json({ success: true, config: updated });
  });

  app.put("/api/rules/config", (req, res) => {
    const updated = matchStore.updateOperationalConfig(req.body);
    res.json({ success: true, config: updated });
  });

  // Get operational evaluations for all matches
  app.get("/api/rules/analysis", (req, res) => {
    const analysis = matchStore.getAllMatchesRulesAnalysis();
    res.json({ analysis });
  });

  // Get operational evaluation for a specific match
  app.get("/api/rules/analysis/:id", (req, res) => {
    const analysis = matchStore.getMatchRulesAnalysis(req.params.id);
    if (!analysis) {
      return res.status(404).json({ error: "Partida não encontrada para análise de regras" });
    }
    res.json({ analysis });
  });

  // --- BOOKMAKER APIS & CREDENTIALS ENDPOINTS ---
  // Get all bookmaker API configurations & enabled status
  app.get("/api/bookmakers/config", (req, res) => {
    const bookmakers = matchStore.getBookmakerCredentials();
    const enabled = matchStore.getOperationalConfig().enabledBookmakers || [];
    res.json({ bookmakers, enabledBookmakers: enabled });
  });

  // Bulk update bookmaker configs
  app.post("/api/bookmakers/config", (req, res) => {
    const updated = matchStore.updateBookmakerCredentials(req.body);
    const enabled = matchStore.getOperationalConfig().enabledBookmakers || [];
    res.json({ success: true, bookmakers: updated, enabledBookmakers: enabled });
  });

  app.put("/api/bookmakers/config", (req, res) => {
    const updated = matchStore.updateBookmakerCredentials(req.body);
    const enabled = matchStore.getOperationalConfig().enabledBookmakers || [];
    res.json({ success: true, bookmakers: updated, enabledBookmakers: enabled });
  });

  // Update a single bookmaker config
  app.put("/api/bookmakers/:id", (req, res) => {
    try {
      const updated = matchStore.updateSingleBookmakerCredential(req.params.id as any, req.body);
      res.json({ success: true, credential: updated });
    } catch (err: any) {
      res.status(400).json({ error: err.message || "Erro ao atualizar casa de apostas" });
    }
  });

  // Test bookmaker connection / ping API key
  app.post("/api/bookmakers/:id/test", (req, res) => {
    try {
      // If client sent an updated apiKey in body, update it first before testing
      if (req.body && (req.body.apiKey !== undefined || req.body.enabled !== undefined)) {
        matchStore.updateSingleBookmakerCredential(req.params.id as any, req.body);
      }
      const testResult = matchStore.testBookmakerConnection(req.params.id as any);
      res.json(testResult);
    } catch (err: any) {
      res.status(400).json({ error: err.message || "Erro ao testar conexão" });
    }
  });

  // --- ALERTS REST API ---

  // Get alert rules
  app.get("/api/alerts/rules", (req, res) => {
    res.json({ rules: matchStore.getAlertRules() });
  });

  // Save / Update alert rule
  app.post("/api/alerts/rules", (req, res) => {
    const rule = req.body;
    if (!rule || !rule.name) {
      return res.status(400).json({ error: "Nome da regra obrigatório" });
    }
    if (!rule.id) {
      rule.id = "rule-" + Date.now();
      rule.triggerCount = 0;
    }
    const saved = matchStore.saveAlertRule(rule);
    res.json({ success: true, rule: saved });
  });

  // Delete alert rule
  app.delete("/api/alerts/rules/:id", (req, res) => {
    const success = matchStore.deleteAlertRule(req.params.id);
    res.json({ success });
  });

  // Get alert logs
  app.get("/api/alerts/logs", (req, res) => {
    res.json({ logs: matchStore.getAlertLogs() });
  });

  // Mark all alerts as read
  app.post("/api/alerts/read", (req, res) => {
    matchStore.markAlertsAsRead();
    res.json({ success: true });
  });

  // Clear all alerts
  app.post("/api/alerts/clear", (req, res) => {
    matchStore.clearAlertLogs();
    res.json({ success: true });
  });

  // Delete single alert by ID
  app.delete("/api/alerts/logs/:id", (req, res) => {
    const success = matchStore.deleteAlertLog(req.params.id);
    res.json({ success });
  });

  // --- LOCAL CONFIGURATION PERSISTENCE & BACKUP ENDPOINTS ---

  // Noise reduction settings
  app.get("/api/noise-reduction", (req, res) => {
    res.json({ noiseReduction: localConfigManager.getConfig().noiseReduction || {} });
  });

  app.post("/api/noise-reduction", (req, res) => {
    try {
      const current = localConfigManager.getConfig().noiseReduction || {};
      const updated = { ...current, ...req.body };
      localConfigManager.saveToDisk({ noiseReduction: updated });
      res.json({ success: true, noiseReduction: updated });
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Erro ao salvar redução de ruído" });
    }
  });

  // Get current local config + file path
  app.get("/api/config", (req, res) => {
    res.json({
      config: localConfigManager.getConfig(),
      filePath: localConfigManager.getFilePath(),
    });
  });

  // Save / Update local config directly to disk
  app.post("/api/config", (req, res) => {
    try {
      const saved = localConfigManager.saveToDisk(req.body);
      matchStore.loadFromLocalConfig();
      res.json({ success: true, config: saved, message: "Configurações salvas localmente no disco com sucesso." });
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Erro ao salvar configurações no disco" });
    }
  });

  // Export / Download local configuration JSON file
  app.get("/api/config/export", (req, res) => {
    const config = localConfigManager.getConfig();
    const filename = `bacanalive_config_${new Date().toISOString().slice(0, 10)}.json`;
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
    res.send(JSON.stringify(config, null, 2));
  });

  // Import configuration JSON file
  app.post("/api/config/import", (req, res) => {
    const result = localConfigManager.importConfig(req.body);
    if (result.success && result.config) {
      matchStore.applyImportedConfig(result.config);
      return res.json({ success: true, message: result.message, config: result.config });
    }
    res.status(400).json({ success: false, message: result.message });
  });

  // Reset local configuration to defaults
  app.post("/api/config/reset", (req, res) => {
    const defaultCfg = localConfigManager.getDefaultConfig();
    localConfigManager.saveToDisk(defaultCfg);
    matchStore.loadFromLocalConfig();
    res.json({ success: true, config: defaultCfg, message: "Configurações restauradas para o padrão com sucesso." });
  });

  // --- GEMINI AI TACTICAL ANALYSIS ---
  app.post("/api/gemini/analyze", async (req, res) => {
    const { matchId } = req.body;
    if (!matchId) {
      return res.status(400).json({ error: "matchId obrigatório" });
    }
    const match = matchStore.getMatch(matchId);
    if (!match) {
      return res.status(404).json({ error: "Partida não encontrada" });
    }

    try {
      const analysis = await generateTacticalAnalysis(match);
      res.json({ analysis });
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Erro na análise tática" });
    }
  });

  // --- VITE MIDDLEWARE SETUP ---
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`BacanaLive Server rodando em http://0.0.0.0:${PORT}`);
  });
}

startServer();
