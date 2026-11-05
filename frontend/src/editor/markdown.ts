/**
 * Erkennung von Markdown beim Einfügen: Text aus einem Chat oder Editor mit `**`, `#` oder `-`
 * soll als Formatierung ankommen, normaler Text unverändert bleiben.
 */

// Zeilen, die nur in Markdown so beginnen: Überschrift, Liste, Zitat, Codeblock, Trennlinie, Tabelle
const BLOCK = [
  /^#{1,6}\s+\S/,
  /^\s*[-*+]\s+\S/,
  /^\s*\d{1,3}[.)]\s+\S/,
  /^>\s?\S/,
  /^```/,
  /^\s*([-*_])(\s*\1){2,}\s*$/,
  /^\|.*\|\s*$/,
];
// Auszeichnungen innerhalb einer Zeile: fett, kursiv, Code, Link
const INLINE = [/\*\*[^*\n]+\*\*/, /__[^_\n]+__/, /(^|[\s(])\*[^*\s][^*\n]*\*(?=[\s).,:;!?]|$)/, /`[^`\n]+`/, /\[[^\]\n]+\]\([^)\s]+\)/];

/** Sieht der eingefügte Text nach Markdown aus? Eine einzelne Aufzählungszeile reicht nicht. */
export function siehtNachMarkdownAus(text: string): boolean {
  const zeilen = text.split(/\r?\n/);
  const block = zeilen.filter((z) => BLOCK.some((r) => r.test(z))).length;
  if (block >= 2 || (block === 1 && /^(#{1,6}\s|```|>)/.test(zeilen.find((z) => BLOCK.some((r) => r.test(z)))!))) {
    return true;
  }
  return INLINE.some((r) => r.test(text));
}

/** Bringt das HTML aus der Zwischenablage selbst Formatierung mit (Word, Webseite)? Dann gilt das HTML. */
export function hatFormatierung(html: string): boolean {
  return /<(strong|b|em|i|u|h[1-6]|ul|ol|li|a\s|table|blockquote|pre|code)[\s>]/i.test(html);
}
