// Ablauf 4: Gantt-Diagramm. Verletzt eine Einteilung aus dem Teamplaner eine Abhängigkeit, steht ein
// Warnzeichen in der Namensspalte und der Pfeil bleibt grau; behoben wird im Teamplaner. Geplante
// Termine ändert man durch Ziehen, Nachfolger rücken nach. Abhängigkeiten anlegen und entfernen.
import type { Page } from "@playwright/test";
import { expect, mitte, test, ziehen } from "./hilfen";

type Daten = {
  aufgaben: Record<string, { id: number; titel: string; beginn: string | null; ende: string | null }>;
  abhaengigkeiten: { id: number; vorher: number; nachher: number; verletzt_plan: boolean; verletzt_ist: boolean }[];
  warnungen: { aufgabe: number; nachher: { titel: string }; vorher: { titel: string } }[];
};

/** Stand auf dem Server, unabhängig von dem, was die Seite gerade anzeigt. */
async function serverdaten(seite: Page): Promise<Daten> {
  return seite.evaluate(async () => {
    const optionen = await (await fetch("/api/gantt/ansichten")).json();
    return (await fetch(`/api/gantt/${optionen.ansichten[0].id}`)).json();
  });
}
const aufgabe = (d: Daten, titel: string) => Object.values(d.aufgaben).find((a) => a.titel === titel)!;
const zeile = (seite: Page, titel: string) => seite.locator(".gt-zeile").filter({ has: seite.locator(".gt-name", { hasText: titel }) });

async function oeffnen(seite: Page) {
  await seite.goto("/gantt/");
  await expect(seite.locator(".gt-zeile--projekt").first()).toBeVisible();
}

test("Gantt: Einteilung verletzt Abhängigkeit, Warnzeichen statt rotem Pfeil, Abhilfe im Teamplaner", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await oeffnen(seite);
  // Demodaten: „Servicewagen ausrüsten“ ist eingeteilt, bevor der Vorgänger „Rahmen Antrieb“ fertig ist
  const vorher = await serverdaten(seite);
  expect(vorher.warnungen.map((w) => w.nachher.titel)).toContain("Servicewagen ausrüsten");
  expect(vorher.abhaengigkeiten.filter((a) => a.verletzt_plan)).toEqual([]);
  await expect(seite.locator(".gt-pfeil").first()).toBeAttached();
  await expect(seite.locator(".gt-pfeil--verletzt"), "kein roter Pfeil ohne Überschneidung der geplanten Balken").toHaveCount(0);
  await expect(seite.locator(".legende")).toContainText("Einteilung verletzt Abhängigkeit");

  // Unteraufgaben eingeklappt: das Warnzeichen steht an der Hauptaufgabe und nennt die betroffene Aufgabe
  const haupt = zeile(seite, "Ausrüstung vorbereiten");
  const zeichen = haupt.locator(".gt-warn");
  await expect(zeichen).toHaveCount(1);
  await expect(zeichen.locator(".gt-warn__hinweis")).toBeHidden();
  await zeichen.focus(); // per Tastatur erreichbar
  await expect(zeichen.locator(".gt-warn__hinweis")).toBeVisible();
  await expect(zeichen.locator(".gt-warn__hinweis")).toContainText("„Servicewagen ausrüsten“: Eingeteilt ab");
  await expect(zeichen.locator(".gt-warn__hinweis")).toContainText("Vorgänger „Rahmen Antrieb“ (Prototyp Förderband)");
  await expect(zeichen.locator(".gt-warn__hinweis")).toContainText("Einteilung im Teamplaner ändern");

  // Aufgeklappt: das Warnzeichen wandert in die Zeile der Unteraufgabe
  await haupt.locator(".gt-klapp").click();
  await expect(zeile(seite, "Servicewagen ausrüsten").locator(".gt-warn")).toHaveCount(1);
  await expect(haupt.locator(".gt-warn")).toHaveCount(0);

  // Geplante Termine im Gantt zu verschieben hilft nicht (das war der gemeldete Fehler: Pfeil blieb rot)
  const balken = zeile(seite, "Servicewagen ausrüsten").locator(".gt-balken");
  const ort = await mitte(balken);
  await ziehen(seite, ort, { x: ort.x + 12 * 14, y: ort.y });
  await expect.poll(async () => aufgabe(await serverdaten(seite), "Servicewagen ausrüsten").beginn)
    .not.toBe(aufgabe(vorher, "Servicewagen ausrüsten").beginn);
  await expect(zeile(seite, "Servicewagen ausrüsten").locator(".gt-warn")).toHaveCount(1);
  await expect(seite.locator(".gt-pfeil--verletzt")).toHaveCount(0);

  // Abhilfe im Teamplaner: die zu frühe Einteilung entfernen
  const planer = await seiteFuer("planer");
  await planer.goto("/");
  const eingeteilt = planer.locator(".tp-balken", { hasText: "Servicewagen ausrüsten" });
  await expect(eingeteilt.first()).toBeVisible();
  for (let n = await eingeteilt.count(); n > 0; n--) {
    await eingeteilt.first().hover();
    await eingeteilt.first().locator(".tp-balken__x").click();
    await expect(eingeteilt).toHaveCount(n - 1);
  }
  await seite.reload();
  await expect(seite.locator(".gt-zeile--projekt").first()).toBeVisible();
  await expect(seite.locator(".gt-warn").first()).toBeVisible(); // die andere Warnung der Demodaten bleibt
  await expect(zeile(seite, "Ausrüstung vorbereiten").locator(".gt-warn")).toHaveCount(0);
  expect((await serverdaten(seite)).warnungen.map((w) => w.nachher.titel)).not.toContain("Servicewagen ausrüsten");
});

