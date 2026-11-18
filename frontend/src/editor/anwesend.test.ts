// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { ANWESEND_HOECHSTENS, anwesendeElemente } from "./gemeinsam";

describe("Anwesende als Avatare", () => {
  it("Initialen oder Foto, Name für Screenreader und Tooltip", () => {
    const [foto, initialen] = anwesendeElemente([
      { person: 9, name: "Person 09", initialen: "P9", foto: null },
      { person: 3, name: "Aushilfe Montage", initialen: "AM", foto: "/foto/3/?v=1" },
    ]);
    expect(foto.getAttribute("aria-label")).toBe("Aushilfe Montage");
    expect(foto.dataset.name).toBe("Aushilfe Montage");
    expect(foto.querySelector("img")?.getAttribute("src")).toBe("/foto/3/?v=1");
    expect(initialen.getAttribute("role")).toBe("img");
    expect(initialen.tabIndex).toBe(0);
    const av = initialen.querySelector(".avatar") as HTMLElement;
    expect(av.textContent).toBe("P9");
    expect(av.classList.contains("av-1")).toBe(true);
    expect(av.getAttribute("aria-hidden")).toBe("true");
  });

  it(`ab mehr als ${ANWESEND_HOECHSTENS} Personen fasst „+N“ den Rest zusammen`, () => {
    const personen = Array.from({ length: 8 }, (_x, i) => ({ person: i, name: `Person 0${i}`, initialen: `P${i}` }));
    const elemente = anwesendeElemente(personen);
    expect(elemente).toHaveLength(ANWESEND_HOECHSTENS);
    const mehr = elemente[elemente.length - 1];
    expect(mehr.textContent).toBe("+4");
    expect(mehr.getAttribute("aria-label")).toBe("Person 04, Person 05, Person 06, Person 07");
    expect(anwesendeElemente(personen.slice(0, ANWESEND_HOECHSTENS))).toHaveLength(ANWESEND_HOECHSTENS);
  });
});
