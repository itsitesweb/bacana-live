import { Match } from "../types";

/**
 * Extrai o ID limpo de 8 caracteres alfanuméricos do Flashscore (ex: YZKrXNd5 ou vBft9bGL).
 * Remove prefixos como 'fs_', 'FS_', 'g_1_', etc.
 */
export function extractCleanFlashscoreId(input?: string | null): string {
  if (!input || typeof input !== "string") return "";
  
  // Se for uma URL completa com parâmetro ?mid= ou &mid= (ex: .../?mid=YZKrXNd5)
  const midParamMatch = input.match(/[?&]mid=([a-zA-Z0-9]{6,14})/i);
  if (midParamMatch && midParamMatch[1]) {
    return midParamMatch[1].replace(/^(?:fs_|FS_|g_1_)/i, "");
  }

  // Se for uma URL de jogo (ex: /jogo/YZKrXNd5/... ou /jogo/futebol/.../YZKrXNd5)
  const urlMatch = input.match(/\/jogo\/(?:futebol\/[^/]+\/[^/]+\/)?(?:FS_|fs_|g_1_)?([a-zA-Z0-9]{6,14})/i);
  if (urlMatch && urlMatch[1]) {
    return urlMatch[1].replace(/^(?:fs_|FS_|g_1_)/i, "");
  }

  // Se for um ID puro ou com prefixo (ex: FS_YZKrXNd5, fs_YZKrXNd5, g_1_YZKrXNd5)
  const cleaned = input
    .replace(/^https?:\/\/[^/]+/i, "")
    .replace(/^(?:fs_|FS_|g_1_|match-)/i, "")
    .replace(/[/?#].*$/, "")
    .trim();

  if (/^[a-zA-Z0-9]{6,14}$/.test(cleaned)) {
    return cleaned;
  }

  return "";
}

/**
 * Retorna o link direto e limpo para o jogo no Flashscore:
 * https://www.flashscore.com.br/jogo/{ID}
 */
export function getFlashscoreUrl(matchOrId: Match | string | undefined | null, fallbackUrlOrId?: string): string {
  if (!matchOrId && !fallbackUrlOrId) {
    return "https://www.flashscore.com.br/";
  }

  // 1. Se foi passado um objeto Match
  if (typeof matchOrId === "object" && matchOrId !== null) {
    const match = matchOrId as Match;

    // Extrair ID limpo dos vários campos possíveis
    const idFromUrl = extractCleanFlashscoreId(match.url);
    const idFromSource = extractCleanFlashscoreId(match.crawlerSourceId);
    const idFromMatchId = extractCleanFlashscoreId(match.id);
    const cleanId = idFromUrl || idFromSource || idFromMatchId;

    if (cleanId) {
      return `https://www.flashscore.com.br/jogo/${cleanId}`;
    }

    // Fallback: busca pelos nomes dos times se não tiver ID
    const h = typeof match.homeTeam?.name === "object" ? (match.homeTeam.name as any)?.name : match.homeTeam?.name || "";
    const a = typeof match.awayTeam?.name === "object" ? (match.awayTeam.name as any)?.name : match.awayTeam?.name || "";
    if (h || a) {
      const q = encodeURIComponent(`${h} ${a}`.trim());
      return `https://www.flashscore.com.br/busca/?q=${q}`;
    }
  }

  // 2. Se foi passado string como primeiro parâmetro ou fallback
  const firstStr = typeof matchOrId === "string" ? matchOrId : "";
  const cleanId = extractCleanFlashscoreId(firstStr) || extractCleanFlashscoreId(fallbackUrlOrId);

  if (cleanId) {
    return `https://www.flashscore.com.br/jogo/${cleanId}`;
  }

  return "https://www.flashscore.com.br/";
}




