/**
 * Freigaben-Bauteil der Ansichten: Suche nach Namen, Filter nach Bereich, „Nur Freigegebene“ und
 * die Sammelaktion für die gerade sichtbaren Personen. Gespeichert wird mit dem Formular der Ansicht.
 */
export function initFreigaben(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLElement>("[data-freigaben]").forEach((bauteil) => {
    if (bauteil.dataset.freigabenAktiv) return;
    bauteil.dataset.freigabenAktiv = "1";
    const suche = bauteil.querySelector<HTMLInputElement>("[data-freigaben-suche]");
    const bereich = bauteil.querySelector<HTMLSelectElement>("[data-freigaben-bereich]");
    const nur = bauteil.querySelector<HTMLInputElement>("[data-freigaben-nur]");
    const leer = bauteil.querySelector<HTMLElement>("[data-freigaben-leer]");
    const zeilen = Array.from(bauteil.querySelectorAll<HTMLElement>(".freigabe-zeile"));
    const recht = (z: HTMLElement) =>
      z.hasAttribute("data-immer") ? "bearbeiten" : z.querySelector<HTMLInputElement>('input[type="radio"]:checked')?.value ?? "";

    const aktualisieren = () => {
      const text = (suche?.value ?? "").trim().toLowerCase();
      let sichtbar = 0;
      for (const z of zeilen) {
        const zeigen = (!text || (z.dataset.name ?? "").includes(text))
          && (!bereich?.value || z.dataset.bereich === bereich.value)
          && (!nur?.checked || recht(z) !== "");
        z.hidden = !zeigen;
        if (zeigen) sichtbar++;
      }
      if (leer) leer.hidden = sichtbar > 0;
      const ohneImmer = zeilen.filter((z) => !z.hasAttribute("data-immer")).map(recht);
      const zahl = (wert: string) => String(ohneImmer.filter((r) => r === wert).length);
      const sehen = bauteil.querySelector("[data-zahl-sehen]");
      const bearbeiten = bauteil.querySelector("[data-zahl-bearbeiten]");
      if (sehen) sehen.textContent = zahl("sehen");
      if (bearbeiten) bearbeiten.textContent = zahl("bearbeiten");
    };

    suche?.addEventListener("input", aktualisieren);
    bereich?.addEventListener("change", aktualisieren);
    nur?.addEventListener("change", aktualisieren);
    bauteil.addEventListener("change", (event) => {
      if ((event.target as HTMLElement).matches('input[type="radio"]')) aktualisieren();
    });
    bauteil.querySelectorAll<HTMLButtonElement>("[data-freigaben-alle]").forEach((knopf) => {
      knopf.addEventListener("click", () => {
        for (const z of zeilen) {
          if (z.hidden) continue;
          const wahl = z.querySelector<HTMLInputElement>(`input[type="radio"][value="${knopf.dataset.freigabenAlle}"]`);
          if (wahl && !wahl.disabled) wahl.checked = true;
        }
        aktualisieren();
      });
    });
    aktualisieren();
  });
}
