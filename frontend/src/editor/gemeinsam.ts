/**
 * Notizen gemeinsam bearbeiten (Server: notizen/live.py). Der Inhalt liegt in einem Yjs-Dokument
 * (Feld „inhalt“ für den Editor, Text „titel“ für den Titel); gleichzeitige Änderungen führt Yjs
 * zusammen, nichts wird überschrieben. Eigene Änderungen gehen gesammelt an den Server, der sie speichert
 * und per Server-Sent Events an alle offenen Seiten der Notiz verteilt. Titel und Markdown schickt der
 * Browser mit, damit Suche, Vorschau und Lesende den aktuellen Stand haben.
 *
 * Eine Notiz ohne Yjs-Stand (älter oder gerade angelegt) bekommt ihn vom ersten Browser, der sie
 * öffnet (/start/); wer dabei zu spät kommt, lädt neu. Wer schreiben darf, meldet sich regelmäßig als
 * anwesend; die Namen der anderen stehen neben dem Titel.
 */
import type { Editor } from "@tiptap/core";
import * as Y from "yjs";
import { csrfToken, zurAnmeldung } from "../lib/csrf";

interface Startdaten {
  notiz: number | null;
  zustand: string;
  aenderungen: string[];
  ab: number;
}

/** Herkunft von Änderungen, die vom Server kommen (nicht zurückschicken) */
const FERN = "fern";
const SENDEN_NACH_MS = 300;
const ABGLEICH_NACH_MS = 2000;
const ANWESEND_ALLE_MS = 20000;
const ANWESEND_GILT_MS = 50000;
const ZUSAMMENFASSEN_AB = 200;

export function zuBytes(text: string): Uint8Array {
  const roh = atob(text);
  const bytes = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) bytes[i] = roh.charCodeAt(i);
  return bytes;
}

export function zuText(bytes: Uint8Array): string {
  let roh = "";
  for (let i = 0; i < bytes.length; i += 0x8000) roh += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(roh);
}

/** Text so ändern, dass nur der geänderte Abschnitt ersetzt wird (gleichzeitige Änderungen bleiben erhalten). */
export function textAngleichen(ytext: Y.Text, neu: string) {
  const alt = ytext.toString();
  if (alt === neu) return;
  let vorne = 0;
  while (vorne < alt.length && vorne < neu.length && alt[vorne] === neu[vorne]) vorne++;
  let hinten = 0;
  while (hinten < alt.length - vorne && hinten < neu.length - vorne && alt[alt.length - 1 - hinten] === neu[neu.length - 1 - hinten]) hinten++;
  ytext.doc!.transact(() => {
    if (alt.length - vorne - hinten > 0) ytext.delete(vorne, alt.length - vorne - hinten);
    if (neu.length - vorne - hinten > 0) ytext.insert(vorne, neu.slice(vorne, neu.length - hinten));
  });
}

/** Cursorposition nach einer fremden Änderung (Yjs-Delta) verschieben. */
export function positionNachAenderung(pos: number, delta: { retain?: number; insert?: unknown; delete?: number }[]): number {
  let stelle = 0;
  let ergebnis = pos;
  for (const d of delta) {
    if (d.retain) stelle += d.retain;
    else if (typeof d.insert === "string") {
      if (stelle <= pos) ergebnis += d.insert.length;
      stelle += d.insert.length;
    } else if (d.delete) {
      if (stelle < pos) ergebnis -= Math.min(d.delete, pos - stelle);
    }
  }
  return Math.max(0, ergebnis);
}

async function senden(url: string, daten: unknown, hintergrund = false): Promise<Response> {
  const kopf: Record<string, string> = { "Content-Type": "application/json", "X-CSRFToken": csrfToken() };
  if (hintergrund) kopf["X-Hintergrund"] = "1";
  return fetch(url, { method: "POST", headers: kopf, body: JSON.stringify(daten), credentials: "same-origin", keepalive: true });
}

