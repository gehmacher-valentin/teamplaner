/**
 * Unteraufgaben:
 * - Abhaken einer Hauptaufgabe mit offenen Unteraufgaben fragt nach, ob diese mit erledigt werden
 *   (Formulare mit data-unteraufgaben-offen="<Anzahl>"; Antwort im Feld name="unteraufgaben"),
 *   ebenso die Wahl eines erledigten Status (<select data-erledigt-status="<IDs>">).
 * - In der Projektliste blendet der Zähler „2 / 5“ die Unteraufgaben ein und aus.
 */
import htmx from "htmx.org";
import { t } from "./texte";

type Antwort = "alle" | "keine" | null;

function fragen(anzahl: number): Promise<Antwort> {
  return new Promise((aufloesen) => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("aria-labelledby", "unter-frage-titel");
    dialog.innerHTML = `<div class="dialog__inhalt">
      <h2 id="unter-frage-titel"></h2>
      <p class="ohne-rand"></p>
      <div class="formular__aktionen">
        <button type="button" class="knopf knopf--primaer" data-antwort="alle"></button>
        <button type="button" class="knopf" data-antwort="keine"></button>
        <button type="button" class="knopf knopf--text" data-antwort=""></button>
      </div></div>`;
    dialog.querySelector("h2")!.textContent = t("unter_frage_titel");
    dialog.querySelector("p")!.textContent = t(anzahl === 1 ? "unter_frage_eine" : "unter_frage_mehrere", { n: anzahl });
    dialog.querySelector('[data-antwort="alle"]')!.textContent = t("unter_alle");
    dialog.querySelector('[data-antwort="keine"]')!.textContent = t("unter_nur_haupt");
    dialog.querySelector('[data-antwort=""]')!.textContent = t("abbrechen");
    const fertig = (antwort: Antwort) => {
      dialog.close();
      dialog.remove();
      aufloesen(antwort);
    };
    dialog.addEventListener("click", (e) => {
      const knopf = (e.target as HTMLElement).closest<HTMLElement>("[data-antwort]");
      if (knopf) fertig((knopf.dataset.antwort || null) as Antwort);
    });
    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      fertig(null);
    });
    document.body.append(dialog);
    dialog.showModal();
    dialog.querySelector<HTMLButtonElement>('[data-antwort="alle"]')!.focus();
  });
}

export function initUnteraufgaben() {
  // In der Capture-Phase, damit HTMX das Absenden erst nach der Antwort sieht
  document.addEventListener(
    "submit",
    (event) => {
      const formular = event.target as HTMLFormElement;
      const anzahl = Number(formular.dataset?.unteraufgabenOffen || 0);
      const feld = formular.querySelector<HTMLInputElement>('input[name="unteraufgaben"]');
      const erledigen = formular.querySelector<HTMLInputElement>('input[name="erledigt"]')?.value === "1";
      if (!anzahl || !feld || !erledigen || formular.dataset.gefragt === "1") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      fragen(anzahl).then((antwort) => {
        if (!antwort) return;
        feld.value = antwort;
        formular.dataset.gefragt = "1";
        if (formular.hasAttribute("hx-post")) htmx.trigger(formular, "submit");
        else formular.requestSubmit();
        delete formular.dataset.gefragt;
      });
    },
    true,
  );

  // Status-Auswahl (Liste, Aufgabendetail): ein erledigter Status fragt genauso nach wie der Haken
  document.addEventListener(
    "change",
    (event) => {
      const wahl = event.target;
      if (!(wahl instanceof HTMLSelectElement) || !wahl.dataset.erledigtStatus) return;
      const formular = wahl.form;
      const anzahl = Number(formular?.dataset.unteraufgabenOffen || 0);
      const feld = formular?.querySelector<HTMLInputElement>('input[name="unteraufgaben"]');
      const erledigt = wahl.dataset.erledigtStatus.split(",").includes(wahl.value);
      if (!anzahl || !feld || !erledigt || wahl.dataset.gefragt === "1") return;
      event.stopImmediatePropagation();
      fragen(anzahl).then((antwort) => {
        if (!antwort) {
          wahl.value = Array.from(wahl.options).find((o) => o.defaultSelected)?.value ?? wahl.value;
          return;
        }
        feld.value = antwort;
        wahl.dataset.gefragt = "1";
        wahl.dispatchEvent(new Event("change", { bubbles: true }));
        delete wahl.dataset.gefragt;
      });
    },
    true,
  );

  document.addEventListener("click", (event) => {
    const knopf = (event.target as HTMLElement).closest<HTMLElement>("[data-unter-umschalten]");
    const block = knopf?.closest(".aufgabe-block");
    if (!knopf || !block) return;
    const zu = block.classList.toggle("aufgabe-block--zu");
    knopf.setAttribute("aria-expanded", String(!zu));
  });
}
