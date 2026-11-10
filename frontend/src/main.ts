// Gemeinsames Skript aller Seiten: Schriften, Styles, HTMX und kleine Helfer.
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-ext-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-ext-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-ext-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import "@fontsource/ibm-plex-sans/latin-ext-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "./styles/app.css";

import htmx from "htmx.org";
import { initAufgabenBaum } from "./lib/aufgabenbaum";
import { initErwaehnungen } from "./lib/erwaehnungen";
import { initFeiern } from "./lib/feiern";
import { initFreigaben } from "./lib/freigaben";
import { initInline, mitwachsen } from "./lib/inline";
import { initListeneditor } from "./lib/listeneditor";
import { initNotizbaum } from "./lib/notizbaum";
import { initPersonenauswahl } from "./lib/personenauswahl";
import { initPersonenwahl } from "./lib/personenwahl";
import { initReihenfolge } from "./lib/reihenfolge";
import { initSeitenleiste, seitenleisteAbgleichen } from "./lib/seitenleiste";
import { initSofort } from "./lib/sofort";
import { initSitzungsfrist } from "./lib/sitzungsfrist";
import { initSortierbar } from "./lib/sortierbar";
import { initSpaltenbreiten } from "./lib/spaltenbreiten";
import { initSuchvorschlaege } from "./lib/suchvorschlaege";
import { initToasts, toast } from "./lib/toast";
import { initUnteraufgaben } from "./lib/unteraufgaben";
import { initVorschlaege } from "./lib/vorschlaege";
import { csrfToken, zurAnmeldung } from "./lib/csrf";
import { t } from "./lib/texte";

declare global {
  interface Window {
    htmx: typeof htmx;
  }
}
window.htmx = htmx;
// Kein eval: die Content-Security-Policy erlaubt nur Skripte aus eigenen Dateien
htmx.config.allowEval = false;
htmx.config.allowScriptTags = false;

document.addEventListener("htmx:configRequest", (event) => {
  (event as CustomEvent).detail.headers["X-CSRFToken"] = csrfToken();
});

// Abgelaufene Sitzung (z. B. Admin nach Inaktivität abgemeldet): Antworten, die auf der Anmeldeseite
// gelandet sind, nicht in die Seite einsetzen, sondern die ganze Seite zur Anmeldung schicken
document.addEventListener("htmx:beforeSwap", (event) => {
  const xhr = (event as CustomEvent).detail.xhr as XMLHttpRequest | undefined;
  if (xhr?.responseURL && new URL(xhr.responseURL).pathname === "/anmelden/") {
    event.preventDefault();
    zurAnmeldung();
  }
});

function init(wurzel: ParentNode) {
  initSortierbar(wurzel);
  initAufgabenBaum(wurzel);
  initErwaehnungen(wurzel);
  initKategorien(wurzel);
  initPersonenauswahl(wurzel);
  initPersonenwahl(wurzel);
  initVorschlaege(wurzel);
  mitwachsen(wurzel);
  initSpaltenbreiten(wurzel);
  initReihenfolge(wurzel);
  initFreigaben(wurzel);
  seitenleisteAbgleichen();
}

// Kategorie-Schalter schaltet alle Ereignisse darin (E-Mail-Benachrichtigungen); gespeichert wird
// die ganze Kategorie in einer Anfrage (verwaltung.einstellungen.benachrichtigung_speichern)
function initKategorien(wurzel: ParentNode) {
  wurzel.querySelectorAll<HTMLInputElement>("input[data-kategorie]").forEach((alle) => {
    const kinder = Array.from(
      alle.closest("section, fieldset")?.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:not([data-kategorie])') ?? [],
    );
    const aktualisieren = () => {
      const an = kinder.filter((k) => k.checked).length;
      alle.checked = an === kinder.length && an > 0;
      alle.indeterminate = an > 0 && an < kinder.length;
    };
    alle.addEventListener("change", () => kinder.forEach((k) => (k.checked = alle.checked)));
    kinder.forEach((k) => k.addEventListener("change", aktualisieren));
    aktualisieren();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSeitenleiste();
  init(document);
  initFeiern();
  initInline();
  initListeneditor();
  initSofort();
  initToasts();
  initUnteraufgaben();
  initNotizbaum();
  initSitzungsfrist();
  initSuchvorschlaege();
});
htmx.onLoad((element) => init(element as ParentNode));

// Mitteilungszentrale im Kopf: Glocke öffnet das Feld, Klick daneben oder Esc schließt es
function mitteilungenSchliessen() {
  const knopf = document.querySelector<HTMLButtonElement>(".mitteilungen__knopf");
  const feld = document.getElementById("mitteilungen-feld");
  if (!knopf || !feld || feld.hidden) return;
  feld.hidden = true;
  knopf.setAttribute("aria-expanded", "false");
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !document.getElementById("mitteilungen-feld")?.hidden) {
    mitteilungenSchliessen();
    document.querySelector<HTMLButtonElement>(".mitteilungen__knopf")?.focus();
  }
});

// Menü der Kopfzeile: Name und Bild öffnen „Einstellungen“ und „Abmelden“
function kopfmenue(oeffnen: boolean, fokus = false) {
  const knopf = document.querySelector<HTMLButtonElement>("[data-kopfmenue] .kopf__nutzer");
  const liste = document.getElementById("kopfmenue-liste");
  if (!knopf || !liste) return;
  liste.hidden = !oeffnen;
  knopf.setAttribute("aria-expanded", String(oeffnen));
  if (oeffnen && fokus) liste.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  if (!oeffnen && fokus) knopf.focus();
}
document.addEventListener("keydown", (event) => {
  const liste = document.getElementById("kopfmenue-liste");
  if (!liste || liste.hidden) return;
  const eintraege = Array.from(liste.querySelectorAll<HTMLElement>('[role="menuitem"]'));
  const i = eintraege.indexOf(document.activeElement as HTMLElement);
  if (event.key === "Escape") kopfmenue(false, true);
  else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const n = eintraege.length;
    eintraege[(i + (event.key === "ArrowDown" ? 1 : n - 1) + n) % n]?.focus();
  }
});

