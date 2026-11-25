/**
 * Link „Im Teamplaner einteilen“ im Aufgabendetail: /teamplaner/?projekt=<id>&suche=<titel>. Die Palette
 * zeigt dann gleich die Projektliste dieses Projekts, gefiltert auf den Titel (Teamplaner.tsx).
 */
export interface PaletteVorgabe {
  projekt: number;
  suche: string;
}

export function paletteAusAdresse(abfrage: string): PaletteVorgabe | null {
  const parameter = new URLSearchParams(abfrage);
  const projekt = Number(parameter.get("projekt"));
  if (!Number.isInteger(projekt) || projekt <= 0) return null;
  return { projekt, suche: (parameter.get("suche") ?? "").trim() };
}

/** Adresse ohne diese Parameter, damit ein Neuladen die eigene Auswahl nicht wieder überschreibt. */
export function ohnePaletteVorgabe(adresse: string): string {
  const url = new URL(adresse);
  url.searchParams.delete("projekt");
  url.searchParams.delete("suche");
  return url.pathname + url.search + url.hash;
}
