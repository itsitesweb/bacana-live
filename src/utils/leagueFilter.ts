/**
 * League & Match Filter Utility
 * Detects and filters out Women's leagues and E-Soccer / Virtual leagues.
 */

export function isIgnoredLeague(
  leagueName?: string,
  country?: string,
  homeTeamName?: string,
  awayTeamName?: string
): boolean {
  const combined = [
    leagueName || "",
    country || "",
    homeTeamName || "",
    awayTeamName || "",
  ]
    .join(" ")
    .toLowerCase();

  if (!combined.trim()) return false;

  // 1. E-Soccer / Virtual & Simulated leagues
  const esoccerPatterns = [
    /\besoccer\b/i,
    /\be-soccer\b/i,
    /\besports\b/i,
    /\be-sports\b/i,
    /\bcyber\b/i,
    /\bvirtual\b/i,
    /\bgt league\b/i,
    /\bgt battle\b/i,
    /\bfifa\b/i,
    /\bpes\b/i,
    /\bfifa volta\b/i,
    /\bvolta football\b/i,
    /\b2x2\b/i,
    /\b3x3\b/i,
    /\b4x4\b/i,
    /\b5x5\b/i,
    /\b6x6\b/i,
    /\b7x7\b/i,
    /\b8x8\b/i,
    /\bgg league\b/i,
    /\bh2h gg\b/i,
    /\be-football\b/i,
    /\befootball\b/i,
    /\bpenalty shootout\b/i,
    /\bsrl\b/i,
    /\bsimulated\b/i,
    /\bshort football\b/i,
    /\bbattle 8m\b/i,
    /\bbattle 10m\b/i,
    /\bbattle 12m\b/i,
  ];

  for (const pattern of esoccerPatterns) {
    if (pattern.test(combined)) {
      return true;
    }
  }

  // 2. Women's Football / Ligas Femininas
  const womenPatterns = [
    /\bfeminino\b/i,
    /\bfeminina\b/i,
    /\bwomen\b/i,
    /\bwoman\b/i,
    /\bladies\b/i,
    /\bfrauen\b/i,
    /\bdames\b/i,
    /\bfemmes\b/i,
    /\bdamen\b/i,
    /\bkvinner\b/i,
    /\bnaiset\b/i,
    /\bmulheres\b/i,
    /\b\(w\)\b/i,
    /\b\[w\]\b/i,
    /\b\(f\)\b/i,
    /\b\[f\]\b/i,
    /\b\(fem\)\b/i,
    /\bwfc\b/i,
    /\bffc\b/i,
    /\bwomen's\b/i,
    /\bfem\.\b/i,
  ];

  for (const pattern of womenPatterns) {
    if (pattern.test(combined)) {
      return true;
    }
  }

  return false;
}