// Mobile Navigation
document.addEventListener("click", (event) => {
  const ziel = event.target as HTMLElement;
  const nutzer = ziel.closest<HTMLButtonElement>("[data-kopfmenue] .kopf__nutzer");
  if (nutzer) {
    kopfmenue(nutzer.getAttribute("aria-expanded") !== "true", event.detail === 0);
    return;
  }
  if (!ziel.closest("[data-kopfmenue]")) kopfmenue(false);
  const glocke = ziel.closest<HTMLButtonElement>(".mitteilungen__knopf");
  if (glocke) {
    const feld = document.getElementById("mitteilungen-feld")!;
    const oeffnen = feld.hidden;
    if (oeffnen) {
      feld.innerHTML = `<div class="leer">${t("laedt")}</div>`;
      htmx.ajax("get", glocke.dataset.url!, { target: feld, swap: "innerHTML" });
    }
    feld.hidden = !oeffnen;
    glocke.setAttribute("aria-expanded", String(oeffnen));
    return;
  }
  if (!ziel.closest("[data-mitteilungen]")) mitteilungenSchliessen();
  const menue = ziel.closest<HTMLButtonElement>("[data-menue]");
  if (menue) {
    const nav = document.getElementById(menue.dataset.menue!);
    const offen = nav?.classList.toggle("offen") ?? false;
    menue.setAttribute("aria-expanded", String(offen));
    return;
  }
  // Text in die Zwischenablage kopieren (z. B. Einladungslink)
  const kopieren = ziel.closest<HTMLElement>("[data-kopieren]");
  if (kopieren) {
    const text = kopieren.dataset.kopieren!;
    navigator.clipboard?.writeText(text).then(() => {
      const vorher = kopieren.textContent;
      kopieren.textContent = kopieren.dataset.kopiertText ?? t("kopiert");
      setTimeout(() => (kopieren.textContent = vorher), 1500);
    });
  }
  // Kommentare: Verlaufseinträge ein- und ausblenden (Aufgabendetail, nicht gespeichert)
  const verlauf = ziel.closest<HTMLElement>("[data-verlauf-umschalten]");
  if (verlauf) {
    const an = verlauf.closest(".kommentare")?.classList.toggle("kommentare--verlauf") ?? false;
    verlauf.setAttribute("aria-pressed", String(an));
  }
  // Drucken (z. B. Ersatzcodes der Zwei-Faktor-Anmeldung)
  if (ziel.closest("[data-drucken]")) window.print();
  // Filter hinter einem Knopf (Projektliste)
  const filter = ziel.closest<HTMLElement>("[data-filter-umschalten]");
  if (filter) {
    const offen = document.getElementById(filter.getAttribute("aria-controls")!)?.classList.toggle("offen") ?? false;
    filter.setAttribute("aria-expanded", String(offen));
  }
  // Dialoge öffnen/schließen
  const oeffnen = ziel.closest<HTMLElement>("[data-dialog-oeffnen]");
  if (oeffnen) {
    document.querySelector<HTMLDialogElement>(oeffnen.dataset.dialogOeffnen!)?.showModal();
  }
  const schliessen = ziel.closest<HTMLElement>("[data-dialog-schliessen]");
  if (schliessen) {
    schliessen.closest("dialog")?.close();
  }
});

// Fehlgeschlagene HTMX-Anfragen (Server- oder Netzfehler) als Toast, statt still nichts zu tun
document.addEventListener("htmx:responseError", () => toast(t("speichern_fehlgeschlagen"), { art: "fehler" }));
document.addEventListener("htmx:sendError", () => toast(t("speichern_fehlgeschlagen"), { art: "fehler" }));

// Formulare mit data-nach-erfolg-leeren nach erfolgreichem HTMX-Absenden leeren (neue Bestellzeile)
document.addEventListener("htmx:afterRequest", (event) => {
  const formular = event.target as HTMLElement;
  const detail = (event as CustomEvent).detail;
  if (formular instanceof HTMLFormElement && formular.matches("[data-nach-erfolg-leeren]") && detail.successful
      && !detail.xhr?.getResponseHeader("X-Fehler")) {
    const datum = formular.querySelector<HTMLInputElement>('input[type="date"][required]');
    const heute = datum?.value;
    formular.reset();
    if (datum && heute) datum.value = heute;
    formular.querySelector<HTMLElement>('textarea, input[type="text"]')?.focus();
  }
});

// Formular-Elemente mit data-auto-absenden schicken das Formular bei Änderung ab (außer, das Formular
// speichert ohnehin bei jeder Änderung per HTMX, hx-trigger="change")
document.addEventListener("change", (event) => {
  const feld = event.target as HTMLElement;
  if (feld.matches("[data-auto-absenden]")) {
    const formular = (feld as HTMLInputElement).form;
    if (formular && !(formular.getAttribute("hx-trigger") ?? "").includes("change")) formular.requestSubmit();
  }
});

// Formulare mit data-bestaetigen fragen vor dem Absenden nach (z. B. Löschen); in der Capture-Phase,
// damit eine Absage auch Formulare mit HTMX aufhält
document.addEventListener(
  "submit",
  (event) => {
    const formular = event.target as HTMLFormElement;
    const frage = formular.dataset.bestaetigen;
    if (frage && !window.confirm(frage)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },
  true,
);
