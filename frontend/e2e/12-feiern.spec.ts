// Ablauf 12: Feieranimation. In den Einstellungen lassen sich alle Figuren der Reihe nach ansehen;
// das Einhorn lädt lottie-web erst dabei nach (Content-Security-Policy: nur Skripte vom eigenen Server).
// Mit eingeschalteter Animation feiert jedes Abhaken; bei „Bewegung reduzieren“ wird die Figur in der Mitte
// nur ein- und ausgeblendet.
import { expect, test } from "./hilfen";

const FIGUREN = ["einhorn", "rakete", "ufo", "kaenguru", "trex", "flamingo", "otter", "lama", "geist", "partygesicht", "pinata"];

test("Feieranimation: alle Figuren ansehen, Einhorn galoppiert per Lottie", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit", { reducedMotion: "no-preference" });
  await seite.goto("/einstellungen/darstellung/");
  const knopf = seite.getByRole("button", { name: "Nächste Figur" });

  await knopf.click();
  const einhorn = seite.locator('.feier[data-figur="einhorn"]');
  await expect(einhorn.locator(".feier__einhorn svg"), "Lottie zeichnet das Einhorn").toBeAttached();
  await expect(einhorn.locator(".feier__spur-band").first()).toHaveAttribute("d", /^M/);
  await expect(einhorn.locator(".feier__funke").first(), "Sparkles entlang der Spur").toBeAttached();
  await expect(einhorn, "Einhorn verschwindet wieder").toHaveCount(0, { timeout: 8000 });

  for (const name of FIGUREN.slice(1)) {
    await knopf.click();
    await expect(seite.locator(`.feier[data-figur="${name}"]`), name).toBeAttached();
  }
  await expect(seite.locator(".feier"), "alle Figuren wieder weg").toHaveCount(0, { timeout: 8000 });
});

test("Feieranimation: Abhaken feiert, bei „Bewegung reduzieren“ ohne Bewegung in der Mitte", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit");
  await seite.goto("/einstellungen/darstellung/");
  const schalter = seite.getByRole("switch", { name: "Feieranimation beim Abhaken" });
  await expect(schalter).not.toBeChecked();
  const gespeichert = seite.waitForResponse((a) => a.url().endsWith("/einstellungen/darstellung/speichern/"));
  await schalter.check();
  await gespeichert;

  await seite.goto("/meine-aufgaben/");
  const zeile = seite.locator("#karte-mir .zugewiesen__zeile", { hasText: "Regal Lager" });
  await zeile.getByRole("button", { name: /Als erledigt markieren/ }).click();
  const ruhig = seite.locator(".feier--ruhig");
  await expect(ruhig).toBeAttached();
  await expect(ruhig.locator(".feier__konfetti"), "kein Konfetti").toHaveCount(0);
  // Mitte des Fensters, kein Flug: die Figur steht auf der waagrechten Mitte
  const box = await ruhig.locator(".feier__bild").boundingBox();
  const breite = seite.viewportSize()!.width;
  expect(Math.abs(box!.x + box!.width / 2 - breite / 2)).toBeLessThan(2);
  await expect(seite.locator(".feier--ruhig")).toHaveCount(0, { timeout: 5000 });

  // Aufräumen: Aufgabe wieder offen, Animation wieder aus
  await zeile.getByRole("button", { name: /Als offen markieren/ }).click();
  await expect(zeile).not.toHaveClass(/zugewiesen__zeile--erledigt/);
  await seite.goto("/einstellungen/darstellung/");
  const aus = seite.waitForResponse((a) => a.url().endsWith("/einstellungen/darstellung/speichern/"));
  await seite.getByRole("switch", { name: "Feieranimation beim Abhaken" }).uncheck();
  await aus;
});
