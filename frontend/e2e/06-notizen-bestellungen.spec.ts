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
  await seite.locator("body").click({ position: { x: 5, y: 5 } });
  await expect(seite).toHaveURL(/\/notizen\/\d+\/$/);
  // Gespeichert wird laufend (gemeinsames Bearbeiten): warten, bis der Server den Text hat
  await expect.poll(async () => (await seite.request.get(seite.url())).text()).toContain("Sichtprüfung Hydraulik");

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

test("Eigene Dialoge statt Browser-Dialog: Link im Editor, Notiz löschen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  seite.on("dialog", (d) => {
    throw new Error(`Browser-Dialog aufgegangen: ${d.message()}`);
  });
  await seite.goto("/notizen/");
  await seite.getByRole("link", { name: "Neue Notiz" }).click();
  await seite.locator("#notiz-titel-eingabe").fill("Dialogprobe");
  await seite.locator("#notiz-titel-eingabe").press("Tab");
  const editor = seite.locator("[data-editor='notiz-text'] [contenteditable='true']");
  await editor.click();
  await seite.keyboard.type("Webseite");
  await seite.keyboard.press("Shift+Home");

  // Link: Adresse im eigenen Dialog
  await seite.getByRole("button", { name: "Link", exact: true }).click();
  const link = seite.getByRole("dialog", { name: "Adresse des Links (leer = entfernen)" });
  await link.getByRole("textbox").fill("https://boku.ac.at");
  await link.getByRole("button", { name: "Übernehmen" }).click();
  await expect(link).toHaveCount(0);
  await expect(editor.locator('a[href="https://boku.ac.at"]')).toHaveText("Webseite");
  await expect(seite).toHaveURL(/\/notizen\/\d+\/$/);

  // Löschen: Abbrechen lässt die Notiz stehen, Bestätigen löscht sie
  await seite.getByRole("button", { name: "Löschen", exact: true }).click();
  const frage = seite.getByRole("dialog", { name: "Notiz endgültig löschen?" });
  await expect(frage.getByRole("button", { name: "Abbrechen" })).toBeFocused();
  await frage.getByRole("button", { name: "Abbrechen" }).click();
  await expect(frage).toHaveCount(0);
  await expect(seite.locator("#notiz-titel-eingabe")).toHaveValue("Dialogprobe");

  await seite.getByRole("button", { name: "Löschen", exact: true }).click();
  await frage.getByRole("button", { name: "Löschen" }).click();
  await expect(seite).not.toHaveURL(/\/notizen\/\d+\/$/);
  await seite.goto("/notizen/?q=Dialogprobe");
  await expect(seite.getByRole("link", { name: /Dialogprobe/ })).toHaveCount(0);
});

test("Editor: Schriftfarbe, Marker und Überschrift bleiben nach dem Neuladen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/notizen/");
  await seite.getByRole("link", { name: "Neue Notiz" }).click();
  await seite.locator("#notiz-titel-eingabe").fill("Farbprobe");
  await seite.locator("#notiz-titel-eingabe").press("Tab");
  const editor = seite.locator("[data-editor='notiz-text'] [contenteditable='true']");
  await editor.click();
  // Erst den Text, dann formatieren (Farben setzen sich sonst in der nächsten Zeile fort);
  // Wörter per Doppelklick auswählen, das ist stabiler als Pfeiltasten. Der Absatz ist so breit wie
  // der Editor: auf das Wort am Zeilenanfang klicken, nicht in die Mitte
  for (const [i, zeile] of ["Achtung", "wichtig", "Ablauf"].entries()) {
    if (i) await seite.keyboard.press("Enter");
    await seite.keyboard.type(zeile);
  }
  const wort = { position: { x: 12, y: 8 } };
  await seite.locator('.editor__leiste button[title="Überschrift 3"]').click();
  await editor.getByText("wichtig", { exact: true }).dblclick(wort);
  await seite.getByRole("button", { name: "Marker" }).click();
  await seite.getByRole("group", { name: "Marker" }).getByRole("button", { name: "Gelb" }).click();
  await editor.getByText("Achtung", { exact: true }).dblclick(wort);
  await seite.getByRole("button", { name: "Schriftfarbe" }).click();
  await seite.getByRole("group", { name: "Schriftfarbe" }).getByRole("button", { name: "Rot" }).click();
  await expect(editor.locator('span[data-farbe="rot"]')).toHaveText("Achtung");
  await expect(editor.locator('mark[data-farbe="gelb"]')).toHaveText("wichtig");
  await expect(editor.locator("h3")).toHaveText("Ablauf");
  await expect(seite).toHaveURL(/\/notizen\/\d+\/$/);
  // Gespeichert wird laufend; im Textfeld der Seite steht das Markdown (HTML-maskiert)
  await expect.poll(async () => (await seite.request.get(seite.url())).text()).toMatch(/mark data-farbe=(&quot;|&#34;|")gelb/);

  await seite.reload();
  const neu = seite.locator("[data-editor='notiz-text'] [contenteditable='true']");
  await expect(neu.locator('span[data-farbe="rot"]')).toHaveText("Achtung");
  await expect(neu.locator('mark[data-farbe="gelb"]')).toHaveText("wichtig");
  await expect(neu.locator("h3")).toHaveText("Ablauf");
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
