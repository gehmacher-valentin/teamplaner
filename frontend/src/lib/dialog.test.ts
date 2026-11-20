// @vitest-environment jsdom
import { beforeAll, describe, expect, it } from "vitest";
import { bestaetigen, eingeben, knopfText } from "./dialog";

beforeAll(() => {
  // jsdom kennt showModal/close noch nicht
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});

function dialog() {
  return document.querySelector<HTMLDialogElement>("dialog.rueckfrage")!;
}

describe("Rückfrage statt window.confirm", () => {
  it("zeigt Frage und Knopf, bestätigt und räumt auf", async () => {
    const antwort = bestaetigen("„plan.pdf“ endgültig löschen?", "Löschen");
    expect(dialog().querySelector("h2")!.textContent).toBe("„plan.pdf“ endgültig löschen?");
    const knopf = dialog().querySelector<HTMLButtonElement>('[type="submit"]')!;
    expect(knopf.textContent).toBe("Löschen");
    expect(knopf.classList.contains("knopf--gefahr-voll")).toBe(true);
    knopf.click();
    expect(await antwort).toBe(true);
    expect(dialog()).toBeNull();
  });

  it("Abbrechen und Esc ergeben false, Fokus kehrt zurück", async () => {
    document.body.innerHTML = '<button id="vorher">x</button>';
    const vorher = document.getElementById("vorher")!;
    vorher.focus();
    const a = bestaetigen("Notiz löschen?");
    dialog().querySelector<HTMLButtonElement>("[data-abbrechen]")!.click();
    expect(await a).toBe(false);
    expect(document.activeElement).toBe(vorher);

    const b = bestaetigen("Notiz löschen?");
    dialog().dispatchEvent(new Event("cancel", { cancelable: true }));
    expect(await b).toBe(false);
  });
});

describe("Eingabe statt window.prompt", () => {
  it("gibt den Text zurück, null bei Abbruch", async () => {
    const a = eingeben("Adresse des Links", "https://");
    const feld = dialog().querySelector("input")!;
    expect(feld.value).toBe("https://");
    feld.value = "  https://boku.ac.at ";
    dialog().querySelector("form")!.requestSubmit();
    expect(await a).toBe("https://boku.ac.at");

    const b = eingeben("Adresse des Links");
    dialog().querySelector<HTMLButtonElement>("[data-abbrechen]")!.click();
    expect(await b).toBeNull();
  });
});

describe("Beschriftung des Aktionsknopfs", () => {
  function formular(html: string) {
    document.body.innerHTML = html;
    return document.querySelector("form")!;
  }

  it("nimmt den Text des Absende-Knopfs, groß geschrieben", () => {
    expect(knopfText(formular('<form><button type="submit">löschen</button></form>'))).toBe("Löschen");
    expect(knopfText(formular('<form><button type="submit">Ordner löschen</button></form>'))).toBe("Ordner löschen");
  });

  it("ohne lesbaren Text „Löschen“, data-bestaetigen-knopf hat Vorrang", () => {
    expect(knopfText(formular('<form><button type="submit">×</button></form>'))).toBe("Löschen");
    expect(knopfText(formular('<form><button type="submit"><svg></svg></button></form>'))).toBe("Löschen");
    expect(knopfText(formular('<form data-bestaetigen-knopf="Entfernen"><button type="submit">×</button></form>'))).toBe("Entfernen");
  });
});
