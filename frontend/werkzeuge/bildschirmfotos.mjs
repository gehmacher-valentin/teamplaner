// Bildschirmfotos für README und Doku (docs/bilder/*.png) aus der laufenden Entwicklungsumgebung.
// Voraussetzung: Entwicklungsserver läuft (docs/entwicklung.md), frische Demodaten (python manage.py demodaten --neu), Frontend gebaut.
//   cd frontend && npm run bildschirmfotos
// Nutzt den installierten Chrome; mit BROWSER=msedge den installierten Edge.
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { anmelden as anmeldenAuf } from "./anmeldung.mjs";

const BASIS = process.env.TEAMPLANER_URL ?? "http://localhost:8000";
const ZIEL = fileURLToPath(new URL("../../docs/bilder/", import.meta.url));
// Breit genug, dass der Teamplaner zwei Wochen samt Seitenleiste zeigt
const DESKTOP = { viewport: { width: 1680, height: 1000 } };
const HANDY = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };

const browser = await chromium.launch({ channel: process.env.BROWSER ?? "chrome" });
await mkdir(ZIEL, { recursive: true });

async function anmelden(email, geraet = DESKTOP) {
  const kontext = await browser.newContext({ ...geraet, locale: "de-AT", colorScheme: "light", reducedMotion: "reduce" });
  return anmeldenAuf(await kontext.newPage(), BASIS, email);
}

async function foto(seite, name, pfad, warteAuf, vorher) {
  await seite.goto(BASIS + pfad);
  await seite.waitForSelector(warteAuf);
  if (vorher) await vorher(seite);
  await seite.waitForTimeout(600); // Schriften, Live-Daten
  await seite.screenshot({ path: `${ZIEL}${name}.png` });
  console.log(`docs/bilder/${name}.png`);
}

const leitung = await anmelden("bereichsleitung@example.test");
await foto(leitung, "teamplaner", "/", ".tp-raster");
await foto(leitung, "projekt", "/projekte/1/", "main");
await foto(leitung, "aufgabe", "/aufgaben/1/", "main");
await foto(leitung, "gantt", "/gantt/", ".gt-zeit");
await foto(leitung, "ansicht", "/einstellungen/ansichten/teamplaner/1/", "main");
await foto(leitung, "notizen", "/notizen/", "main", async (s) => {
  await Promise.all([s.waitForURL(/\/notizen\/\d+\/$/), s.getByRole("link", { name: "Budget Produktion 2027" }).first().click()]);
});
// Die Bestellliste hat elf Spalten: etwas breiter, damit sie ohne Scrollen ganz zu sehen ist
await foto(leitung, "bestellungen", "/bestellungen/", "main", (s) => s.setViewportSize({ width: 1840, height: 1000 }));
await leitung.setViewportSize(DESKTOP.viewport);

const mitarbeit = await anmelden("mitarbeiter@example.test");
await foto(mitarbeit, "kalender", "/kalender/", ".tp-raster");
await foto(mitarbeit, "konto", "/einstellungen/benachrichtigungen/", "main");

const handy = await anmelden("planer@example.test", HANDY);
// Montag wählen, damit das Bild auch am Wochenende Einteilungen zeigt
await foto(handy, "handy", "/", "button[aria-pressed]", (s) => s.locator("button[aria-pressed]").first().click());

await browser.close();
