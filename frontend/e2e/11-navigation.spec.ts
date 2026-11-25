// Ablauf 11: Seitennavigation am Desktop. Sie bleibt beim Scrollen des Inhalts stehen, nur die
// Projektliste scrollt, Hauptpunkte und Verwaltung bleiben sichtbar. Legt viele Projekte an und
// läuft deshalb als letzter Ablauf.
import { expect, test } from "./hilfen";
import type { Page } from "@playwright/test";

const LAPTOP = { viewport: { width: 1440, height: 800 } };

async function box(seite: Page, auswahl: string) {
  const r = await seite.locator(auswahl).first().boundingBox();
  if (!r) throw new Error(`${auswahl} nicht sichtbar`);
  return r;
}

async function ganzSichtbarIn(seite: Page, eintrag: string, bereich: string) {
  const e = await box(seite, eintrag);
  const b = await box(seite, bereich);
  return e.y >= b.y - 0.5 && e.y + e.height <= b.y + b.height + 0.5;
}

test("Navigation: wenige Projekte, kein Scrollbereich, Verwaltung unten", async ({ seiteFuer }) => {
  const seite = await seiteFuer("admin");
  await seite.goto("/meine-aufgaben/");
  const liste = seite.locator("[data-projektliste]");
  await expect(liste.locator("a").first()).toBeVisible();
  await expect(liste).not.toHaveAttribute("data-ueberlauf");
  expect(await liste.evaluate((l) => l.scrollHeight <= l.clientHeight + 1)).toBe(true);
  // Verwaltung schließt unten an der Navigation ab, auch mit wenigen Projekten
  const nav = await box(seite, ".seitennav");
  const unten = await box(seite, ".seitennav__unten");
  expect(nav.y + nav.height - (unten.y + unten.height)).toBeLessThan(20);
  expect(unten.y + unten.height).toBeLessThanOrEqual(seite.viewportSize()!.height);
});

test("Navigation: Mitarbeiter:in ohne Verwaltung, Projektliste reicht bis unten", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit");
  await seite.goto("/meine-aufgaben/");
  await expect(seite.locator(".seitennav__unten")).toHaveCount(0);
  const nav = await box(seite, ".seitennav");
  const liste = await box(seite, "[data-projektliste]");
  expect(nav.y + nav.height - (liste.y + liste.height)).toBeLessThan(20);
});

test("Navigation: viele Projekte, nur die Liste scrollt, aktives Projekt sichtbar", async ({ seiteFuer }) => {
  const seite = await seiteFuer("admin", LAPTOP);
  // Projekte ohne Priorität stehen hinten, das letzte davon also ganz unten in der Liste
  await seite.goto("/projekte/neu/");
  const csrf = await seite.locator("input[name=csrfmiddlewaretoken]").first().inputValue();
  for (let i = 1; i <= 24; i++) {
    const antwort = await seite.request.post("/projekte/neu/", {
      form: { csrfmiddlewaretoken: csrf, name: `Zz Navigation ${String(i).padStart(2, "0")}`, farbe: "grau" },
      headers: { Referer: new URL("/projekte/neu/", seite.url()).href },
      maxRedirects: 0,
    });
    expect(antwort.status(), `Projekt ${i} anlegen`).toBe(302);
  }
  await seite.goto("/projekte/");
  const letztes = seite.locator("[data-projektliste] a").last();
  await expect(letztes).toContainText("Zz Navigation");
  const ziel = await letztes.getAttribute("href");

  await seite.goto(ziel!);
  const liste = seite.locator("[data-projektliste]");
  await expect(liste).toHaveAttribute("data-ueberlauf", "");
  await expect(liste).toHaveAttribute("data-mehr-oben", "");
  await expect(liste.locator("[aria-current='page']")).toHaveAttribute("href", ziel!);
  expect(await ganzSichtbarIn(seite, "[data-projektliste] [aria-current='page']", "[data-projektliste]")).toBe(true);

  // Hauptpunkte und Verwaltung bleiben sichtbar, die Navigation scrollt nicht als Ganzes
  const hoehe = seite.viewportSize()!.height;
  await expect(seite.locator(".seitennav__oben a").first()).toBeInViewport();
  const unten = await box(seite, ".seitennav__unten");
  expect(unten.y + unten.height).toBeLessThanOrEqual(hoehe);
  expect(await seite.locator(".seitennav").evaluate((n) => n.scrollHeight <= n.clientHeight + 1)).toBe(true);

  // Inhalt scrollen: die Navigation bleibt an ihrer Position
  const vorher = await box(seite, ".seitennav");
  await seite.evaluate(() => {
    document.getElementById("inhalt")!.style.minHeight = "3000px";
    window.scrollTo(0, 1200);
  });
  await expect.poll(() => seite.evaluate(() => window.scrollY)).toBeGreaterThan(1000);
  const nachher = await box(seite, ".seitennav");
  expect(nachher.y).toBeCloseTo(vorher.y, 0);
  await expect(seite.locator(".seitennav__oben a").first()).toBeInViewport();

  // Die Liste scrollt für sich, die Seite bleibt, wo sie war
  await liste.evaluate((l) => l.scrollTo(0, 0));
  await expect(liste).not.toHaveAttribute("data-mehr-oben");
  await expect(liste).toHaveAttribute("data-mehr-unten", "");
  expect(await seite.evaluate(() => window.scrollY)).toBeGreaterThan(1000);

  // Scrollposition der Liste bleibt beim Seitenwechsel erhalten
  await liste.evaluate((l) => l.scrollTo(0, 120));
  await expect.poll(() => seite.evaluate(() => sessionStorage.getItem("seitennav-projekte"))).toBe("120");
  await seite.locator(".seitennav__oben a", { hasText: "Kalender" }).click();
  await expect(seite).toHaveURL(/\/kalender\//);
  await expect.poll(() => liste.evaluate((l) => l.scrollTop)).toBe(120);

  // Tastatur: der fokussierte Eintrag wird in der Liste sichtbar gescrollt
  await liste.locator("a").last().focus();
  expect(await ganzSichtbarIn(seite, "[data-projektliste] a:focus", "[data-projektliste]")).toBe(true);
});

test("Navigation: sehr niedriges Fenster, die ganze Navigation scrollt statt abzuschneiden", async ({ seiteFuer }) => {
  const seite = await seiteFuer("admin", { viewport: { width: 1280, height: 420 } });
  await seite.goto("/meine-aufgaben/");
  const liste = await box(seite, "[data-projektliste]");
  expect(liste.height).toBeGreaterThanOrEqual(140);
  const nav = seite.locator(".seitennav");
  expect(await nav.evaluate((n) => n.scrollHeight > n.clientHeight)).toBe(true);
  await nav.evaluate((n) => n.scrollTo(0, n.scrollHeight));
  await expect(seite.locator(".seitennav__unten a").last()).toBeInViewport();
});
