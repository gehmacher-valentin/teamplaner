// Ablauf 8: Farbschema umstellen. Die Auswahl speichert sofort und lädt die Seite neu (HX-Refresh);
// danach müssen Auswahlfeld und data-theme am <html> schon beim ersten Umstellen den neuen Wert zeigen.
import { expect, test } from "./hilfen";

test("Farbschema: Anzeige stimmt nach jedem Umstellen", async ({ seiteFuer }) => {
  const seite = await seiteFuer("mitarbeit");
  await seite.goto("/einstellungen/darstellung/");
  const auswahl = seite.getByRole("combobox", { name: "Farbschema" });
  await expect(auswahl).toHaveValue("system");

  for (const wert of ["dark", "light", "system", "dark", "system"]) {
    const neuGeladen = seite.waitForEvent("load");
    await auswahl.selectOption(wert);
    await neuGeladen;
    await expect(seite.locator("html"), `data-theme nach Umstellen auf ${wert}`).toHaveAttribute("data-theme", wert);
    await expect(auswahl, `Auswahl nach Umstellen auf ${wert}`).toHaveValue(wert);
  }
});
