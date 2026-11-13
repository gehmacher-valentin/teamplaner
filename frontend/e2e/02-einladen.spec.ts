// Ablauf 2: Konto einladen. Einladen in der eigenen Rolle ist erlaubt, das Bearbeiten des neuen
// Kontos danach nicht. Trotzdem muss der Link zum Festlegen des Passworts erscheinen.
import { expect, test, type Rolle } from "./hilfen";

const faelle: [string, Rolle, string, boolean][] = [
  ["Admin lädt Admin ein", "admin", "Admin", false],
  ["Admin lädt Bereichsleitung ein", "admin", "Bereichsleitung", true],
  ["Bereichsleitung lädt Bereichsleitung ein", "leitung", "Bereichsleitung", false],
  ["Bereichsleitung lädt Mitarbeiter:in ein", "leitung", "Mitarbeiter:in", true],
];

for (const [name, rolle, neueRolle, bearbeitbar] of faelle) {
  test(`Einladen: ${name}`, async ({ seiteFuer }, info) => {
    const seite = await seiteFuer(rolle);
    const person = `Person E${info.workerIndex}${faelle.findIndex((f) => f[0] === name)}`;
    await seite.goto("/einstellungen/personen/");
    await seite.getByRole("link", { name: "Person einladen" }).click();
    await seite.locator("#id_anzeigename").fill(person);
    await seite.locator("#id_email").fill(`${person.toLowerCase().replace(/\s/g, ".")}@example.test`);
    await seite.locator("#id_rolle").selectOption({ label: neueRolle });
    await seite.locator("#id_bereich").selectOption({ label: "Produktion" });
    await seite.getByRole("button", { name: "Konto anlegen und Link erzeugen" }).click();

    await expect(seite.getByRole("heading", { level: 1 })).toContainText(person);
    await expect(seite.locator(".toast").filter({ hasText: `Konto für ${person} angelegt.` })).toBeVisible();
    const link = seite.locator(".passwort-link code");
    await expect(link).toContainText("/passwort/setzen/");
    await expect(seite.locator(".passwort-link__qr svg")).toBeVisible();
    // Stammdaten bearbeiten nur bei niedrigerer Rolle
    await expect(seite.getByRole("heading", { name: "Stammdaten" })).toHaveCount(bearbeitbar ? 1 : 0);

    // Der Link funktioniert, und er wird nur einmal gezeigt
    const adresse = (await link.innerText()).trim();
    await seite.reload();
    await expect(seite.locator(".passwort-link")).toHaveCount(0);
    const gast = await seite.context().browser()!.newContext();
    const gastSeite = await gast.newPage();
    await gastSeite.goto(adresse);
    await expect(gastSeite.locator('input[type="password"]').first()).toBeVisible();
    await gast.close();
  });
}

test("Personen: Suche filtert beim Tippen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("admin");
  await seite.goto("/einstellungen/personen/");
  const liste = seite.locator("#personen-liste");
  await expect(liste).toContainText("Person 01");
  await seite.getByLabel("Personen suchen").pressSequentially("Person 05");
  await expect(liste).not.toContainText("Person 01");
  await expect(liste).toContainText("Person 05");
  await expect(seite).toHaveURL(/q=Person(\+|%20)05/);
});
