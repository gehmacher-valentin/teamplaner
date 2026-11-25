// @vitest-environment jsdom
// Senden und Abgleich beim gemeinsamen Bearbeiten (gemeinsam.ts) ohne Browser: Warteschlange, erneuter
// Versuch bei 5xx und offline, Neuladen bzw. Anmeldung bei 4xx, Abgleich nach fremden Änderungen.
// E2E 07 prüft nur den Ablauf ohne Fehler.
import type { Editor } from "@tiptap/core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as Y from "yjs";
import { gemeinsamVorbereiten, seitenwechsel, zuBytes, zuText } from "./gemeinsam";

type Anfrage = { url: string; daten: Record<string, unknown>; hintergrund: boolean };

class QuelleStub {
  static CLOSED = 2;
  static letzte: QuelleStub;
  readyState = 1;
  handler = new Map<string, (ev: unknown) => void>();
  constructor(readonly url: string) {
    QuelleStub.letzte = this;
  }
  addEventListener(name: string, fn: (ev: unknown) => void) {
    this.handler.set(name, fn);
  }
  close() {
    this.readyState = QuelleStub.CLOSED;
  }
  senden(name: string, data: unknown, lastEventId = "") {
    this.handler.get(name)?.({ data: JSON.stringify(data), lastEventId });
  }
}

let anfragen: Anfrage[];
let antworten: (number | "offline")[];
let markdown: string;

function startdaten(notiz: number) {
  const vorher = new Y.Doc();
  vorher.getText("titel").insert(0, "Liste");
  return { notiz, zustand: zuText(Y.encodeStateAsUpdate(vorher)), aenderungen: [], ab: 3 };
}

/** Window- und Document-Listener früherer Tests bleiben bestehen: Tests, die sie auslösen, nehmen eine eigene Notiz-ID */
function vorbereiten(notiz = 12) {
  document.body.innerHTML = `
    <script id="start" type="application/json">${JSON.stringify(startdaten(notiz))}</script>
    <div><textarea id="notiz-text">alt</textarea></div>
    <div id="notiz-anwesend"></div>`;
  const gemeinsam = gemeinsamVorbereiten("start", document.querySelector("textarea")!)!;
  const editor = { get isEmpty() { return markdown === ""; }, getMarkdown: () => markdown } as unknown as Editor;
  gemeinsam.starten(editor);
  return gemeinsam.doc;
}

/** Eigene Änderung im Editor (Herkunft lokal, nicht vom Server) */
function tippen(doc: Y.Doc, text: string) {
  markdown += text;
  doc.getText("inhalt-test").insert(doc.getText("inhalt-test").length, text);
}

const aenderungen = () => anfragen.filter((a) => a.url === "/notizen/12/aenderung/");
/** Eingefügter Text eines Updates (ohne den Stand davor, den es nicht enthält) */
const inhalt = (update: unknown) =>
  Y.decodeUpdate(zuBytes(update as string)).structs
    .map((s) => ((s as Y.Item).content as Y.ContentString | undefined)?.str ?? "")
    .join("");

