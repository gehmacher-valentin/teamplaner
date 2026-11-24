/**
 * Hochladen von Anhängen über eine Kachel (templates/teile/anhang_feld.html, Aufgaben und Notizen):
 * Datei hineinziehen oder auswählen, danach ausdrücklich „Hochladen“. Solange etwas ausgewählt ist,
 * fragt die Seite vor dem Verlassen nach.
 *
 * Das echte Dateifeld bleibt für Tastatur und Screenreader in der Kachel. Die Auswahl merkt sich das
 * Modul je Adresse: In der Seitenleiste ersetzt HTMX das Formular bei jeder Aktion, das neue bekommt
 * dann dieselbe Datei. Vorschau als data:-Adresse, blob: lässt die Content-Security-Policy nicht zu.
 */
import { bestaetigen } from "./dialog";
import { t } from "./texte";
import { toast } from "./toast";

const FELD = "form[data-anhang-feld]";
const MIT_VORSCHAU = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]); // wie Anhang.hat_vorschau
const DATEISYMBOL =
  '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>';

/** Ausgewählt und noch nicht hochgeladen, je Adresse des Formulars. */
const auswahl = new Map<string, File>();

/** „Zeichnung.PDF“ → „PDF“ wie der Filter dateiendung. */
export function endung(name: string): string {
  const punkt = name.lastIndexOf(".");
  return punkt < 0 ? "" : name.slice(punkt + 1).toUpperCase().slice(0, 5);
}

/** Wie der Filter dateigroesse. */
export function groesse(bytes: number): string {
  let wert = bytes;
  for (const einheit of ["B", "KB", "MB"]) {
    if (wert < 1024) return einheit === "B" ? `${wert} B` : `${wert.toFixed(1).replace(".", ",")} ${einheit}`;
    wert /= 1024;
  }
  return `${wert.toFixed(1).replace(".", ",")} GB`;
}

export function zuGross(datei: Pick<File, "size">, maxMb: number): boolean {
  return maxMb > 0 && datei.size > maxMb * 1024 * 1024;
}

const eingabe = (feld: HTMLFormElement) => feld.querySelector<HTMLInputElement>('input[type="file"]')!;
const schluessel = (feld: HTMLFormElement) => feld.getAttribute("action")!;
const teil = (feld: HTMLFormElement, name: string) => feld.querySelector<HTMLElement>(`.anhang-feld__${name}`)!;

/** Dateifeld auf die gemerkte Auswahl setzen, auch nach „Abbrechen“ im Auswahlfenster. */
function eingabeSetzen(feld: HTMLFormElement, datei: File | undefined) {
  if (!datei) {
    eingabe(feld).value = "";
    return;
  }
  const ablage = new DataTransfer();
  ablage.items.add(datei);
  eingabe(feld).files = ablage.files;
}

function vorschauZeigen(feld: HTMLFormElement, datei: File) {
  const vorschau = teil(feld, "vorschau");
  const symbol = () => {
    vorschau.innerHTML = `${DATEISYMBOL}<span class="anhang-kachel__endung"></span>`;
    vorschau.querySelector("span")!.textContent = endung(datei.name);
  };
  symbol();
  if (!MIT_VORSCHAU.has(datei.type)) return;
  const leser = new FileReader();
  leser.onload = () => {
    if (auswahl.get(schluessel(feld)) !== datei) return; // inzwischen eine andere
    const bild = document.createElement("img");
    bild.alt = "";
    bild.onerror = symbol;
    bild.src = String(leser.result);
    vorschau.replaceChildren(bild);
  };
  leser.readAsDataURL(datei);
}

function anzeigen(feld: HTMLFormElement) {
  const datei = auswahl.get(schluessel(feld));
  feld.classList.toggle("anhang-feld--gewaehlt", Boolean(datei));
  sperren(feld, false);
  teil(feld, "status").textContent = datei ? t("anhang_status", { name: datei.name }) : "";
  teil(feld, "vorschau").replaceChildren();
  if (!datei) return;
  teil(feld, "marke").textContent = t("anhang_offen");
  teil(feld, "entfernen").textContent = t("anhang_entfernen");
  teil(feld, "name").textContent = datei.name;
  teil(feld, "name").title = datei.name;
  teil(feld, "groesse").textContent = groesse(datei.size);
  vorschauZeigen(feld, datei);
}

