// Ablauf 5: Aufgabe in der Projektliste anlegen, in der Seitenleiste direkt bearbeiten, mit
// @-Erwähnung kommentieren und einen Anhang hochladen. Die erwähnte Person findet den Kommentar
// im Posteingang.
import { expect, ruhe, test } from "./hilfen";

const TITEL = "Messprotokoll Hallenboden";

test("Aufgabe: anlegen, in der Seitenleiste bearbeiten, erwähnen, Anhang, Posteingang", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/projekte/1/");

  // Anlegen in der Liste
  const neu = seite.locator(".neue-aufgabe input[name='titel']").first();
  await neu.fill(TITEL);
  await neu.press("Enter");
  const zeile = seite.locator(".aufgabe-zeile", { hasText: TITEL });
  await expect(zeile).toHaveCount(1);
  await expect(neu, "Eingabefeld ist für die nächste Aufgabe wieder leer").toHaveValue("");

  // Seitenleiste neben der Liste
  await zeile.locator(".aufgabe-titel").click();
  const leiste = seite.locator("#seitenleiste, .seitenleiste").first();
  await expect(leiste.locator(".titel-eingabe")).toHaveValue(TITEL);

  // Titel direkt bearbeiten: gespeichert beim Verlassen, die Zeile in der Liste zieht mit
  const titel = leiste.locator(".titel-eingabe");
  await titel.fill(`${TITEL} Nord`);
  await titel.press("Enter");
  await expect(seite.locator(".aufgabe-zeile", { hasText: `${TITEL} Nord` })).toHaveCount(1);

  // Kommentar mit @-Erwähnung über die Vorschlagsliste
  const feld = leiste.locator("textarea[name='text']");
  await feld.click();
  await feld.pressSequentially("Bitte gegenlesen @Person 01");
  const vorschlag = leiste.locator(".vorschlaege [role='option']", { hasText: "Person 01" }).first();
  await expect(vorschlag).toBeVisible();
  await vorschlag.click();
  await leiste.getByRole("button", { name: "Kommentieren" }).click();
  await expect(leiste.locator(".kommentar__text").last()).toContainText("Bitte gegenlesen");
  await expect(leiste.locator(".kommentar__text").last()).toContainText("Person 01");

  // Anhang hochladen
  await leiste.locator("input[type='file']").setInputFiles({
    name: "messprotokoll.txt", mimeType: "text/plain", buffer: Buffer.from("Messreihe 1: in Ordnung"),
  });
  await leiste.getByRole("button", { name: "Hochladen" }).click();
  await expect(leiste.locator(".anhaenge")).toContainText("messprotokoll.txt");
  await ruhe(seite);

  // Alles gespeichert: die eigene Seite der Aufgabe zeigt Titel, Kommentar und Anhang
  await seite.reload();
  const eintrag = seite.locator(".aufgabe-zeile", { hasText: `${TITEL} Nord` });
  await expect(eintrag).toHaveCount(1);
  await seite.goto((await eintrag.locator(".aufgabe-titel").getAttribute("href"))!);
  await expect(seite.locator(".titel-eingabe")).toHaveValue(`${TITEL} Nord`);
  await expect(seite.locator(".kommentar__text")).toContainText("Bitte gegenlesen");
  await expect(seite.locator(".anhaenge")).toContainText("messprotokoll.txt");

  // Die erwähnte Person (Person 01) sieht die Erwähnung im Posteingang
  const erwaehnt = await seiteFuer("mitarbeit");
  await erwaehnt.goto("/posteingang/");
  const meldung = erwaehnt.locator("main").getByText(`${TITEL} Nord`).first();
  await expect(meldung).toBeVisible();
});