export interface Gemeinsam {
  doc: Y.Doc;
  /** Nach dem Anlegen des Editors: Stand herstellen, verbinden */
  starten: (editor: Editor) => void;
}

export function gemeinsamVorbereiten(datenId: string, feld: HTMLTextAreaElement): Gemeinsam | null {
  const quelle = document.getElementById(datenId);
  if (!quelle?.textContent) return null;
  const start = JSON.parse(quelle.textContent) as Startdaten;
  const doc = new Y.Doc();
  if (start.zustand) Y.applyUpdate(doc, zuBytes(start.zustand), FERN);
  for (const a of start.aenderungen) Y.applyUpdate(doc, zuBytes(a), FERN);
  const leer = !start.zustand && start.aenderungen.length === 0;
  const schreiben = !feld.readOnly && !feld.disabled;
  const ytitel = doc.getText("titel");
  const client = Math.random().toString(36).slice(2) + Date.now().toString(36);

  let editor: Editor;
  let notiz = start.notiz;
  let ab = start.ab;
  let seitZustand = start.aenderungen.length;
  let erfasst = false; // ab hier zählt jede eigene Änderung als zu senden
  let bereit = false; // Server hat einen Stand: senden und empfangen
  const warteschlange: Uint8Array[] = [];
  let sendetGerade = false;
  let sendenTimer = 0;
  let abgleichTimer = 0;
  let zuletztGesendet = feld.value;

  const markdown = () => (editor.isEmpty ? "" : editor.getMarkdown());
  const titelFeld = () => document.getElementById("notiz-titel-eingabe") as HTMLInputElement | null;
  const titel = () => titelFeld()?.value ?? ytitel.toString();
  const neuLaden = () => window.location.reload();

  const fehler = (antwort: Response) => {
    if (antwort.status === 401) zurAnmeldung();
    else if (antwort.status === 400 || antwort.status === 403 || antwort.status === 404 || antwort.status === 409) neuLaden();
  };

  const senden_ = async () => {
    window.clearTimeout(sendenTimer);
    if (!bereit || sendetGerade || !warteschlange.length || notiz === null) return;
    sendetGerade = true;
    const anzahl = warteschlange.length;
    const text = markdown();
    try {
      const antwort = await senden(`/notizen/${notiz}/aenderung/`, {
        update: zuText(Y.mergeUpdates(warteschlange.slice(0, anzahl))), text, titel: titel(), eigen: true,
      });
      if (antwort.ok) {
        warteschlange.splice(0, anzahl);
        zuletztGesendet = text;
      } else if (antwort.status >= 500) {
        sendenTimer = window.setTimeout(senden_, 3000);
      } else {
        fehler(antwort);
      }
    } catch {
      sendenTimer = window.setTimeout(senden_, 3000); // offline: später erneut, nichts geht verloren
    } finally {
      sendetGerade = false;
    }
    if (warteschlange.length && !sendenTimer) sendenTimer = window.setTimeout(senden_, SENDEN_NACH_MS);
  };

  // Nach fremden Änderungen den gespeicherten Markdown-Text auf den zusammengeführten Stand bringen
  const abgleichen = () => {
    window.clearTimeout(abgleichTimer);
    abgleichTimer = window.setTimeout(async () => {
      if (!schreiben || !bereit || notiz === null || warteschlange.length) return;
      const text = markdown();
      if (text === zuletztGesendet) return;
      zuletztGesendet = text;
      try {
        await senden(`/notizen/${notiz}/aenderung/`, { text, titel: titel() }, true);
      } catch { /* beim nächsten Mal */ }
    }, ABGLEICH_NACH_MS);
  };

  doc.on("update", (update: Uint8Array, herkunft: unknown) => {
    if (herkunft === FERN || !erfasst || !schreiben) return;
    warteschlange.push(update);
    window.clearTimeout(sendenTimer);
    sendenTimer = window.setTimeout(senden_, SENDEN_NACH_MS);
  });

  // ---------- Titel ----------
  const titelZeigen = (ereignis?: Y.YTextEvent) => {
    const wert = ytitel.toString();
    const eingabe = titelFeld();
    if (eingabe) {
      if (eingabe.value !== wert) {
        const aktiv = document.activeElement === eingabe;
        const a = eingabe.selectionStart ?? wert.length;
        const b = eingabe.selectionEnd ?? a;
        eingabe.value = wert;
        if (aktiv && ereignis) {
          const delta = ereignis.changes.delta as { retain?: number; insert?: unknown; delete?: number }[];
          eingabe.setSelectionRange(positionNachAenderung(a, delta), positionNachAenderung(b, delta));
        }
      }
      eingabe.defaultValue = wert;
    } else if (wert) {
      const kopf = document.querySelector("#notiz-titel h2");
      if (kopf) kopf.textContent = wert;
    }
  };
  ytitel.observe((ereignis) => {
    if (ereignis.transaction.origin === FERN) titelZeigen(ereignis);
  });
  if (schreiben) {
    document.addEventListener("input", (ev) => {
      if ((ev.target as HTMLElement).id === "notiz-titel-eingabe") textAngleichen(ytitel, (ev.target as HTMLInputElement).value);
    });
    // Sobald die Notiz gemeinsam gespeichert wird, speichert der Titel nicht mehr über das Formular
    document.addEventListener("change", (ev) => {
      if ((ev.target as HTMLElement).id === "notiz-titel-eingabe" && notiz !== null) {
        ev.stopPropagation();
        (ev.target as HTMLInputElement).defaultValue = (ev.target as HTMLInputElement).value;
      }
    }, true);
  }

  // ---------- Anwesend ----------
  const anwesende = new Map<string, { name: string; person: number; bis: number }>();
  let eigenePerson = -1;
  let antwortTimer = 0;
  const anwesendZeigen = () => {
    const ort = document.getElementById("notiz-anwesend");
    if (!ort) return;
    const jetzt = Date.now();
    const namen = new Map<number, string>();
    for (const [id, a] of anwesende) {
      if (a.bis < jetzt) anwesende.delete(id);
      else if (a.person !== eigenePerson) namen.set(a.person, a.name);
    }
    ort.replaceChildren(...[...namen.values()].sort((x, y) => x.localeCompare(y)).map((name) => {
      const s = document.createElement("span");
      s.className = "tag";
      s.textContent = name;
      return s;
    }));
  };
  const melden = (weg = false) => {
    if (!schreiben || notiz === null) return;
    senden(`/notizen/${notiz}/anwesend/`, { client, weg }, true).catch(() => undefined);
  };

  // ---------- Live-Verbindung ----------
  const verbinden = () => {
    let wartezeit = 2000;
    let quelleOffen: EventSource;
    const oeffnen = () => {
      const q = new EventSource(`/api/planung/stream/notiz/${notiz}?ab=${ab}`);
      quelleOffen = q;
      q.addEventListener("open", () => { wartezeit = 2000; melden(); });
      q.addEventListener("aenderung", (ev) => {
        const daten = JSON.parse((ev as MessageEvent).data) as { daten: string[] };
        doc.transact(() => {
          for (const d of daten.daten) Y.applyUpdate(doc, zuBytes(d), FERN);
        }, FERN);
        const id = Number((ev as MessageEvent).lastEventId);
        if (id) ab = id;
        seitZustand += daten.daten.length;
        zeigen();
        abgleichen();
        if (schreiben && seitZustand >= ZUSAMMENFASSEN_AB && !warteschlange.length) {
          seitZustand = 0;
          senden(`/notizen/${notiz}/zusammenfassen/`, { zustand: zuText(Y.encodeStateAsUpdate(doc)), bis: ab }, true)
            .catch(() => undefined);
        }
      });
      q.addEventListener("da", (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { client: string; person: number; name: string; weg: boolean };
        if (d.client === client) {
          eigenePerson = d.person;
        } else if (d.weg) {
          anwesende.delete(d.client);
        } else {
          // Neu dazugekommen: gleich antworten, damit die andere Seite uns auch sieht
          if (!anwesende.has(d.client) && !antwortTimer) {
            antwortTimer = window.setTimeout(() => { antwortTimer = 0; melden(); }, 200);
          }
          anwesende.set(d.client, { name: d.name, person: d.person, bis: Date.now() + ANWESEND_GILT_MS });
        }
        anwesendZeigen();
      });
      q.addEventListener("error", () => {
        // Bei einer Fehlerantwort gibt der Browser auf – dann selbst mit wachsendem Abstand neu verbinden
        if (q.readyState === EventSource.CLOSED) {
          window.setTimeout(oeffnen, wartezeit);
          wartezeit = Math.min(wartezeit * 2, 30000);
        }
      });
    };
    oeffnen();
    window.setInterval(() => { melden(); anwesendZeigen(); }, ANWESEND_ALLE_MS);
    window.addEventListener("pagehide", () => { melden(true); quelleOffen?.close(); });
    window.addEventListener("online", () => { if (warteschlange.length) senden_(); });
  };

  // Lesende sehen zunächst die Anzeige vom Server, ab dem ersten Stand den Editor
  const zeigen = () => {
    if (schreiben) return;
    const html = document.getElementById("notiz-html");
    if (!html || html.hidden || (leer && !doc.getXmlFragment("inhalt").length && !ytitel.length)) return;
    html.hidden = true;
    (feld.parentElement as HTMLElement).hidden = false;
  };

  // Ersten Stand anlegen (ältere oder gerade angelegte Notiz)
  const anlegen = async () => {
    erfasst = true;
    const zustand = zuText(Y.encodeStateAsUpdate(doc));
    const text = markdown();
    try {
      const antwort = await senden(`/notizen/${notiz}/start/`, { zustand, text, titel: titel() });
      if (!antwort.ok) return fehler(antwort);
      ab = 0; // der eigene Start kommt über die Verbindung zurück und schadet nicht
      zuletztGesendet = text;
      bereit = true;
      verbinden();
      if (warteschlange.length) senden_();
    } catch {
      window.setTimeout(neuLaden, 3000);
    }
  };

  return {
    doc,
    starten(e: Editor) {
      editor = e;
      if (notiz === null) {
        // Neue Notiz: Der Titel legt sie an (notiz_speichern); danach gemeinsam weiter
        const pruefen = () => {
          const wert = (document.querySelector('#notiz-zustand input[name="notiz"]') as HTMLInputElement | null)?.value;
          if (notiz === null && wert) {
            notiz = Number(wert);
            document.removeEventListener("htmx:afterSettle", pruefen);
            // Der Titel kann vor dem Laden des Skripts getippt worden sein (input-Ereignis verpasst)
            textAngleichen(ytitel, titelFeld()?.value ?? "");
            anlegen();
          }
        };
        document.addEventListener("htmx:afterSettle", pruefen);
        return;
      }
      if (leer && schreiben) {
        // Vorhandenen Text übernehmen, ohne dass „Rückgängig“ ihn wieder löscht
        e.chain().setMeta("addToHistory", false).setContent(feld.value, { contentType: "markdown" }).run();
        textAngleichen(ytitel, titelFeld()?.value ?? "");
        anlegen();
        return;
      }
      // Ältere Stände ohne Titel im Yjs-Dokument: den Titel vom Server behalten und nachtragen
      const titelNachtragen = schreiben && !ytitel.length && Boolean(titelFeld()?.value);
      if (!leer && !titelNachtragen) titelZeigen();
      erfasst = true;
      bereit = true;
      zeigen();
      verbinden();
      if (titelNachtragen) textAngleichen(ytitel, titelFeld()!.value);
    },
  };
}
