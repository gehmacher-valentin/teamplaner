/**
 * Felder, die beim Verlassen speichern (data-inline): Enter speichert, Esc stellt den gespeicherten
 * Wert wieder her – wie die Info-Zeile im Teamplaner. In mehrzeiligen Feldern macht Umschalt+Enter
 * einen Zeilenumbruch. Gespeichert wird über das change-Ereignis (hx-trigger="change"); mit
 * data-enter-absenden schickt Enter stattdessen das Formular ab (neue Zeile in den Bestellungen).
 * Textfelder mit data-mitwachsen werden so hoch wie ihr Inhalt (wo CSS field-sizing fehlt).
 */
const MITWACHSEN_PER_CSS = typeof CSS !== "undefined" && CSS.supports?.("field-sizing", "content");

function anpassen(feld: HTMLTextAreaElement) {
  feld.style.height = "auto";
  feld.style.height = `${feld.scrollHeight + feld.offsetHeight - feld.clientHeight}px`;
}

export function mitwachsen(wurzel: ParentNode) {
  if (MITWACHSEN_PER_CSS) return;
  wurzel.querySelectorAll<HTMLTextAreaElement>("textarea[data-mitwachsen]").forEach(anpassen);
}

export function initInline() {
  if (!MITWACHSEN_PER_CSS) {
    document.addEventListener("input", (event) => {
      if (event.target instanceof HTMLTextAreaElement && event.target.matches("[data-mitwachsen]")) anpassen(event.target);
    });
  }
  document.addEventListener("keydown", (event) => {
    const feld = event.target;
    if (!(feld instanceof HTMLInputElement || feld instanceof HTMLTextAreaElement) || !feld.matches("[data-inline]")) return;
    if (event.key === "Enter" && !(feld instanceof HTMLTextAreaElement && event.shiftKey)) {
      event.preventDefault(); // kein Absenden des Formulars, gespeichert wird beim Verlassen
      if (feld.matches("[data-enter-absenden]")) feld.form?.requestSubmit();
      else feld.blur();
    } else if (event.key === "Escape") {
      event.preventDefault();
      feld.value = feld.defaultValue;
      feld.dispatchEvent(new Event("input", { bubbles: true }));
      feld.blur();
    }
  });
}
