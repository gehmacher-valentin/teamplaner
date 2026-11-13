// Ablauf 1: alle Seiten der Navigation öffnen, am Desktop und am Handy. Der Fehlerwächter lässt den
// Test bei Konsolenfehlern und Antworten ab 400 scheitern; zusätzlich darf nirgends Vorlagen-Syntax
// als Text stehen (ein mehrzeiliger {# #}-Kommentar wird von Django als Text ausgegeben).
import { expect, HANDY, test, type Rolle } from "./hilfen";
import type { Page } from "@playwright/test";

async function ohneVorlagenreste(seite: Page) {
  const text = await seite.locator("body").innerText();
  const fund = /.{0,40}(\{#|#\}|\{%|%\}).{0,40}/.exec(text)?.[0] ?? "";
  expect(fund, `Vorlagen-Syntax im sichtbaren Text von ${seite.url()}`).toBe("");
}

async function navigation(seite: Page) {
  await seite.goto("/start/");
  const ziele = await seite.locator("header a[href^='/'], nav a[href^='/']").evaluateAll((links) =>
    [...new Set(links.map((a) => a.getAttribute("href")!))].filter((h) => !h.startsWith("/abmelden")));
  expect(ziele.length).toBeGreaterThan(5);
  return ziele;
}

const laeufe: [string, Rolle, object][] = [
  ["Admin am Desktop", "admin", {}],
  ["Planer:in am Desktop", "planer", {}],
  ["Mitarbeiter:in am Handy", "mitarbeit", HANDY],
];

for (const [name, rolle, geraet] of laeufe) {
  test(`Rundgang: ${name}`, async ({ seiteFuer }) => {
    const seite = await seiteFuer(rolle, geraet);
    for (const ziel of await navigation(seite)) {
      const antwort = await seite.goto(ziel);
      expect(antwort?.status(), ziel).toBe(200);
      await seite.waitForLoadState("networkidle");
      await ohneVorlagenreste(seite);
    }
  });
}

test("Rundgang: Einstellungen des Admins", async ({ seiteFuer }) => {
  const seite = await seiteFuer("admin");
  await seite.goto("/einstellungen/");
  const ziele = await seite.locator("main a[href^='/einstellungen/']").evaluateAll((links) =>
    [...new Set(links.map((a) => a.getAttribute("href")!))]);
  expect(ziele.length).toBeGreaterThan(8);
  for (const ziel of ziele) {
    expect((await seite.goto(ziel))?.status(), ziel).toBe(200);
    await ohneVorlagenreste(seite);
  }
});

test("Rundgang: Aufgabe mit Anhang zeigt keine Vorlagenreste", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/aufgaben/1/");
  await seite.locator('input[type="file"]').first().setInputFiles({
    name: "messprotokoll.txt", mimeType: "text/plain", buffer: Buffer.from("Messreihe 1"),
  });
  await seite.getByRole("button", { name: "Hochladen" }).click();
  await expect(seite.locator(".anhaenge")).toContainText("messprotokoll.txt");
  await ohneVorlagenreste(seite);
});