beforeEach(() => {
  vi.useFakeTimers();
  anfragen = [];
  antworten = [];
  markdown = "alt";
  vi.stubGlobal("EventSource", QuelleStub);
  vi.stubGlobal("fetch", vi.fn(async (url: string, optionen: RequestInit) => {
    const kopf = optionen.headers as Record<string, string>;
    anfragen.push({ url, daten: JSON.parse(optionen.body as string), hintergrund: kopf["X-Hintergrund"] === "1" });
    const status = url.endsWith("/aenderung/") ? (antworten.shift() ?? 200) : 204;
    if (status === "offline") throw new TypeError("Failed to fetch");
    return { ok: status < 300, status, json: async () => ({ id: anfragen.length }) } as Response;
  }));
  seitenwechsel.neuLaden = vi.fn();
  seitenwechsel.zurAnmeldung = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Änderungen senden", () => {
  it("sammelt schnelle Änderungen und schickt sie gemeinsam mit Text und Titel", async () => {
    const doc = vorbereiten();
    expect(QuelleStub.letzte.url).toBe("/api/planung/stream/notiz/12?ab=3");
    tippen(doc, " a");
    await vi.advanceTimersByTimeAsync(100);
    tippen(doc, "b");
    expect(aenderungen()).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(300);
    expect(aenderungen()).toHaveLength(1);
    const { daten } = aenderungen()[0];
    expect(inhalt(daten.update)).toBe(" ab");
    expect(daten).toMatchObject({ text: "alt ab", titel: "Liste", eigen: true });
    // Gesendetes geht nicht noch einmal mit
    tippen(doc, "c");
    await vi.advanceTimersByTimeAsync(300);
    expect(aenderungen()).toHaveLength(2);
    expect(inhalt(aenderungen()[1].daten.update)).toBe("c");
  });

  it.each([500, 503, "offline"] as const)("bei %s: nach 3 s erneut, nichts geht verloren", async (fehler) => {
    const doc = vorbereiten();
    antworten.push(fehler);
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    expect(aenderungen()).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(2999);
    expect(aenderungen()).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(aenderungen()).toHaveLength(2);
    expect(inhalt(aenderungen()[1].daten.update)).toBe(" x");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(aenderungen()).toHaveLength(2); // danach ist die Warteschlange leer
    expect(seitenwechsel.neuLaden).not.toHaveBeenCalled();
  });

  it("neue Eingabe während des Wartens auf den erneuten Versuch schickt beides zusammen", async () => {
    const doc = vorbereiten();
    antworten.push(502);
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    tippen(doc, "y");
    await vi.advanceTimersByTimeAsync(300);
    expect(aenderungen().map((a) => inhalt(a.daten.update))).toEqual([" x", " xy"]);
  });

  it("wieder online: sendet sofort, statt auf den nächsten Versuch zu warten", async () => {
    const doc = vorbereiten();
    antworten.push("offline");
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(0);
    expect(aenderungen()).toHaveLength(2);
  });

  it.each([400, 403, 404, 409])("bei %i: Seite neu laden, kein erneuter Versuch", async (status) => {
    const doc = vorbereiten();
    antworten.push(status);
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    expect(seitenwechsel.neuLaden).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(aenderungen()).toHaveLength(1);
  });

  it("bei 401: zur Anmeldung", async () => {
    const doc = vorbereiten();
    antworten.push(401);
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    expect(seitenwechsel.zurAnmeldung).toHaveBeenCalledOnce();
    expect(seitenwechsel.neuLaden).not.toHaveBeenCalled();
  });

  it("während eine Anfrage läuft, wartet die nächste auf deren Antwort", async () => {
    const doc = vorbereiten();
    let freigeben!: () => void;
    const fetchVorher = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn(async (url: string, optionen: RequestInit) => {
      if (!freigeben) await new Promise<void>((weiter) => (freigeben = weiter));
      return fetchVorher(url, optionen);
    }));
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300);
    tippen(doc, "y");
    await vi.advanceTimersByTimeAsync(1000);
    expect(aenderungen()).toHaveLength(0); // erste hängt noch
    freigeben();
    await vi.advanceTimersByTimeAsync(300);
    expect(aenderungen().map((a) => inhalt(a.daten.update))).toEqual([" x", "y"]);
  });
});