/** Während des Hochladens ist der Knopf gesperrt; das Dateifeld selbst nicht, sonst ginge es nicht mit. */
function sperren(feld: HTMLFormElement, an: boolean) {
  const knopf = feld.querySelector<HTMLButtonElement>('[type="submit"]')!;
  knopf.dataset.text ??= knopf.textContent!;
  knopf.disabled = an;
  knopf.textContent = an ? t("anhang_laedt") : knopf.dataset.text;
  feld.querySelector<HTMLButtonElement>(".anhang-feld__entfernen")!.disabled = an;
  feld.classList.toggle("anhang-feld--laedt", an);
}

function waehlen(feld: HTMLFormElement, datei: File) {
  const maxMb = Number(feld.dataset.maxMb) || 0;
  if (zuGross(datei, maxMb)) {
    toast(t("anhang_zu_gross", { name: datei.name, mb: maxMb }), { art: "fehler" });
    eingabeSetzen(feld, auswahl.get(schluessel(feld)));
    return;
  }
  auswahl.set(schluessel(feld), datei);
  eingabeSetzen(feld, datei);
  anzeigen(feld);
}

function verwerfen(feld: HTMLFormElement) {
  auswahl.delete(schluessel(feld));
  eingabeSetzen(feld, undefined);
  anzeigen(feld);
}

function offene(wurzel: ParentNode | null): HTMLFormElement[] {
  return Array.from(wurzel?.querySelectorAll<HTMLFormElement>(FELD) ?? []).filter((f) => auswahl.has(schluessel(f)));
}

/**
 * Vor dem Schließen oder Wechseln eines Bereichs: Ist dort eine Datei ausgewählt, fragt die Seite nach.
 * Ohne Auswahl läuft ``weiter`` sofort, damit sich am bisherigen Ablauf nichts ändert.
 */
export function auswahlVerlassen(wurzel: ParentNode | null, weiter: () => void, bleiben?: () => void) {
  const felder = offene(wurzel);
  if (!felder.length) return weiter();
  bestaetigen(t("anhang_verwerfen_frage"), t("anhang_verwerfen")).then((ja) => {
    if (!ja) return bleiben?.();
    felder.filter((f) => f.isConnected).forEach(verwerfen);
    weiter();
  });
}

/** Auswahl ohne Rückfrage vergessen, z. B. wenn die Aufgabe gelöscht wurde. */
export function auswahlVergessen(wurzel: ParentNode | null) {
  offene(wurzel).forEach(verwerfen);
}

/** Frisch eingesetzte Felder bekommen die gemerkte Auswahl zurück. */
export function anhangfelderAbgleichen(wurzel: ParentNode) {
  const felder = Array.from(wurzel.querySelectorAll<HTMLFormElement>(FELD));
  if (wurzel instanceof HTMLFormElement && wurzel.matches(FELD)) felder.push(wurzel);
  for (const feld of felder) {
    const datei = auswahl.get(schluessel(feld));
    if (!datei) continue;
    eingabeSetzen(feld, datei);
    anzeigen(feld);
  }
}

const mitDateien = (e: DragEvent) => e.dataTransfer?.types.includes("Files") ?? false;
const feldAn = (e: Event) => (e.target as Element | null)?.closest?.<HTMLFormElement>(FELD) ?? null;

function ziehenMarkieren(ziel: HTMLFormElement | null) {
  document.querySelectorAll(".anhang-feld--ziel").forEach((f) => f !== ziel && f.classList.remove("anhang-feld--ziel"));
  ziel?.classList.add("anhang-feld--ziel");
}