test("Gantt: Balken ziehen zieht den Nachfolger nach, Pfeil bleibt grau", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await oeffnen(seite);
  const vorher = await serverdaten(seite);
  const a0 = aufgabe(vorher, "Zeichnungen Antrieb"); // Vorgänger von „Bohrungen Rahmen“
  const b0 = aufgabe(vorher, "Bohrungen Rahmen");

  const balken = zeile(seite, "Zeichnungen Antrieb").locator(".gt-balken");
  const ort = await mitte(balken);
  await ziehen(seite, ort, { x: ort.x + 12 * 21, y: ort.y }); // Maßstab „Monate“: 12 px je Tag, drei Wochen später
  await expect.poll(async () => aufgabe(await serverdaten(seite), "Zeichnungen Antrieb").ende).not.toBe(a0.ende);

  const nachher = await serverdaten(seite);
  const a1 = aufgabe(nachher, "Zeichnungen Antrieb");
  const b1 = aufgabe(nachher, "Bohrungen Rahmen");
  expect(a1.ende! > a0.ende!).toBe(true);
  expect(b1.beginn! > a1.ende!, "Nachfolger beginnt nach dem Ende des Vorgängers").toBe(true);
  expect(b1.beginn! > b0.beginn!, "Nachfolger wurde nachgezogen").toBe(true);
  expect(nachher.abhaengigkeiten.filter((x) => x.verletzt_plan)).toEqual([]);
  await expect(seite.locator(".gt-pfeil--verletzt")).toHaveCount(0);
  // Die Anzeige entspricht dem Stand auf dem Server
  await expect(balken).toHaveAttribute("title", new RegExp(a1.ende!.split("-").reverse().slice(0, 2).join("\\.")));
});

test("Gantt: zwei schnelle Änderungen zeigen den jüngsten Stand", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await oeffnen(seite);
  // Die Antwort auf das erste Neuladen kommt erst nach der auf das zweite an
  let nr = 0;
  await seite.route(/\/api\/gantt\/\d+$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const meine = ++nr;
    const antwort = await route.fetch().catch(() => null);
    if (!antwort) return route.abort().catch(() => {});
    if (meine === 1) await new Promise((fertig) => setTimeout(fertig, 1500));
    await route.fulfill({ response: antwort }).catch(() => {}); // die überholte Anfrage ist bereits abgebrochen
  });
  const eins = zeile(seite, "Regal Lager").locator(".gt-balken");
  const zwei = zeile(seite, "Geländer Galerie").locator(".gt-balken");
  const titelEins = await eins.getAttribute("title");
  const titelZwei = await zwei.getAttribute("title");
  let ort = await mitte(eins);
  await ziehen(seite, ort, { x: ort.x + 12 * 7, y: ort.y });
  ort = await mitte(zwei);
  await ziehen(seite, ort, { x: ort.x + 12 * 7, y: ort.y });
  await seite.waitForTimeout(2500); // länger als die verzögerte erste Antwort
  await expect(eins).not.toHaveAttribute("title", titelEins!);
  await expect(zwei, "die zweite Änderung bleibt sichtbar").not.toHaveAttribute("title", titelZwei!);
  const stand = await serverdaten(seite);
  for (const [ort2, titel] of [[eins, "Regal Lager"], [zwei, "Geländer Galerie"]] as const) {
    const ende = aufgabe(stand, titel).ende!.split("-").reverse().slice(0, 2).join("\\.");
    await expect(ort2).toHaveAttribute("title", new RegExp(ende));
  }
});

test("Gantt: Abhängigkeit anlegen und entfernen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await oeffnen(seite);
  const anzahl = (await serverdaten(seite)).abhaengigkeiten.length;

  const reihe = zeile(seite, "Inventur Werkzeuge");
  await reihe.hover();
  await reihe.getByRole("button", { name: "Termine" }).click();
  const dialog = seite.getByRole("dialog");
  await dialog.getByPlaceholder(/suchen/i).fill("Geländer");
  await dialog.locator(".gt-wahl__karte", { hasText: "Geländer Galerie" }).last().click();
  await expect.poll(async () => (await serverdaten(seite)).abhaengigkeiten.length).toBe(anzahl + 1);
  const d = await serverdaten(seite);
  const neu = d.abhaengigkeiten.find((x) => x.vorher === aufgabe(d, "Geländer Galerie").id && x.nachher === aufgabe(d, "Inventur Werkzeuge").id);
  expect(neu, "Abhängigkeit Geländer Galerie vor Inventur Werkzeuge").toBeTruthy();
  expect(neu!.verletzt_plan).toBe(false);

  await dialog.getByRole("button", { name: /Geländer Galerie/ }).filter({ hasText: "×" }).click();
  const frage = seite.getByRole("dialog").last();
  await frage.getByRole("button", { name: "Entfernen" }).click();
  await expect.poll(async () => (await serverdaten(seite)).abhaengigkeiten.length).toBe(anzahl);
});
