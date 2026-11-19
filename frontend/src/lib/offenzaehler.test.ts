// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { zaehlerAktualisieren } from "./offenzaehler";

describe("Zähler nach dem Abhaken", () => {
  it("zählt nur offene Zeilen, entfernt leere Gruppen und zeigt die Leer-Meldung", () => {
    document.body.innerHTML = `
      <section id="karte" data-zaehlen>
        <span data-zaehler>3</span>
        <div data-gruppe id="g1"><span data-gruppe-zahl>2</span><div data-zeile data-erledigt></div><div data-zeile></div></div>
        <div data-gruppe id="g2"><span data-gruppe-zahl>1</span></div>
        <div data-leer hidden></div>
      </section>`;
    const karte = document.getElementById("karte")!;
    zaehlerAktualisieren(karte);
    expect(karte.querySelector("[data-zaehler]")!.textContent).toBe("1");
    expect(karte.querySelector("#g1 [data-gruppe-zahl]")!.textContent).toBe("1");
    expect(karte.querySelector("#g2")).toBeNull();
    expect(karte.querySelector<HTMLElement>("[data-leer]")!.hidden).toBe(true);
    karte.querySelectorAll("[data-zeile]").forEach((z) => z.remove());
    zaehlerAktualisieren(karte);
    expect(karte.querySelector("[data-zaehler]")!.textContent).toBe("0");
    expect(karte.querySelector<HTMLElement>("[data-leer]")!.hidden).toBe(false);
  });

  it("lässt Karten ohne data-zaehlen in Ruhe", () => {
    document.body.innerHTML = `<section id="k"><span data-zaehler>7</span></section>`;
    zaehlerAktualisieren(document.getElementById("k"));
    expect(document.querySelector("[data-zaehler]")!.textContent).toBe("7");
  });
});
