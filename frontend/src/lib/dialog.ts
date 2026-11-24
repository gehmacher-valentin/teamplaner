/**
 * Eigene Dialoge statt window.confirm und window.prompt: im Stil der Seite, Deutsch/Englisch,
 * Esc und „Abbrechen“ brechen ab, danach steht der Fokus wieder dort, wo er vorher war.
 *
 * - bestaetigen(): Rückfrage mit „Abbrechen“ und rotem Aktionsknopf
 * - eingeben(): Frage mit einem Textfeld (z. B. Adresse eines Links im Editor)
 * - initBestaetigen(): Formulare mit data-bestaetigen="Frage" fragen vor dem Absenden nach.
 *   Der Knopf heißt wie der Absende-Knopf des Formulars; ohne lesbaren Text (Symbol, ×) „Löschen“,
 *   oder data-bestaetigen-knopf="…" legt ihn fest.
 */
import { t } from "./texte";

let laufend = 0;

function oeffnen<T>(aufbauen: (dialog: HTMLDialogElement, fertig: (wert: T) => void) => void, abbruch: T): Promise<T> {
  return new Promise((aufloesen) => {
    const vorher = document.activeElement as HTMLElement | null;
    const dialog = document.createElement("dialog");
    dialog.className = "rueckfrage";
    const id = `rueckfrage-${++laufend}`;
    dialog.setAttribute("aria-labelledby", `${id}-titel`);
    let erledigt = false;
    const fertig = (wert: T) => {
      if (erledigt) return;
      erledigt = true;
      dialog.close();
      dialog.remove();
      if (vorher?.isConnected) vorher.focus({ preventScroll: true });
      aufloesen(wert);
    };
    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      fertig(abbruch);
    });
    // Klick auf den abgedunkelten Hintergrund bricht ab
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) fertig(abbruch);
    });
    aufbauen(dialog, fertig);
    dialog.querySelector("h2")!.id = `${id}-titel`;
    document.body.append(dialog);
    dialog.showModal();
  });
}

function geruest(frage: string, knopf: string, gefahr: boolean): HTMLFormElement {
  const formular = document.createElement("form");
  formular.method = "dialog";
  formular.className = "dialog__inhalt";
  formular.innerHTML = `<h2></h2>
    <div class="formular__aktionen formular__aktionen--rechts">
      <button type="button" class="knopf" data-abbrechen></button>
      <button type="submit" class="knopf ${gefahr ? "knopf--gefahr-voll" : "knopf--primaer"}"></button>
    </div>`;
  formular.querySelector("h2")!.textContent = frage;
  formular.querySelector("[data-abbrechen]")!.textContent = t("abbrechen");
  formular.querySelector('[type="submit"]')!.textContent = knopf;
  return formular;
}

/** Rückfrage vor einer Aktion; true, wenn bestätigt. */
export function bestaetigen(frage: string, knopf = t("loeschen")): Promise<boolean> {
  return oeffnen<boolean>((dialog, fertig) => {
    const formular = geruest(frage, knopf, true);
    formular.addEventListener("submit", (e) => {
      e.preventDefault();
      fertig(true);
    });
    formular.querySelector("[data-abbrechen]")!.addEventListener("click", () => fertig(false));
    dialog.append(formular);
    // Fokus auf „Abbrechen“: Enter löst nicht versehentlich das Löschen aus
    queueMicrotask(() => formular.querySelector<HTMLButtonElement>("[data-abbrechen]")!.focus());
  }, false);
}

/** Frage mit Textfeld; der eingegebene Text oder null bei Abbruch. */
export function eingeben(frage: string, wert = "", knopf = t("uebernehmen")): Promise<string | null> {
  return oeffnen<string | null>((dialog, fertig) => {
    const formular = geruest(frage, knopf, false);
    const feld = document.createElement("input");
    feld.type = "text";
    feld.value = wert;
    feld.setAttribute("aria-label", frage);
    feld.autocomplete = "off";
    formular.querySelector("h2")!.after(feld);
    formular.addEventListener("submit", (e) => {
      e.preventDefault();
      fertig(feld.value.trim());
    });
    formular.querySelector("[data-abbrechen]")!.addEventListener("click", () => fertig(null));
    dialog.append(formular);
    queueMicrotask(() => {
      feld.focus();
      feld.select();
    });
  }, null);
}

/** Beschriftung des Aktionsknopfs für ein Formular mit data-bestaetigen. */
export function knopfText(formular: HTMLFormElement, absender?: HTMLElement | null): string {
  if (formular.dataset.bestaetigenKnopf) return formular.dataset.bestaetigenKnopf;
  const knopf = absender ?? formular.querySelector<HTMLElement>('[type="submit"]');
  const text = knopf?.textContent?.replace(/\s+/g, " ").trim() ?? "";
  if (!/\p{L}{2,}/u.test(text)) return t("loeschen");
  return text.charAt(0).toLocaleUpperCase() + text.slice(1);
}

/** Frage vor dem Absenden: am Formular oder an der gerade gewählten Option einer Auswahlliste. */
export function frageVon(formular: HTMLFormElement): string | undefined {
  return formular.dataset?.bestaetigen
    || formular.querySelector<HTMLOptionElement>("select option:checked[data-bestaetigen]")?.dataset.bestaetigen;
}

export function initBestaetigen() {
  // In der Capture-Phase, damit HTMX das Absenden erst nach der Antwort sieht
  document.addEventListener(
    "submit",
    (event) => {
      const formular = event.target as HTMLFormElement;
      const frage = frageVon(formular);
      if (!frage || formular.dataset.bestaetigt === "1") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const absender = (event as SubmitEvent).submitter as HTMLButtonElement | null;
      bestaetigen(frage, knopfText(formular, absender)).then((ja) => {
        if (!ja || !formular.isConnected) return;
        formular.dataset.bestaetigt = "1";
        // HTMX über window (main.ts), damit dieses Modul ohne HTMX testbar bleibt
        if (formular.hasAttribute("hx-post") && window.htmx) window.htmx.trigger(formular, "submit");
        else formular.requestSubmit(absender && formular.contains(absender) ? absender : undefined);
        delete formular.dataset.bestaetigt;
      });
    },
    true,
  );
}
