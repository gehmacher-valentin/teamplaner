// Gemeinsames für alle Browser-Tests: angemeldete Seiten je Rolle und der Fehlerwächter.
import { test as basis, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

export { expect };

export const KONTEN = {
  admin: "admin@example.test",
  leitung: "bereichsleitung@example.test",
  planer: "planer@example.test",
  mitarbeit: "mitarbeiter@example.test",
} as const;
export type Rolle = keyof typeof KONTEN;

export const HANDY = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

/** Gespeicherte Anmeldung der Rolle (legt e2e/einrichten.ts vor dem ersten Test an). */
export const zustand = (rolle: Rolle) => fileURLToPath(new URL(`./.zustand/${rolle}.json`, import.meta.url));

/** Was als Fehler zählt: Konsolenfehler, nicht abgefangene Ausnahmen, Antworten ab Status 400. */
export class Waechter {
  readonly fehler: string[] = [];
  private erlaubt: RegExp[] = [];

  beobachten(seite: Page) {
    seite.on("console", (m) => {
      if (m.type() === "error") this.melden(`Konsole: ${m.text()} (${seite.url()})`);
    });
    seite.on("pageerror", (f) => this.melden(`Ausnahme: ${f.message} (${seite.url()})`));
    seite.on("response", (a) => {
      if (a.status() >= 400) this.melden(`HTTP ${a.status()} ${a.request().method()} ${a.url()}`);
    });
  }

  /** Erwartete Fehler dieses Tests, z. B. ein 403, das der Test selbst auslöst. */
  erlauben(...muster: RegExp[]) {
    this.erlaubt.push(...muster);
  }

  private melden(text: string) {
    this.fehler.push(text);
  }

  unerwartet() {
    return this.fehler.filter((f) => !this.erlaubt.some((m) => m.test(f)));
  }
}

type Hilfen = {
  waechter: Waechter;
  /** Neue Seite in eigenem Browser-Kontext, angemeldet als die Rolle, vom Wächter beobachtet. */
  seiteFuer: (rolle: Rolle, optionen?: Parameters<Browser["newContext"]>[0]) => Promise<Page>;
};

export const test = basis.extend<Hilfen>({
  waechter: [
    async ({}, use) => {
      const waechter = new Waechter();
      await use(waechter);
      expect(waechter.unerwartet(), "Konsolenfehler, Ausnahmen oder Antworten ab 400").toEqual([]);
    },
    { auto: true },
  ],
  seiteFuer: async ({ browser, waechter }, use) => {
    const kontexte: BrowserContext[] = [];
    await use(async (rolle, optionen = {}) => {
      const kontext = await browser.newContext({ storageState: zustand(rolle), ...optionen });
      kontexte.push(kontext);
      const seite = await kontext.newPage();
      waechter.beobachten(seite);
      return seite;
    });
    for (const kontext of kontexte) await kontext.close();
  },
});

/** Nach einer Aktion, die per HTMX oder fetch speichert: warten, bis nichts mehr unterwegs ist. */
export async function ruhe(seite: Page) {
  await seite.waitForLoadState("networkidle");
}

/** Mit der Maus ziehen, in Schritten, damit Ziehen-Erkennung (ab 5 px) und Zielsuche greifen. */
export async function ziehen(seite: Page, von: { x: number; y: number }, nach: { x: number; y: number }) {
  await seite.mouse.move(von.x, von.y);
  await seite.mouse.down();
  await seite.mouse.move(von.x + 8, von.y + 4, { steps: 3 });
  await seite.mouse.move(nach.x, nach.y, { steps: 12 });
  await seite.mouse.move(nach.x, nach.y);
  await seite.mouse.up();
}

export async function mitte(ort: ReturnType<Page["locator"]>) {
  const r = await ort.boundingBox();
  if (!r) throw new Error("Element nicht sichtbar");
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, links: r.x, oben: r.y, breite: r.width, hoehe: r.height };
}
