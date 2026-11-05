/**
 * Feieranimation beim Abhaken einer Aufgabe. Nur wenn im Konto eingeschaltet –
 * der Server setzt dann data-feiern am <body> (nach einem Seitenwechsel) oder schickt
 * das HTMX-Ereignis „feiern“ (beim Abhaken in der Liste).
 * Damit es eine Überraschung bleibt, feiert nur etwa jedes zweite Abhaken.
 * Bei „Bewegung reduzieren“ erscheint die Figur nur kurz, ohne zu fliegen, ohne Konfetti.
 * Grafiken: Fluent Emoji von Microsoft (MIT-Lizenz, siehe feiern/LIZENZ.txt).
 */
import rakete from "./feiern/rocket.svg";
import knaller from "./feiern/party-popper.svg";
import pokal from "./feiern/trophy.svg";
import sternaugen from "./feiern/star-struck.svg";
import konfettiball from "./feiern/confetti-ball.svg";

/** Im Schnitt jedes zweite Abhaken */
const WAHRSCHEINLICHKEIT = 0.5;

type Figur = { bild: string; art: "flug" | "auftritt"; name: string };

const FIGUREN: Figur[] = [
  { bild: rakete, art: "flug", name: "rakete" },
  { bild: knaller, art: "auftritt", name: "knaller" },
  { bild: pokal, art: "auftritt", name: "pokal" },
  { bild: sternaugen, art: "auftritt", name: "sternaugen" },
  { bild: konfettiball, art: "auftritt", name: "konfettiball" },
];

const FARBEN = ["#f472b6", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#fb7185"];

function konfetti(huelle: HTMLElement) {
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

/** ``immer``: ohne Zufall (z. B. zum Ausprobieren). */
export function feiern(immer = false) {
  if (!immer && Math.random() >= WAHRSCHEINLICHKEIT) return;
  const ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const figur = FIGUREN[Math.floor(Math.random() * FIGUREN.length)];
  const art = ruhig ? "ruhig" : figur.art;

  const huelle = document.createElement("div");
  huelle.className = `feier feier--${art} feier--${figur.name}`;
  huelle.setAttribute("aria-hidden", "true");
  const figurElement = document.createElement("div");
  figurElement.className = "feier__figur";
  const bild = new Image();
  bild.src = figur.bild;
  bild.alt = "";
  bild.className = "feier__bild";
  figurElement.append(bild);
  huelle.append(figurElement);
  if (!ruhig) konfetti(huelle);

  // Erst zeigen, wenn die Grafik geladen ist – sonst fliegt beim ersten Mal ein leerer Rahmen
  bild.decode().catch(() => undefined).then(() => {
    document.body.append(huelle);
    window.setTimeout(() => huelle.remove(), ruhig ? 1600 : 2800);
  });
}

export function initFeiern() {
  if (document.body.dataset.feiern) {
    delete document.body.dataset.feiern;
    window.setTimeout(() => feiern(), 150);
  }
  document.body.addEventListener("feiern", () => feiern());
}
