// Bildschirmfotos für README und Doku (docs/bilder/*.png) aus der laufenden Entwicklungsumgebung.
// Voraussetzung: docker compose up, frische Demodaten (python manage.py demodaten --neu), Frontend gebaut.
//   cd frontend && npm run bildschirmfotos
// Nutzt den installierten Chrome; mit BROWSER=msedge den installierten Edge.
import { createHmac } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const BASIS = process.env.TEAMPLANER_URL ?? "http://localhost:8000";
const PASSWORT = process.env.DEMO_PASSWORT ?? "Teamplaner-Demo-2026";
const ZIEL = fileURLToPath(new URL("../../docs/bilder/", import.meta.url));
// Breit genug, dass der Teamplaner zwei Wochen samt Seitenleiste zeigt
const DESKTOP = { viewport: { width: 1680, height: 1000 } };
const HANDY = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };

const browser = await chromium.launch({ channel: process.env.BROWSER ?? "chrome" });
await mkdir(ZIEL, { recursive: true });

function einmalcode(geheimnis) {
  const bits = geheimnis.replace(/\s/g, "").toUpperCase().split("")
    .map((z) => "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(z).toString(2).padStart(5, "0")).join("");
  const schluessel = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const zaehler = Buffer.alloc(8);
  zaehler.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac("sha1", schluessel).update(zaehler).digest();
  return String((hash.readUInt32BE(hash[19] & 15) & 0x7fffffff) % 1000000).padStart(6, "0");
}

async function anmelden(email, geraet = DESKTOP) {
  const kontext = await browser.newContext({ ...geraet, locale: "de-AT", colorScheme: "light", reducedMotion: "reduce" });
  const seite = await kontext.newPage();
  await seite.goto(`${BASIS}/anmelden/`);
  await seite.fill('input[name="username"]', email);
  await seite.fill('input[name="password"]', PASSWORT);
  await Promise.all([seite.waitForURL((url) => !url.pathname.startsWith("/anmelden")), seite.click('button[type="submit"]')]);
  if (seite.url().includes("/zwei-faktor/")) {
    // Pflicht für Admin und Bereichsleitung: einmal einrichten
    await seite.fill('input[name="code"]', einmalcode(await seite.textContent("code.mono")));
    await seite.fill('input[name="passwort"]', PASSWORT);
    await Promise.all([seite.waitForLoadState("load"), seite.click('form.formular button[type="submit"]')]);
  }
  return seite;
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
