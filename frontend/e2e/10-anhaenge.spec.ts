// Ablauf 10: Anhänge über die Kachel hochladen: auswählen, ziehen, verwerfen, hochladen, zu große Datei,
// Auswahl bleibt in der Seitenleiste erhalten, Rückfrage vor dem Verlassen.
import type { Locator, Page } from "@playwright/test";
import { expect, ruhe, test } from "./hilfen";

const datei = (name: string, inhalt = "Messreihe") => ({ name, mimeType: "text/plain", buffer: Buffer.from(inhalt) });
const fertig = (ort: Page | Locator) => ort.locator(".anhang-kachel:not(.anhang-feld)");

/** Dateien aus dem Dateimanager über einem Element ablegen. */
async function ablegen(seite: Page, ziel: Locator, dateien: { name: string; groesse?: number }[], nur: "dragover" | "drop" = "drop") {
  const daten = await seite.evaluateHandle((liste) => {
    const d = new DataTransfer();
    for (const f of liste) d.items.add(new File([new Uint8Array(f.groesse ?? 12)], f.name, { type: "text/plain" }));
    return d;
  }, dateien);
  await ziel.dispatchEvent("dragover", { dataTransfer: daten });
  if (nur === "drop") await ziel.dispatchEvent("drop", { dataTransfer: daten });
}

test("Anhang: auswählen, verwerfen, andere Datei, hochladen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/aufgaben/2/");
  const feld = seite.locator(".anhang-feld");
  const eingabe = feld.locator('input[type="file"]');
  await expect(feld).toContainText("Datei hierher ziehen oder auswählen");
  await expect(feld.getByRole("button", { name: "Hochladen" })).toBeHidden();
  await expect(eingabe).toHaveCSS("clip", "rect(0px, 0px, 0px, 0px)"); // kein Dateifeld des Browsers sichtbar
  const vorher = await fertig(seite).count();

  await eingabe.setInputFiles(datei("falsch.txt"));
  await expect(feld).toContainText("Noch nicht hochgeladen");
  await expect(feld).toContainText("falsch.txt");
  await expect(feld).toContainText("TXT");
  await feld.getByRole("button", { name: "Entfernen" }).click();
  await expect(feld).not.toHaveClass(/anhang-feld--gewaehlt/);
  expect(await eingabe.evaluate((e: HTMLInputElement) => e.files!.length)).toBe(0);

  await eingabe.setInputFiles(datei("erste.txt"));
  await eingabe.setInputFiles(datei("richtig.txt"));
  await expect(feld).toContainText("richtig.txt");
  await expect(fertig(seite)).toHaveCount(vorher);
  await feld.getByRole("button", { name: "Hochladen" }).click();
  await expect(fertig(seite)).toHaveCount(vorher + 1);
  await expect(fertig(seite).last()).toContainText("richtig.txt");
  await expect(seite.locator(".anhang-feld")).not.toHaveClass(/anhang-feld--gewaehlt/);
});

test("Anhang: hineinziehen, mehrere, zu groß, daneben", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/aufgaben/2/");
  const feld = seite.locator(".anhang-feld");
  await ablegen(seite, feld.locator(".anhang-feld__leer"), [{ name: "plan.txt" }], "dragover");
  await expect(feld).toHaveClass(/anhang-feld--ziel/);
  await ablegen(seite, seite.locator("h1, .titel-eingabe").first(), [{ name: "plan.txt" }]);
  await expect(feld).not.toHaveClass(/anhang-feld--(ziel|gewaehlt)/);

  await ablegen(seite, feld, [{ name: "a.txt" }, { name: "b.txt" }]);
  await expect(seite.locator(".toast").filter({ hasText: "Bitte nur eine Datei auf einmal." })).toBeVisible();
  await expect(feld).not.toHaveClass(/anhang-feld--gewaehlt/);

  await ablegen(seite, feld, [{ name: "gross.bin", groesse: 25 * 1024 * 1024 + 1 }]);
  await expect(seite.locator(".toast").filter({ hasText: "„gross.bin“ ist zu groß (höchstens 25 MB)." })).toBeVisible();
  await expect(feld).not.toHaveClass(/anhang-feld--gewaehlt/);

  await ablegen(seite, feld, [{ name: "gezogen.txt" }]);
  await expect(feld).toContainText("gezogen.txt");
  await feld.getByRole("button", { name: "Hochladen" }).click();
  await expect(fertig(seite).last()).toContainText("gezogen.txt");
});