describe("Fremde Änderungen", () => {
  function fremdeAenderung(doc: Y.Doc, text: string) {
    const andere = new Y.Doc();
    Y.applyUpdate(andere, Y.encodeStateAsUpdate(doc));
    let update!: Uint8Array;
    andere.on("update", (u: Uint8Array) => (update = u));
    andere.getText("inhalt-test").insert(0, text);
    return zuText(update);
  }

  it("werden übernommen, nicht zurückgeschickt, und der Markdown-Text wird nach 2 s abgeglichen", async () => {
    const doc = vorbereiten();
    QuelleStub.letzte.senden("aenderung", { daten: [fremdeAenderung(doc, "fremd ")] }, "9");
    expect(doc.getText("inhalt-test").toString()).toBe("fremd ");
    markdown = "fremd alt"; // so sieht der Editor den zusammengeführten Stand
    await vi.advanceTimersByTimeAsync(1999);
    expect(aenderungen()).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(aenderungen()).toHaveLength(1);
    expect(aenderungen()[0]).toMatchObject({ daten: { text: "fremd alt", titel: "Liste" }, hintergrund: true });
    expect(aenderungen()[0].daten.update).toBeUndefined();
    // Gleicher Text: kein weiterer Abgleich; neue Verbindung setzt bei der letzten ID auf
    QuelleStub.letzte.senden("aenderung", { daten: [fremdeAenderung(doc, "!")] }, "10");
    await vi.advanceTimersByTimeAsync(2000);
    expect(aenderungen()).toHaveLength(1);
  });

  it("kein Abgleich, solange eigene Änderungen noch nicht gesendet sind", async () => {
    const doc = vorbereiten();
    antworten.push(500);
    tippen(doc, " x");
    await vi.advanceTimersByTimeAsync(300); // schlägt fehl, bleibt in der Warteschlange
    QuelleStub.letzte.senden("aenderung", { daten: [fremdeAenderung(doc, "fremd ")] }, "9");
    markdown = "fremd alt x";
    await vi.advanceTimersByTimeAsync(2000);
    expect(aenderungen().filter((a) => a.daten.update === undefined)).toHaveLength(0);
  });

  it("Verbindungsfehler: neu verbinden mit wachsendem Abstand", async () => {
    vorbereiten();
    const erste = QuelleStub.letzte;
    erste.readyState = QuelleStub.CLOSED;
    erste.senden("error", {});
    await vi.advanceTimersByTimeAsync(1999);
    expect(QuelleStub.letzte).toBe(erste);
    await vi.advanceTimersByTimeAsync(1);
    const zweite = QuelleStub.letzte;
    expect(zweite).not.toBe(erste);
    zweite.readyState = QuelleStub.CLOSED;
    zweite.senden("error", {});
    await vi.advanceTimersByTimeAsync(3999);
    expect(QuelleStub.letzte).toBe(zweite);
    await vi.advanceTimersByTimeAsync(1);
    expect(QuelleStub.letzte).not.toBe(zweite);
  });
});

describe("Anwesenheit", () => {
  const anwesend = (notiz: number) => anfragen.filter((a) => a.url === `/notizen/${notiz}/anwesend/`);

  it("meldet sich beim Verbinden und beim Verlassen ab", async () => {
    vorbereiten(20);
    QuelleStub.letzte.senden("open", {});
    await vi.advanceTimersByTimeAsync(0);
    expect(anwesend(20).map((a) => a.daten.weg)).toEqual([false]);
    window.dispatchEvent(new Event("pagehide"));
    await vi.advanceTimersByTimeAsync(0);
    expect(anwesend(20).map((a) => a.daten.weg)).toEqual([false, true]);
  });

  it("nach dem Löschen der Notiz keine Abmeldung mehr (sie gäbe 404)", async () => {
    vorbereiten(21);
    document.body.insertAdjacentHTML("beforeend",
      `<form id="loeschen" method="post" action="/notizen/21/loeschen/"></form><form id="anderes" action="/notizen/22/loeschen/"></form>`);
    const absenden = (id: string, abbrechen = false) => {
      const ev = new Event("submit", { bubbles: true, cancelable: true });
      if (abbrechen) ev.preventDefault();
      document.getElementById(id)!.dispatchEvent(ev);
    };
    absenden("loeschen", true); // erstes Absenden, von der Rückfrage abgebrochen
    absenden("anderes");
    window.dispatchEvent(new Event("pagehide"));
    await vi.advanceTimersByTimeAsync(0);
    expect(anwesend(21).map((a) => a.daten.weg)).toEqual([true]);
    absenden("loeschen"); // nach „Löschen“ in der Rückfrage
    window.dispatchEvent(new Event("pagehide"));
    await vi.advanceTimersByTimeAsync(0);
    expect(anwesend(21).map((a) => a.daten.weg)).toEqual([true]);
  });
});
