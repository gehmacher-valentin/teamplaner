import { useEffect, useRef, useState } from "react";

/** Zustand, der pro Browser im localStorage bleibt (nur Bequemlichkeit, nie Pflichtdaten). */
export function useGespeichert<T extends object>(schluessel: string, vorgabe: T): [T, (aenderung: Partial<T>) => void] {
  const [wert, setWert] = useState<T>(() => {
    try {
      const roh = window.localStorage.getItem(schluessel);
      return roh ? { ...vorgabe, ...JSON.parse(roh) } : vorgabe;
    } catch {
      return vorgabe;
    }
  });
  const aendern = (aenderung: Partial<T>) =>
    setWert((alt) => {
      const neu = { ...alt, ...aenderung };
      try {
        window.localStorage.setItem(schluessel, JSON.stringify(neu));
      } catch {
        /* privater Modus o. Ä. */
      }
      return neu;
    });
  return [wert, aendern];
}

export function useMediaQuery(abfrage: string): boolean {
  const [treffer, setTreffer] = useState(() => window.matchMedia(abfrage).matches);
  useEffect(() => {
    const mq = window.matchMedia(abfrage);
    const aendern = () => setTreffer(mq.matches);
    mq.addEventListener("change", aendern);
    return () => mq.removeEventListener("change", aendern);
  }, [abfrage]);
  return treffer;
}

/** Ruft ``rueckruf`` höchstens alle ``ms`` Millisekunden auf (letzter Aufruf gewinnt). */
export function useEntprellt(rueckruf: () => void, ms: number): () => void {
  const timer = useRef<number>();
  const aktuell = useRef(rueckruf);
  aktuell.current = rueckruf;
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => aktuell.current(), ms);
  };
}
