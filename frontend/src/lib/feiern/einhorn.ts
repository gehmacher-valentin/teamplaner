/**
 * Einhorn der Feieranimation: galoppiert (Lottie) von links unten nach rechts oben, dahinter eine
 * Regenbogen-Spur mit Verlauf und weißem Schein, Sparkles funkeln entlang der Spur.
 * Eigenes Modul, damit lottie-web erst beim ersten Einhorn geladen wird.
 */
import lottie from "lottie-web/build/player/lottie_light";
import daten from "./einhorn.json";
import funkeBild from "./sparkles.svg";

const NS = "http://www.w3.org/2000/svg";
const FARBEN = ["#FF6B8B", "#FFA45B", "#FFE27A", "#6FE0A0", "#6CC2FF", "#A77BFF"];
/** Seitenverhältnis der zugeschnittenen Animation (608 × 547) */
const HOEHE_ZU_BREITE = 547 / 608;
/** Anteil der Gesamtdauer für den Flug, der Rest gehört dem Ausblenden der Spur */
const FLUG = 0.63;

let nummer = 0;

type Punkt = [number, number];

export function einhornFliegen(dauer: number) {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const groesse = Math.min(240, W * 0.22);
  const flugdauer = dauer * FLUG;
  const band = Math.max(5, groesse * 0.04);
  const id = `feier-einhorn-${(nummer += 1)}`;

  const huelle = document.createElement("div");
  huelle.className = "feier feier--einhorn";
  huelle.dataset.figur = "einhorn";
  huelle.setAttribute("aria-hidden", "true");

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "feier__spur");
  svg.setAttribute("width", String(W));
  svg.setAttribute("height", String(H));
  svg.innerHTML = `<defs>
      <linearGradient id="${id}-aus" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.85" stop-color="#fff" stop-opacity="1"/></linearGradient>
      <mask id="${id}-maske" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="url(#${id}-aus)"/></mask>
      <filter id="${id}-weich"><feGaussianBlur stdDeviation="1.3"/></filter>
      <filter id="${id}-schein" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="${band * 1.6}"/></filter>
    </defs>
    <g mask="url(#${id}-maske)">
      <path class="feier__spur-schein" fill="none" stroke="#fff" stroke-width="${band * 9}" stroke-linecap="round" opacity="0.85" filter="url(#${id}-schein)"/>
      <g filter="url(#${id}-weich)" fill="none" stroke-linecap="round" stroke-width="${band + 0.5}">
        ${FARBEN.map((farbe) => `<path class="feier__spur-band" stroke="${farbe}"/>`).join("")}
      </g>
    </g>`;
  huelle.append(svg);

  const figur = document.createElement("div");
  figur.className = "feier__einhorn";
  figur.style.width = `${groesse}px`;
  figur.style.height = `${groesse * HOEHE_ZU_BREITE}px`;
  huelle.append(figur);
  document.body.append(huelle);

  const animation = lottie.loadAnimation({ container: figur, renderer: "svg", loop: true, autoplay: true, animationData: daten });
  animation.setSpeed(1.3);

  // Flugbahn: kubische Bezier von links unten nach rechts oben
  const P: Punkt[] = [[-groesse, H * 0.86], [W * 0.3, H * 0.78], [W * 0.62, H * 0.42], [W + groesse * 0.6, H * 0.1]];
  const punkt = (t: number): Punkt => {
    const u = 1 - t;
    const k = (i: 0 | 1) => u * u * u * P[0][i] + 3 * u * u * t * P[1][i] + 3 * u * t * t * P[2][i] + t * t * t * P[3][i];
    return [k(0), k(1)];
  };
  const richtung = (t: number) => {
    const a = punkt(Math.max(0, t - 0.01));
    const b = punkt(Math.min(1, t + 0.01));
    return Math.atan2(b[1] - a[1], b[0] - a[0]);
  };
  // Die Spur kommt am Hinterteil heraus, ein Stück hinter der Mitte des Einhorns
  const hinten = (t: number): Punkt => {
    const [x, y] = punkt(t);
    const w = richtung(t);
    const r = groesse * 0.32;
    return [x - Math.cos(w) * r, y - Math.sin(w) * r + groesse * 0.06];
  };

  const baender = [...svg.querySelectorAll<SVGPathElement>(".feier__spur-band")];
  const schein = svg.querySelector<SVGPathElement>(".feier__spur-schein")!;
  const verlauf = svg.querySelector<SVGLinearGradientElement>(`#${id}-aus`)!;
  const start = performance.now();
  let letzterFunke = 0;

  function funke(x: number, y: number) {
    const bild = new Image();
    bild.src = funkeBild;
    bild.alt = "";
    bild.className = "feier__funke";
    const s = (0.08 + Math.random() * 0.09) * groesse;
    bild.style.width = `${s}px`;
    bild.style.left = `${x + (Math.random() - 0.5) * groesse * 0.5 - s / 2}px`;
    bild.style.top = `${y + (Math.random() - 0.5) * groesse * 0.45 - s / 2}px`;
    huelle.append(bild);
    bild.animate([
      { transform: "scale(0) rotate(-30deg)", opacity: 0 },
      { transform: "scale(1.25) rotate(10deg)", opacity: 1, offset: 0.25 },
      { transform: "scale(1) rotate(0deg)", opacity: 1, offset: 0.5 },
      { transform: "scale(0.6) rotate(15deg)", opacity: 0 },
    ], { duration: 1100 + Math.random() * 400, easing: "ease-out", fill: "forwards" });
  }

  function bild(jetzt: number) {
    const roh = Math.min(1, (jetzt - start) / flugdauer);
    // Sanfter Start, dann gleichmäßig
    const t = roh < 0.5 ? 2 * roh * roh * 0.9 + roh * 0.1 : roh;
    const [x, y] = punkt(t);
    const neigung = (richtung(t) * 180 / Math.PI) * 0.6;
    figur.style.transform = `translate(${x - groesse / 2}px, ${y - groesse * 0.45}px) rotate(${neigung}deg) scaleX(-1)`;

    // Spur: Punkte vom Anfang bis jetzt, sechs parallele Bänder
    const n = 60;
    const punkte: Punkt[] = [];
    for (let i = 0; i <= n; i += 1) punkte.push(hinten((t * i) / n));
    const versatz = (k: number) => punkte.map((p, i) => {
      const a = punkte[Math.max(0, i - 1)];
      const b = punkte[Math.min(n, i + 1)];
      const w = Math.atan2(b[1] - a[1], b[0] - a[0]);
      const o = (k - 2.5) * band;
      return `${(p[0] - Math.sin(w) * o).toFixed(1)},${(p[1] + Math.cos(w) * o).toFixed(1)}`;
    }).join(" L");
    baender.forEach((b, i) => b.setAttribute("d", `M${versatz(i)}`));
    schein.setAttribute("d", `M${versatz(2.5)}`);
    const anfang = hinten(Math.max(0, t - 0.55));
    const ende = hinten(t);
    verlauf.setAttribute("x1", String(anfang[0]));
    verlauf.setAttribute("y1", String(anfang[1]));
    verlauf.setAttribute("x2", String(ende[0]));
    verlauf.setAttribute("y2", String(ende[1]));

    if (jetzt - letzterFunke > 70 && roh < 0.97) {
      letzterFunke = jetzt;
      funke(ende[0], ende[1]);
    }
    if (roh < 1) {
      window.requestAnimationFrame(bild);
    } else {
      svg.classList.add("feier__spur--aus");
      window.setTimeout(() => {
        animation.destroy();
        huelle.remove();
      }, Math.max(0, dauer - flugdauer));
    }
  }
  window.requestAnimationFrame(bild);
}
