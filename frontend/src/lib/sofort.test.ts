// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { serverstandHerstellen } from "./sofort";

describe("Sofort speichernde Felder nach dem Neuladen", () => {
  it("zeigen den Stand vom Server, nicht den vom Browser wiederhergestellten (Firefox)", () => {
    document.body.innerHTML = `
      <select id="farbschema" hx-swap="none" autocomplete="off">
        <option value="system">Wie am Gerät</option><option value="dark" selected>Dunkel</option>
      </select>
      <input id="feier" type="checkbox" hx-swap="none" checked>
      <select id="normal"><option value="a">A</option><option value="b" selected>B</option></select>`;
    const farbschema = document.getElementById("farbschema") as HTMLSelectElement;
    const feier = document.getElementById("feier") as HTMLInputElement;
    const normal = document.getElementById("normal") as HTMLSelectElement;
    // So sieht es aus, wenn der Browser die zuletzt gewählten Werte zurückschreibt
    farbschema.value = "system";
    feier.checked = false;
    normal.value = "a";
    serverstandHerstellen();
    expect(farbschema.value).toBe("dark");
    expect(feier.checked).toBe(true);
    expect(normal.value).toBe("a"); // nur sofort speichernde Felder (hx-swap="none")
  });
});
