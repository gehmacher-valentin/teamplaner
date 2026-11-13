// Ablauf 6: Notizen und Bestellungen je einmal anlegen, bearbeiten und wiederfinden.
import { expect, ruhe, test } from "./hilfen";

test("Notiz: anlegen, Text mit Markdown schreiben, über die Suche wiederfinden", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/notizen/");
  await seite.getByRole("link", { name: "Neue Notiz" }).click();

  const titel = seite.locator("#notiz-titel-eingabe");
  await titel.fill("Prüfplan Hebebühne");
  await titel.press("Tab");
  const editor = seite.locator("[data-editor='notiz-text'] [contenteditable='true']");
  await editor.click();
  await seite.keyboard.type("## Offene Punkte");
  await seite.keyboard.press("Enter");
  await seite.keyboard.type("Sichtprüfung Hydraulik vor dem Prüftermin");
  await seite.locator("body").click({ position: { x: 5, y: 5 } }); // Feld verlassen: speichern
  await ruhe(seite);
  await expect(seite).toHaveURL(/\/notizen\/\d+\/$/);

  // Nach dem Neuladen steht alles da, die Überschrift als Überschrift
  await seite.reload();
  await expect(seite.locator("#notiz-titel-eingabe")).toHaveValue("Prüfplan Hebebühne");
  const neuGeladen = seite.locator("[data-editor='notiz-text'] [contenteditable='true']");
  await expect(neuGeladen.locator("h2")).toHaveText("Offene Punkte");
  await expect(neuGeladen).toContainText("Sichtprüfung Hydraulik");

  // Wiederfinden über die Suche (Volltext)
  await seite.goto("/notizen/");
  await seite.locator("#notiz-suche").fill("Hydraulik");
  await seite.locator("#notiz-suche").press("Enter");
  await expect(seite.getByRole("link", { name: /Prüfplan Hebebühne/ }).first()).toBeVisible();

  // Persönliche Notizen sieht niemand sonst
  const andere = await seiteFuer("leitung");
  await andere.goto("/notizen/?q=Hydraulik");
  await expect(andere.getByRole("link", { name: /Prüfplan Hebebühne/ })).toHaveCount(0);
});

test("Bestellung: Zeile anlegen, Status ändern, für alle sichtbar", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/bestellungen/");
  const neu = seite.locator(".bestellzeile--neu");
  await neu.locator("[name='neu-bedarf']").fill("Hydrauliköl HLP 46, 20 Liter");
  await neu.locator("[name='neu-lieferant']").fill("Lieferant Nord");
  await neu.getByRole("button", { name: "Zeile hinzufügen" }).click();

  const zeile = seite.locator("form.bestellzeile:not(.bestellzeile--neu)").filter({ has: seite.locator("textarea[name='bedarf']", { hasText: "Hydrauliköl HLP 46" }) });
  await expect(zeile).toHaveCount(1);
  await expect(neu.locator("[name='neu-bedarf']"), "Eingabezeile ist wieder leer").toHaveValue("");

  // Status direkt in der Zeile ändern
  const status = zeile.locator("select[name='status']");
  const werte = await status.locator("option").evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value));
  await status.selectOption(werte[1]);
  await ruhe(seite);
  await expect(zeile.locator("select[name='status']")).toHaveValue(werte[1]);

  // Eine Liste für alle: auch die Mitarbeiter:in sieht die Zeile mit dem neuen Status
  const andere = await seiteFuer("mitarbeit");
  await andere.goto("/bestellungen/");
  const dort = andere.locator(".bestellzeile").filter({ hasText: "Hydrauliköl HLP 46" });
  await expect(dort).toHaveCount(1);
});
