/** Tiptap-Erweiterungen für Beschreibungen (HTML) und Notizen (Markdown), siehe index.ts. */
import { textblockTypeInputRule } from "@tiptap/core";
import Heading from "@tiptap/extension-heading";
import { TableKit } from "@tiptap/extension-table";
import { Placeholder } from "@tiptap/extensions";
import { Markdown } from "@tiptap/markdown";
import StarterKit from "@tiptap/starter-kit";

// Beschreibungen kennen nur eine Überschriftenebene (h3); „#“ bis „######“ am Zeilenanfang führen dorthin
const ZwischenUeberschrift = Heading.extend({
  addInputRules() {
    return [textblockTypeInputRule({ find: /^#{1,6}\s$/, type: this.type, getAttributes: { level: 3 } })];
  },
});

export function erweiterungen(markdown: boolean, platzhalter: string) {
  const gemeinsam = [
    Placeholder.configure({ placeholder: platzhalter }),
    // Auch bei HTML: nur zum Umwandeln von eingefügtem Markdown
    Markdown.configure({ markedOptions: { gfm: true, breaks: true } }),
  ];
  if (markdown) {
    // Nur, was sich als Markdown speichern lässt (Python-Markdown „extra“): kein Unterstrichen,
    // kein Durchgestrichen; Tabellen bleiben erhalten
    return [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, underline: false, strike: false, link: { openOnClick: false, autolink: true } }),
      TableKit.configure({ table: { resizable: false } }),
      ...gemeinsam,
    ];
  }
  return [
    StarterKit.configure({ heading: false, link: { openOnClick: false, autolink: true } }),
    ZwischenUeberschrift.configure({ levels: [3] }),
    ...gemeinsam,
  ];
}
