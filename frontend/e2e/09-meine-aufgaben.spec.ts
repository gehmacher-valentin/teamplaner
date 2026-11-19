// Ablauf 9: Meine Aufgaben. Abgehakte Aufgaben bleiben 5 s sichtbar und lassen sich zurücknehmen, die
// Folgeaufgabe einer wiederkehrenden Aufgabe erscheint erst danach; dasselbe in der Projektliste.
// Betreute Platzhalter: Auswahl bei „Eingeteilt“, „Platzhaltern zugewiesen“ breit als dritte Spalte,
// schmaler im Wechsel per Umschalter. Mehrere Einteilungen eines Tages stehen nebeneinander.
import { expect, HANDY, ruhe, test } from "./hilfen";

const NACHLAUF = 5000;

test("Abhaken: bleibt 5 s sichtbar, Folgeaufgabe erst danach", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit");
  await seite.goto("/meine-aufgaben/");
  const zeilen = seite.locator("#karte-mir .zugewiesen__zeile", { hasText: "Wochencheck Hebebühne" });
  await expect(zeilen).toHaveCount(1);
  const zaehler = seite.locator("#karte-mir [data-zaehler]");
  const vorher = Number(await zaehler.textContent());

  await zeilen.getByRole("button", { name: /Als erledigt markieren/ }).click();
  const erledigt = zeilen.first();
  await expect(erledigt).toHaveClass(/zugewiesen__zeile--erledigt/);
  await expect(erledigt.getByRole("button", { name: /Als offen markieren/ })).toBeVisible();
  await expect(seite.getByText("Nächster Termin angelegt: Wochencheck Hebebühne")).toBeVisible();
  // Die Folgeaufgabe steht noch nicht in der Liste: ein schneller zweiter Klick träfe sonst sie
  await expect(zeilen).toHaveCount(1);
  await expect(zaehler).toHaveText(String(vorher - 1));

  await seite.waitForTimeout(NACHLAUF + 500);
  await expect(seite.locator("#karte-mir .zugewiesen__zeile--erledigt")).toHaveCount(0);
  await expect(zeilen, "Folgeaufgabe nach Ablauf").toHaveCount(1);
  await expect(zeilen.first().getByRole("button", { name: /Als erledigt markieren/ })).toBeVisible();
  await expect(zaehler).toHaveText(String(vorher));
});

test("Abhaken: innerhalb von 5 s rückgängig, Aufgabe bleibt offen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit");
  await seite.goto("/meine-aufgaben/");
  const zeile = seite.locator("#karte-mir .zugewiesen__zeile", { hasText: "Regal Lager" });
  await zeile.getByRole("button", { name: /Als erledigt markieren/ }).click();
  await expect(zeile).toHaveClass(/zugewiesen__zeile--erledigt/);
  await zeile.getByRole("button", { name: /Als offen markieren/ }).click();
  await expect(zeile).not.toHaveClass(/zugewiesen__zeile--erledigt/);
  await seite.waitForTimeout(NACHLAUF + 500);
  await expect(zeile).toBeVisible();
  await seite.reload();
  await expect(seite.locator("#karte-mir .zugewiesen__zeile", { hasText: "Regal Lager" })).toBeVisible();
});

test("Projektliste: abgehakte Aufgabe bleibt 5 s, dann ausgeblendet (Filter „Offen“)", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/projekte/");
  await seite.getByRole("link", { name: "Prototyp Förderband" }).first().click();
  await ruhe(seite);
  const zeile = seite.locator(".aufgabe-zeile", { hasText: "Steuerung verdrahten" });
  await expect(zeile).toBeVisible();
  await zeile.getByRole("button", { name: /Als erledigt markieren: Steuerung verdrahten/ }).click();
  await expect(zeile.getByRole("button", { name: /Als offen markieren/ })).toBeVisible();
  await seite.waitForTimeout(2000);
  await expect(zeile, "nach 2 s noch sichtbar").toBeVisible();
  await seite.waitForTimeout(NACHLAUF - 2000 + 500);
  await expect(zeile).toHaveCount(0);
});