test("Anhang: Rückfrage beim Verlassen der Seite", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/aufgaben/2/");
  await seite.locator('.anhang-feld input[type="file"]').setInputFiles(datei("vergessen.txt"));
  await seite.locator("h2").first().click(); // der Browser fragt nur nach einer Eingabe auf der Seite
  const art = new Promise<string>((gefragt) => {
    seite.once("dialog", async (frage) => {
      await frage.dismiss();
      gefragt(frage.type());
    });
  });
  await seite.locator(".pfad a").first().click({ noWaitAfter: true });
  expect(await art).toBe("beforeunload");
  await expect(seite).toHaveURL(/\/aufgaben\/2\/$/);
  await expect(seite.locator(".anhang-feld")).toContainText("vergessen.txt");
  await seite.locator(".anhang-feld").getByRole("button", { name: "Entfernen" }).click();
});

test("Anhang in der Seitenleiste: Auswahl bleibt, Schließen fragt nach, hochladen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/aufgaben/2/");
  const projekt = await seite.locator(".pfad a[href*='/projekte/']").last().getAttribute("href");
  await seite.goto(`${projekt}?aufgabe=2`);
  const leiste = seite.locator("#seitenleiste");
  const feld = leiste.locator(".anhang-feld");
  await feld.locator('input[type="file"]').setInputFiles(datei("leiste.txt"));
  await expect(feld).toContainText("leiste.txt");

  // Ein Kommentar lädt den Inhalt der Seitenleiste neu, die Auswahl bleibt
  await leiste.locator('.kommentare textarea, textarea[name="text"]').last().fill("Anhang folgt");
  await leiste.getByRole("button", { name: "Kommentieren" }).click();
  await expect(leiste.locator(".kommentar__text").last()).toContainText("Anhang folgt");
  await expect(feld).toContainText("leiste.txt");
  expect(await feld.locator('input[type="file"]').evaluate((e: HTMLInputElement) => e.files![0]?.name)).toBe("leiste.txt");

  // Schließen: erst nachfragen
  await leiste.locator("[data-seitenleiste-schliessen]").click();
  const frage = seite.getByRole("dialog", { name: /noch nicht hochgeladen/ });
  await frage.getByRole("button", { name: "Abbrechen" }).click();
  await expect(feld).toContainText("leiste.txt");

  await feld.getByRole("button", { name: "Hochladen" }).click();
  await expect(fertig(leiste).last()).toContainText("leiste.txt");
  await expect(feld).not.toHaveClass(/anhang-feld--gewaehlt/);
  await ruhe(seite);

  // Verwerfen schließt
  await feld.locator('input[type="file"]').setInputFiles(datei("weg.txt"));
  await leiste.locator("[data-seitenleiste-schliessen]").click();
  await frage.getByRole("button", { name: "Verwerfen" }).click();
  await expect(leiste).toBeHidden();
  await seite.reload();
  await expect(seite.locator("body")).not.toContainText("weg.txt");
});

test("Anhang an einer Notiz: hochladen und löschen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/notizen/");
  await seite.getByRole("link", { name: "Neue Notiz" }).click();
  await seite.locator("#notiz-titel-eingabe").fill("Anhangprobe");
  await seite.locator("#notiz-titel-eingabe").press("Tab");
  await expect(seite).toHaveURL(/\/notizen\/\d+\/$/);
  const feld = seite.locator(".anhang-feld");
  await feld.locator('input[type="file"]').setInputFiles(datei("notiz.txt"));
  await feld.getByRole("button", { name: "Hochladen" }).click();
  await expect(fertig(seite)).toContainText("notiz.txt");
  await fertig(seite).getByRole("button", { name: /Anhang löschen/ }).click();
  await seite.getByRole("dialog").getByRole("button", { name: "Löschen" }).click();
  await expect(fertig(seite)).toHaveCount(0);
});
