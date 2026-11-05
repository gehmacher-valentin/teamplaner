/**
 * Übersetzung im Browser. Die Sprache kommt aus dem lang-Attribut der Seite,
 * das Django passend zur Kontoeinstellung setzt. Jedes Wörterbuch muss alle Schlüssel
 * des deutschen enthalten – das prüft TypeScript über den Typ ``Woerterbuch``.
 */

export const SPRACHEN = ["de", "en"] as const;
export type Sprache = (typeof SPRACHEN)[number];

export function sprache(): Sprache {
  const lang = typeof document !== "undefined" ? document.documentElement.lang.slice(0, 2) : "de";
  return (SPRACHEN as readonly string[]).includes(lang) ? (lang as Sprache) : "de";
}

export type Woerterbuch<T extends Record<string, string>> = { [K in keyof T]: string };

export function uebersetzer<T extends Record<string, string>>(woerterbuecher: { de: T } & Record<Exclude<Sprache, "de">, Woerterbuch<T>>) {
  return function t(schluessel: keyof T, werte: Record<string, string | number> = {}): string {
    const text = woerterbuecher[sprache()]?.[schluessel] ?? woerterbuecher.de[schluessel];
    return String(text).replace(/\{(\w+)\}/g, (_, name) => String(werte[name] ?? `{${name}}`));
  };
}
