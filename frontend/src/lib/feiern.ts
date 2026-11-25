/**
 * Feieranimation beim Abhaken einer Aufgabe. Nur wenn im Konto eingeschaltet:
 * der Server setzt dann data-feiern am <body> (nach einem Seitenwechsel) oder schickt
 * das HTMX-Ereignis „feiern“ (beim Abhaken in der Liste).
 * Jedes Abhaken feiert, mit einer zufälligen Figur, nie zweimal hintereinander dieselbe.
 * Bei „Bewegung reduzieren“ wird die Figur in der Mitte nur ein- und ausgeblendet, ohne Bewegung, ohne Konfetti.
 * Grafiken: Fluent Emoji von Microsoft (MIT-Lizenz) und das Einhorn „Unicorn Rainbow“ von
 * Praveen Singh (Lottie Simple License), siehe feiern/LIZENZ.txt.
 */
import rakete from "./feiern/rocket.svg";
import ufo from "./feiern/flying-saucer.svg";
import kaenguru from "./feiern/kangaroo.svg";
import trex from "./feiern/t-rex.svg";
import flamingo from "./feiern/flamingo.svg";
import otter from "./feiern/otter.svg";
import lama from "./feiern/llama.svg";
import geist from "./feiern/ghost.svg";
import partygesicht from "./feiern/partying-face.svg";
import pinata from "./feiern/pinata.svg";

type Konfetti = "regen" | "platzen";
interface Figur {
  name: string;
  /** Grafik; fehlt beim Einhorn (Lottie-Animation, eigenes Modul) */
  bild?: string;
  /** Gesamtdauer in ms, danach wird die Hülle entfernt */
  dauer: number;
  konfetti?: Konfetti;
}

export const FIGUREN: readonly Figur[] = [
  { name: "einhorn", dauer: 4600 },
  { name: "rakete", bild: rakete, dauer: 2800, konfetti: "regen" },
  { name: "ufo", bild: ufo, dauer: 3100 },
  { name: "kaenguru", bild: kaenguru, dauer: 3300 },
  { name: "trex", bild: trex, dauer: 3700 },
  { name: "flamingo", bild: flamingo, dauer: 2700, konfetti: "regen" },
  { name: "otter", bild: otter, dauer: 4100 },
  { name: "lama", bild: lama, dauer: 2900 },
  { name: "geist", bild: geist, dauer: 3300 },
  { name: "partygesicht", bild: partygesicht, dauer: 2800, konfetti: "regen" },
  { name: "pinata", bild: pinata, dauer: 4100, konfetti: "platzen" },
];

/** Piñata platzt nach dieser Zeit: 66 % von 3,4 s (feier-pinata-bild in app.css) */
const PINATA_PLATZT_MS = 2244;

