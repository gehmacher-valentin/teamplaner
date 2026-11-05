// Mehrfachauswahl von Personen als Kästchenliste mit Suche (Projektmitglieder, Notiz-Ordner).
// Ausgewählte stehen beim Laden oben; die Suche blendet nicht passende Einträge aus.
import { t } from "./texte";

export function initPersonenauswahl(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>("[data-personenauswahl]").forEach((feld) => {
    if (feld.dataset.bereit) return;
    feld.dataset.bereit = "1";
    const liste = feld.querySelector<HTMLElement>(".personenauswahl__liste");
    const suche = feld.querySelector<HTMLInputElement>("[data-personenauswahl-suche]");
    const zahl = feld.querySelector<HTMLElement>("[data-personenauswahl-zahl]");
    const leer = feld.querySelector<HTMLElement>("[data-personenauswahl-leer]");
    if (!liste) return;
    const eintraege = Array.from(liste.querySelectorAll<HTMLLabelElement>(".personenauswahl__eintrag"));
    const kaestchen = (e: HTMLLabelElement) => e.querySelector<HTMLInputElement>("input[type=checkbox]")!;

    // Ausgewählte zuerst, sonst Reihenfolge des Servers (alphabetisch)
    eintraege
      .filter((e) => kaestchen(e).checked)
      .reverse()
      .forEach((e) => liste.prepend(e));

    const zaehlen = () => {
      const n = eintraege.filter((e) => kaestchen(e).checked).length;
      if (zahl) zahl.textContent = n ? t("ausgewaehlt", { n }) : "";
      eintraege.forEach((e) => e.classList.toggle("personenauswahl__eintrag--an", kaestchen(e).checked));
    };
    const filtern = () => {
      const begriff = (suche?.value ?? "").trim().toLowerCase();
      let sichtbar = 0;
      eintraege.forEach((e) => {
        const passt = !begriff || (e.textContent ?? "").toLowerCase().includes(begriff);
        e.hidden = !passt;
        if (passt) sichtbar += 1;
      });
      if (leer) leer.hidden = sichtbar > 0;
    };
    liste.addEventListener("change", zaehlen);
    suche?.addEventListener("input", filtern);
    // Enter in der Suche wählt den einzigen bzw. ersten Treffer, statt das Formular abzuschicken
    suche?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      const treffer = eintraege.find((e) => !e.hidden);
      if (treffer && suche.value.trim()) {
        kaestchen(treffer).checked = true;
        suche.value = "";
        filtern();
        zaehlen();
      }
    });
    zaehlen();
  });
}
