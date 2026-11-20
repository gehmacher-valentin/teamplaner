// Ablauf 3: Einteilen im Teamplaner. Aufgabe aus der Palette auf Person und Tag ziehen, Balken
// verschieben und verlängern, entfernen und rückgängig machen. Eine zweite Person mit derselben
// Ansicht sieht jede Änderung ohne Neuladen (Live-Verbindung). Dazu der Freitext-Chip neben „Abwesend“.
import type { Locator, Page } from "@playwright/test";
import { expect, mitte, test, ziehen } from "./hilfen";

const AUFGABE = "Rolltor einbauen";
const PERSON = "Person 00";

const zeile = (seite: Page, person: string) =>
  seite.locator(".tp-zeile").filter({ has: seite.locator(".tp-person__name", { hasText: person }) });
const balken = (seite: Page, person: string) => zeile(seite, person).locator(".tp-balken", { hasText: AUFGABE });

/** Spalten zweier aufeinanderfolgender Arbeitstage, damit keine Feiertagsabfrage dazwischenkommt. */
async function zweiArbeitstage(reihe: Locator) {
  const frei = await reihe.locator(".tp-zelle").evaluateAll((zellen) => zellen.map((z) => z.classList.contains("tp-frei")));
  // Drei freie Spalten in Folge: einteilen, um einen Tag verschieben, um einen Tag verlängern
  const start = frei.findIndex((f, i) => !f && frei[i + 1] === false && frei[i + 2] === false);
  expect(start, "drei Arbeitstage in Folge im sichtbaren Zeitraum").toBeGreaterThanOrEqual(0);
  return start;
}

/** Zeitraum aus der Beschriftung des Balkens, z. B. „16.11.–17.11.2026“ oder „16.11.2026“. */
async function zeitraum(ort: Locator) {
  const text = (await ort.getAttribute("aria-label")) ?? "";
  return /(\d{2}\.\d{2}\.(?:\d{4})?(?:–\d{2}\.\d{2}\.\d{4})?)/.exec(text.split(PERSON)[1] ?? "")?.[1] ?? "";
}

test("Einteilen: ziehen, verschieben, verlängern, rückgängig, live bei der zweiten Person", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  const zweite = await seiteFuer("leitung");
  for (const s of [seite, zweite]) {
    await s.goto("/teamplaner/");
    await expect(s.locator(".tp-raster")).toBeVisible();
    await expect(zeile(s, PERSON)).toBeVisible();
    await expect(balken(s, PERSON)).toHaveCount(0);
  }

  const reihe = zeile(seite, PERSON);
  const start = await zweiArbeitstage(reihe);
  const zelle = (i: number) => reihe.locator(".tp-zelle").nth(i);

  // 1. Aus der Palette auf Person und Tag ziehen
  const karte = seite.getByRole("button", { name: `${AUFGABE} – auf Person und Tag ziehen` });
  await karte.scrollIntoViewIfNeeded();
  await ziehen(seite, await mitte(karte), await mitte(zelle(start)));
  await expect(balken(seite, PERSON)).toHaveCount(1);
  await expect(balken(zweite, PERSON), "zweite Person sieht die Einteilung ohne Neuladen").toHaveCount(1);
  const ersterTag = await zeitraum(balken(seite, PERSON));
  expect(ersterTag).not.toBe("");

  // 2. Um einen Tag verschieben
  await ziehen(seite, await mitte(balken(seite, PERSON)), await mitte(zelle(start + 1)));
  await expect.poll(() => zeitraum(balken(seite, PERSON))).not.toBe(ersterTag);
  const verschoben = await zeitraum(balken(seite, PERSON));
  await expect.poll(() => zeitraum(balken(zweite, PERSON))).toBe(verschoben);

  // 3. Am rechten Griff um einen Tag verlängern
  await balken(seite, PERSON).hover();
  const griff = balken(seite, PERSON).locator(".tp-griff--rechts");
  await ziehen(seite, await mitte(griff), await mitte(zelle(start + 2)));
  await expect.poll(() => zeitraum(balken(seite, PERSON))).toContain("–");
  const verlaengert = await zeitraum(balken(seite, PERSON));
  await expect.poll(() => zeitraum(balken(zweite, PERSON))).toBe(verlaengert);

  // Gespeichert, nicht nur angezeigt
  await seite.reload();
  await expect.poll(() => zeitraum(balken(seite, PERSON))).toBe(verlaengert);

  // 4. Entfernen und rückgängig machen
  await balken(seite, PERSON).hover();
  await balken(seite, PERSON).locator(".tp-balken__x").click();
  await expect(balken(seite, PERSON)).toHaveCount(0);
  await expect(balken(zweite, PERSON)).toHaveCount(0);
  await seite.locator(".toast").getByRole("button", { name: "Rückgängig" }).click();
  await expect(balken(seite, PERSON)).toHaveCount(1);
  await expect(balken(zweite, PERSON)).toHaveCount(1);
  await expect.poll(() => zeitraum(balken(seite, PERSON))).toBe(verlaengert);
});

test("Freitext: Chip ziehen, Text eingeben, ändern, entfernen und rückgängig, live bei der zweiten Person", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  const zweite = await seiteFuer("leitung");
  const hinweis = (s: Page, text: string) => zeile(s, PERSON).locator(".tp-balken--freitext", { hasText: text });
  for (const s of [seite, zweite]) {
    await s.goto("/teamplaner/");
    await expect(zeile(s, PERSON)).toBeVisible();
  }
  // Den Knopf „Eintragen …“ gibt es nicht mehr – Dauer und Text kommen per Klick auf den Balken
  await expect(seite.locator(".tp-palette").getByRole("button", { name: "Eintragen …" })).toHaveCount(0);

  // 1. Chip auf Person und Tag ziehen: Dialog fragt nach dem Text
  const chip = seite.getByRole("button", { name: "Freitext – auf Person und Tag ziehen" });
  await ziehen(seite, await mitte(chip), await mitte(zeile(seite, PERSON).locator(".tp-zelle").nth(2)));
  const dialog = seite.getByRole("dialog", { name: "Freitext eintragen" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Text", { exact: true }).fill("Schulung Kran");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(hinweis(seite, "Schulung Kran")).toHaveCount(1);
  await expect(hinweis(zweite, "Schulung Kran"), "zweite Person sieht den Freitext ohne Neuladen").toHaveCount(1);

  // 2. Klick auf den Balken: Text und Dauer ändern
  await hinweis(seite, "Schulung Kran").click();
  const bearbeiten = seite.getByRole("dialog", { name: "Freitext bearbeiten" });
  await bearbeiten.getByLabel("Text", { exact: true }).fill("Messe Wels");
  await bearbeiten.getByRole("button", { name: "Speichern" }).click();
  await expect(hinweis(seite, "Messe Wels")).toHaveCount(1);
  await expect(hinweis(zweite, "Messe Wels")).toHaveCount(1);
  await seite.reload();
  await expect(hinweis(seite, "Messe Wels")).toHaveCount(1);

  // 3. Entfernen und rückgängig machen
  await hinweis(seite, "Messe Wels").hover();
  await hinweis(seite, "Messe Wels").locator(".tp-balken__x").click();
  await expect(hinweis(seite, "Messe Wels")).toHaveCount(0);
  await expect(hinweis(zweite, "Messe Wels")).toHaveCount(0);
  await seite.locator(".toast").getByRole("button", { name: "Rückgängig" }).click();
  await expect(hinweis(seite, "Messe Wels")).toHaveCount(1);
  await expect(hinweis(zweite, "Messe Wels")).toHaveCount(1);
});
