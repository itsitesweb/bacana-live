/**
 * Safe JSON fetching utility for BacanaLive
 * Prevents "Unexpected token '<', <!doctype..." syntax errors when HTML is returned.
 */

export async function safeFetchJson<T>(url: string, options?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      return null;
    }
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    // Network or JSON parse error handled gracefully
    return null;
  }
}