export function initAnhangfelder() {
  let unterwegs = false; // Formular wird gerade normal abgeschickt: nicht nachfragen

  document.addEventListener("change", (event) => {
    const feld = feldAn(event);
    if (!feld || event.target !== eingabe(feld)) return;
    const datei = eingabe(feld).files?.[0];
    if (datei) waehlen(feld, datei);
    else eingabeSetzen(feld, auswahl.get(schluessel(feld))); // Auswahlfenster abgebrochen
  });

  document.addEventListener("click", (event) => {
    const feld = feldAn(event);
    if (!feld || !(event.target as Element).closest(".anhang-feld__entfernen")) return;
    verwerfen(feld);
    eingabe(feld).focus({ preventScroll: true });
  });

  document.addEventListener("submit", (event) => {
    const feld = feldAn(event);
    if (!feld || event.defaultPrevented && !feld.hasAttribute("hx-post")) return;
    if (!feld.hasAttribute("hx-post")) unterwegs = true;
    window.setTimeout(() => sperren(feld, true)); // erst, wenn die Daten gelesen sind
  });

  // Seitenleiste: hochgeladen, bevor HTMX den neuen Inhalt einsetzt; bei Fehlern bleibt die Auswahl
  document.addEventListener("htmx:beforeSwap", (event) => {
    const { requestConfig, xhr } = (event as CustomEvent).detail;
    const feld = requestConfig?.elt as Element | undefined;
    if (feld?.matches?.(FELD) && xhr.status < 400) auswahl.delete(schluessel(feld as HTMLFormElement));
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    const { requestConfig, successful } = (event as CustomEvent).detail;
    const feld = requestConfig?.elt as Element | undefined;
    if (feld?.matches?.(FELD) && !successful) sperren(feld as HTMLFormElement, false);
  });

  // Ziehen: nur die Kachel nimmt Dateien an. Daneben passiert nichts, der Browser öffnet die Datei nicht
  const ziehen = (event: DragEvent) => {
    if (!mitDateien(event) || (event.target as Element | null)?.closest?.('input[type="file"]:not(.anhang-feld__datei)')) return;
    const feld = feldAn(event);
    const ziel = feld?.classList.contains("anhang-feld--laedt") ? null : feld;
    event.preventDefault();
    event.dataTransfer!.dropEffect = ziel ? "copy" : "none";
    ziehenMarkieren(ziel);
  };
  document.addEventListener("dragenter", ziehen);
  document.addEventListener("dragover", ziehen);
  document.addEventListener("dragleave", (event) => {
    if (!event.relatedTarget) ziehenMarkieren(null); // Fenster verlassen
  });
  document.addEventListener("drop", (event) => {
    if (!mitDateien(event) || (event.target as Element | null)?.closest?.('input[type="file"]:not(.anhang-feld__datei)')) return;
    event.preventDefault();
    ziehenMarkieren(null);
    const feld = feldAn(event);
    if (!feld || feld.classList.contains("anhang-feld--laedt")) return;
    const daten = event.dataTransfer!;
    if (daten.files.length > 1) return void toast(t("anhang_nur_eine"), { art: "info" });
    if (Array.from(daten.items).some((i) => i.webkitGetAsEntry?.()?.isDirectory)) return void toast(t("anhang_ordner"), { art: "info" });
    if (daten.files[0]) waehlen(feld, daten.files[0]);
  });

  window.addEventListener("beforeunload", (event) => {
    if (unterwegs || !offene(document).length) return;
    event.preventDefault();
  });
  // Zurück aus dem Zwischenspeicher des Browsers: das Formular ist wieder benutzbar
  window.addEventListener("pageshow", (event) => {
    unterwegs = false;
    if (event.persisted) offene(document).forEach(anzeigen);
  });

  anhangfelderAbgleichen(document);
  // Firefox stellt nach dem Neuladen die Auswahl im Dateifeld wieder her
  document.querySelectorAll<HTMLFormElement>(FELD).forEach((feld) => {
    const datei = eingabe(feld).files?.[0];
    if (datei && !auswahl.has(schluessel(feld))) waehlen(feld, datei);
  });
}
