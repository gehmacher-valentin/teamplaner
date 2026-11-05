import { csrfToken, zurAnmeldung } from "../lib/csrf";
import { t } from "./texte";
import type { Abwesenheit, Einteilung, Optionen, PaletteDaten, Raster } from "./typen";

/** Kennung dieses Browser-Tabs – eigene Änderungen werden im Live-Stream ignoriert. */
export const CLIENT_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);

export class ApiFehler extends Error {
  constructor(
    public status: number,
    public code: string,
    nachricht: string,
    public daten: Record<string, unknown> = {},
  ) {
    super(nachricht);
  }
}

/** ``hintergrund``: ohne Zutun der Person (Nachladen nach einem Live-Ereignis) – verlängert die
 *  Sitzung von Admins nicht (Abmeldung nach Inaktivität). */
async function anfrage<T>(methode: string, url: string, body?: unknown, hintergrund = false): Promise<T> {
  const antwort = await fetch(url, {
    method: methode,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      "X-Client-Id": CLIENT_ID,
      ...(hintergrund ? { "X-Hintergrund": "1" } : {}),
    },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (antwort.status === 204) return undefined as T;
  let daten: Record<string, unknown> = {};
  try {
    daten = await antwort.json();
  } catch {
    /* leere Antwort */
  }
  if (!antwort.ok) {
    if (antwort.status === 401) {
      // Sitzung beendet (z. B. Admin nach Inaktivität): zur Anmeldung, nichts mehr anzeigen
      zurAnmeldung();
    }
    if (antwort.status === 403 && !daten.code) {
      throw new ApiFehler(403, "abgemeldet", t("sitzung_abgelaufen"));
    }
    throw new ApiFehler(
      antwort.status,
      String(daten.code ?? "fehler"),
      String(daten.nachricht ?? daten.detail ?? t("speichern_fehler")),
      daten,
    );
  }
  return daten as T;
}

const q = (params: Record<string, string | number | null | undefined>) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();

export const api = {
  optionen: () => anfrage<Optionen>("GET", "/api/planung/ansichten"),
  raster: (ansicht: string, von: string, bis: string, archivierte: boolean, hintergrund = false) =>
    anfrage<Raster>("GET", `/api/planung/raster?${q({ ansicht, von, bis, archivierte: archivierte ? 1 : null })}`,
      undefined, hintergrund),
  palette: (params: { modus: string; projekt?: number | null; gewerk?: number | null; tag?: number | null; q?: string },
    hintergrund = false) =>
    anfrage<PaletteDaten>("GET", `/api/planung/palette?${q(params)}`, undefined, hintergrund),

  einteilungAnlegen: (daten: { aufgabe_id: number; person_id: number; von: string; bis: string; feiertag_bestaetigt?: boolean }) =>
    anfrage<Einteilung>("POST", "/api/planung/einteilungen", daten),
  einteilungAendern: (id: number, daten: { version: number; person_id?: number; von?: string; bis?: string; feiertag_bestaetigt?: boolean }) =>
    anfrage<Einteilung>("PATCH", `/api/planung/einteilungen/${id}`, daten),
  einteilungLoeschen: (id: number, version: number) =>
    anfrage<void>("DELETE", `/api/planung/einteilungen/${id}?version=${version}`),

  abwesenheitAnlegen: (daten: { person_id: number; von: string; bis: string }) =>
    anfrage<Abwesenheit>("POST", "/api/planung/abwesenheiten", daten),
  abwesenheitAendern: (id: number, daten: { version: number; person_id?: number; von?: string; bis?: string }) =>
    anfrage<Abwesenheit>("PATCH", `/api/planung/abwesenheiten/${id}`, daten),
  abwesenheitLoeschen: (id: number, version: number) =>
    anfrage<void>("DELETE", `/api/planung/abwesenheiten/${id}?version=${version}`),

  tagesinfo: (datum: string, text: string) =>
    anfrage<{ datum: string; text: string }>("PUT", `/api/planung/tagesinfo/${datum}`, { text }),
  tagesfreigabe: (datum: string, stufe: string) =>
    anfrage<{ datum: string; stufe: string }>("PUT", `/api/planung/tagesfreigabe/${datum}`, { stufe }),
};
