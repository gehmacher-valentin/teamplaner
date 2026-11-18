// Ablauf 7: zwei Personen bearbeiten dieselbe Notiz gleichzeitig. Beide sehen die Änderungen der
// anderen ohne Neuladen, nichts wird überschrieben, und jede sieht, wer die Notiz noch bearbeitet.
import type { Page } from "@playwright/test";
import { expect, test } from "./hilfen";

const editor = (seite: Page) => seite.locator("[data-editor='notiz-text'] [contenteditable='true']");

test("Notiz: gleichzeitig bearbeiten, live bei allen, ohne Überschreiben", async ({ seiteFuer }) => {
  const a = await seiteFuer("planer");
  await a.goto("/notizen/");
  await a.getByRole("link", { name: "Besprechung Produktion" }).click();
  await a.getByRole("link", { name: /Wartung Maschinen/ }).first().click();
  await expect(editor(a)).toContainText("Förderband");
  const url = a.url();
  // Die ältere Notiz bekommt beim ersten Öffnen ihren gemeinsamen Stand
  await expect.poll(async () => (await a.request.get(url)).text()).toContain('"aenderungen": ["');

  const b = await seiteFuer("mitarbeit");
  await b.goto(url);
  await expect(editor(b)).toContainText("Förderband");
  // Mitbearbeitende als runder Avatar (Initialen), der Name für Screenreader und beim Zeigen
  const anwesendA = a.locator("#notiz-anwesend").getByRole("img", { name: "Person 01" });
  await expect(anwesendA).toBeVisible();
  await expect(anwesendA.locator(".avatar")).toHaveText("P1");
  await expect(a.locator("#notiz-anwesend")).not.toContainText("Person 01");
  await anwesendA.hover();
  await expect(anwesendA).toHaveAttribute("data-name", "Person 01");
  await expect(b.locator("#notiz-anwesend").getByRole("img", { name: "Person 05" })).toBeVisible();

  // Gleichzeitig tippen: a am Anfang, b am Ende
  await editor(a).click();
  await a.keyboard.press("Control+Home");
  await editor(b).click();
  await b.keyboard.press("Control+End");
  await Promise.all([a.keyboard.type("Zuerst lesen. "), b.keyboard.type(" Termin mit Person 02.")]);
  for (const seite of [a, b]) {
    await expect(editor(seite)).toContainText("Zuerst lesen.");
    await expect(editor(seite)).toContainText("Termin mit Person 02.");
  }

  // Titel live
  await a.locator("#notiz-titel-eingabe").fill("Wartung Maschinen 2027");
  await expect(b.locator("#notiz-titel-eingabe")).toHaveValue("Wartung Maschinen 2027");

  // Gespeichert: eine dritte Person sieht nach dem Öffnen beide Änderungen und den neuen Titel
  await expect.poll(async () => (await a.request.get(url)).text()).toContain("Termin mit Person 02.");
  const c = await seiteFuer("leitung");
  await c.goto(url);
  await expect(c.locator("#notiz-titel-eingabe")).toHaveValue("Wartung Maschinen 2027");
  await expect(editor(c)).toContainText("Zuerst lesen.");
  await expect(editor(c)).toContainText("Termin mit Person 02.");

  // Wer die Seite verlässt, verschwindet aus der Anzeige
  await b.close();
  await expect(a.locator("#notiz-anwesend").getByRole("img", { name: "Person 01" })).toHaveCount(0);
});