const FARBEN = ["#f472b6", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#fb7185"];
const SPEICHER = "teamplaner-letzte-feier";

/** Zufällige Figur, aber nie dieselbe wie zuletzt. */
export function naechsteFigur(namen: readonly string[], letzte: string | null, zufall: () => number = Math.random): string {
  const auswahl = namen.length > 1 ? namen.filter((n) => n !== letzte) : namen;
  return auswahl[Math.min(auswahl.length - 1, Math.floor(zufall() * auswahl.length))];
}

function letzteLesen(): string | null {
  try {
    return window.sessionStorage.getItem(SPEICHER);
  } catch {
    return null;
  }
}

function letzteMerken(name: string) {
  try {
    window.sessionStorage.setItem(SPEICHER, name);
  } catch {
    /* privater Modus o. Ä. */
  }
}

/** Konfetti fällt von oben über die ganze Breite */
function konfettiRegen(huelle: HTMLElement) {
  for (let i = 0; i < 36; i += 1) {
    const stueck = document.createElement("span");
    stueck.className = "feier__konfetti";
    stueck.style.left = `${Math.random() * 100}vw`;
    stueck.style.background = FARBEN[i % FARBEN.length];
    stueck.style.animationDelay = `${Math.random() * 0.6}s`;
    stueck.style.animationDuration = `${1.6 + Math.random() * 0.9}s`;
    stueck.style.setProperty("--drift", `${(Math.random() - 0.5) * 30}vw`);
    stueck.style.setProperty("--dreh", `${(Math.random() - 0.5) * 1440}deg`);
    huelle.append(stueck);
  }
}

/** Konfetti platzt von einem Punkt aus in alle Richtungen und fällt dann */
function konfettiPlatzen(huelle: HTMLElement, x: number, y: number) {
  for (let i = 0; i < 44; i += 1) {
    const stueck = document.createElement("span");
    stueck.className = "feier__konfetti feier__konfetti--platzen";
    stueck.style.left = `${x}px`;
    stueck.style.top = `${y}px`;
    stueck.style.background = FARBEN[i % FARBEN.length];
    const winkel = Math.random() * Math.PI * 2;
    const weite = 80 + Math.random() * 220;
    stueck.style.setProperty("--dx", `${Math.cos(winkel) * weite}px`);
    stueck.style.setProperty("--dy", `${Math.sin(winkel) * weite * 0.8 - 60}px`);
    stueck.style.setProperty("--dreh", `${(Math.random() - 0.5) * 1080}deg`);
    stueck.style.animationDuration = `${1.1 + Math.random() * 0.6}s`;
    huelle.append(stueck);
  }
}

function bildElement(quelle: string) {
  const bild = new Image();
  bild.src = quelle;
  bild.alt = "";
  bild.className = "feier__bild";
  return bild;
}

function zeigeRuhig(figur: Figur & { bild: string }) {
  const huelle = document.createElement("div");
  huelle.className = "feier feier--ruhig";
  huelle.dataset.figur = figur.name;
  huelle.setAttribute("aria-hidden", "true");
  const figurElement = document.createElement("div");
  figurElement.className = "feier__figur";
  const bild = bildElement(figur.bild);
  figurElement.append(bild);
  huelle.append(figurElement);
  bild.decode().catch(() => undefined).then(() => {
    document.body.append(huelle);
    window.setTimeout(() => huelle.remove(), 1800);
  });
}

function zeigeFigur(figur: Figur & { bild: string }) {
  const huelle = document.createElement("div");
  huelle.className = `feier feier--${figur.name}`;
  huelle.dataset.figur = figur.name;
  huelle.setAttribute("aria-hidden", "true");
  const figurElement = document.createElement("div");
  figurElement.className = "feier__figur";
  if (figur.name === "pinata") {
    const schnur = document.createElement("span");
    schnur.className = "feier__schnur";
    figurElement.append(schnur);
  }
  const bild = bildElement(figur.bild);
  figurElement.append(bild);
  huelle.append(figurElement);
  if (figur.konfetti === "regen") konfettiRegen(huelle);

  // Erst zeigen, wenn die Grafik geladen ist, sonst fliegt beim ersten Mal ein leerer Rahmen
  bild.decode().catch(() => undefined).then(() => {
    document.body.append(huelle);
    if (figur.konfetti === "platzen") {
      window.setTimeout(() => {
        const r = bild.getBoundingClientRect();
        konfettiPlatzen(huelle, r.left + r.width / 2, r.top + r.height / 2);
      }, PINATA_PLATZT_MS);
    }
    window.setTimeout(() => huelle.remove(), figur.dauer);
  });
}

/** Spielt eine Figur ab: die genannte oder eine zufällige (nie zweimal hintereinander dieselbe). */
export function feiern(name?: string) {
  const ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Das Einhorn lebt von der Bewegung; ruhig nur die Figuren mit Grafik
  const moeglich = FIGUREN.filter((f) => !ruhig || f.bild);
  const gewaehlt = name ?? naechsteFigur(moeglich.map((f) => f.name), letzteLesen());
  const figur = moeglich.find((f) => f.name === gewaehlt) ?? moeglich[0];
  letzteMerken(figur.name);

  if (!figur.bild) {
    import("./feiern/einhorn")
      .then((m) => m.einhornFliegen(figur.dauer))
      .catch(() => feiern("rakete"));
    return;
  }
  const mitBild = figur as Figur & { bild: string };
  if (ruhig) zeigeRuhig(mitBild);
  else zeigeFigur(mitBild);
}

/** Knopf „Nächste Figur“ in den Einstellungen: alle Figuren der Reihe nach ansehen. */
let probeIndex = 0;
function probe() {
  const figur = FIGUREN[probeIndex % FIGUREN.length];
  probeIndex += 1;
  feiern(figur.name);
}

export function initFeiern() {
  if (document.body.dataset.feiern) {
    delete document.body.dataset.feiern;
    window.setTimeout(() => feiern(), 150);
  }
  document.body.addEventListener("feiern", () => feiern());
  document.addEventListener("click", (ereignis) => {
    if ((ereignis.target as Element | null)?.closest?.("[data-feier-probe]")) probe();
  });
}
