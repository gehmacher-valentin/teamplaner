import { csrfToken, zurAnmeldung } from "../lib/csrf";
import type { GDaten, GOptionen } from "./typen";
import { t } from "./texte";

export class GanttFehler extends Error {
  constructor(public status: number, public code: string, nachricht: string) {
    super(nachricht);
  }
}

async function anfrage<T>(methode: string, url: string, body?: unknown): Promise<T> {
  const antwort = await fetch(url, {
    method: methode,
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (antwort.status === 204) return undefined as T;
  let daten: Record<string, unknown> = {};
  try {
    daten = await antwort.json();
  } catch {
    /* leer */
  }
  if (!antwort.ok) {
    if (antwort.status === 401) zurAnmeldung(); // Sitzung abgelaufen
    throw new GanttFehler(antwort.status, String(daten.code ?? "fehler"), String(daten.nachricht ?? daten.detail ?? t("speichern_fehler")));
  }
  return daten as T;
}

export const api = {
  optionen: () => anfrage<GOptionen>("GET", "/api/gantt/ansichten"),
  unteraufgabenOffen: (wert: boolean) => anfrage<{ unteraufgaben_offen: boolean }>("PATCH", "/api/gantt/einstellungen", { unteraufgaben_offen: wert }),
  daten: (ansicht: number) => anfrage<GDaten>("GET", `/api/gantt/${ansicht}`),
  aufgabe: (ansicht: number, id: number, werte: { beginn: string | null; ende: string | null; version: number }) =>
    anfrage<{ version: number }>("PATCH", `/api/gantt/${ansicht}/aufgaben/${id}`, werte),
  projekt: (ansicht: number, id: number, werte: { beginn: string | null; ende: string | null }) =>
    anfrage<void>("PATCH", `/api/gantt/${ansicht}/projekte/${id}`, werte),
  abhaengigkeitAnlegen: (ansicht: number, vorher: number, nachher: number) =>
    anfrage<{ id: number }>("POST", `/api/gantt/${ansicht}/abhaengigkeiten`, { vorher, nachher }),
  abhaengigkeitLoeschen: (ansicht: number, id: number) => anfrage<void>("DELETE", `/api/gantt/${ansicht}/abhaengigkeiten/${id}`),
  projektZuordnen: (ansicht: number, projekt: number, hinzu: boolean) =>
    anfrage<void>(hinzu ? "POST" : "DELETE", `/api/gantt/${ansicht}/projekte/${projekt}/zuordnung`),
};