test("Platzhalter: Auswahl bei „Eingeteilt“, Spalten und Umschalter je Breite", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer");
  await seite.goto("/meine-aufgaben/");
  const eingeteilt = seite.locator("#karte-eingeteilt");
  // Zwei Einteilungen am selben Tag nebeneinander (Demodaten: nächste Woche Mi/Do der Planerin)
  const kacheln = eingeteilt.locator(".tageskacheln").filter({ has: seite.locator(".tageskarte + .tageskarte") }).first();
  const [links, rechts] = await kacheln.locator(".tageskarte").evaluateAll((k) => k.map((e) => e.getBoundingClientRect().top));
  expect(Math.abs(links - rechts), "Kacheln in einer Zeile").toBeLessThan(2);

  // Breit: drei Spalten, kein Umschalter
  await expect(seite.getByRole("heading", { name: "Platzhaltern zugewiesen" })).toBeVisible();
  await expect(seite.locator("#karte-platzhalter")).toContainText("Bohrungen Rahmen");
  await expect(seite.locator("#karte-platzhalter")).toContainText("Prüfprotokolle ablegen");
  await expect(seite.locator(".meine-umschalter").first()).toBeHidden();

  // Filter auf einen Platzhalter
  await seite.locator("#platzhalter-filter").selectOption({ label: "Leihkraft Prüfung" });
  await expect(seite).toHaveURL(/platzhalter=\d+/);
  await expect(seite.locator("#karte-platzhalter")).not.toContainText("Bohrungen Rahmen");
  await expect(seite.locator("#karte-platzhalter")).toContainText("Prüfprotokolle ablegen");

  // Eingeteilt für einen Platzhalter, mit Abwesenheit
  await seite.locator("#eingeteilt-wahl").selectOption({ label: "Aushilfe Montage" });
  await expect(seite).toHaveURL(/eingeteilt=\d+/);
  await expect(seite.locator("#karte-eingeteilt")).toContainText("Abwesend");
  await expect(seite.locator("#karte-eingeteilt")).toContainText("Bohrungen Rahmen");
  await expect(seite.locator("#karte-eingeteilt")).toContainText("Lager aufräumen");
  await expect(seite).toHaveURL(/platzhalter=\d+/); // Filter bleibt erhalten

  // Mittel: zwei Spalten, Umschalter statt dritter Spalte. Der Filter hat „Platzhaltern zugewiesen“ gewählt
  await seite.setViewportSize({ width: 1280, height: 900 });
  await expect(seite).toHaveURL(/zugewiesen=platzhalter/);
  await expect(seite.locator("#karte-platzhalter .meine-umschalter")).toBeVisible();
  await expect(seite.locator("#karte-mir")).toBeHidden();
  await seite.locator("#karte-platzhalter .meine-umschalter").getByRole("link", { name: "Mir zugewiesen" }).click();
  await expect(seite).not.toHaveURL(/zugewiesen=platzhalter/);
  await expect(seite.locator("#karte-mir")).toBeVisible();
  await expect(seite.locator("#karte-platzhalter")).toBeHidden();
  await seite.locator("#karte-mir .meine-umschalter").getByRole("link", { name: "Platzhaltern zugewiesen" }).click();
  await expect(seite).toHaveURL(/zugewiesen=platzhalter/);
  await expect(seite.locator("#karte-platzhalter")).toBeVisible();
  await expect(seite.locator("#eingeteilt-wahl")).toHaveValue(/\d+/); // Auswahl bei „Eingeteilt“ bleibt
  await ruhe(seite);
});

test("Platzhalter am Handy: untereinander, ohne waagrechtes Scrollen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("planer", HANDY);
  await seite.goto("/meine-aufgaben/?zugewiesen=platzhalter");
  await expect(seite.locator("#eingeteilt-wahl")).toBeVisible();
  await expect(seite.locator("#karte-platzhalter .meine-umschalter")).toBeVisible();
  await expect(seite.locator("#karte-platzhalter")).toContainText("Bohrungen Rahmen");
  const breite = await seite.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(breite, "kein waagrechtes Scrollen").toBeLessThanOrEqual(0);
});
