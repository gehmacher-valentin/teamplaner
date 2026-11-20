/**
 * Schriftfarbe und Marker im Editor: feste Palette, gespeichert als <span data-farbe="…"> bzw.
 * <mark data-farbe="…"> ohne Inline-Styles. Die Farben selbst kommen aus dem CSS (hell und dunkel).
 * In Notizen (Markdown) stehen sie als kleines HTML im Text; der Server lässt nur diese Tags mit
 * den Werten hier durch (projekte.dienste.html_bereinigen, notizen.markdown.als_html).
 */
import { type CommandProps, Mark, mergeAttributes } from "@tiptap/core";

export const SCHRIFTFARBEN = ["rot", "orange", "gruen", "blau", "violett", "grau"] as const;
export const MARKERFARBEN = ["gelb", "gruen", "blau", "rosa"] as const;

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    farben: {
      schriftfarbeSetzen: (farbe: string | null) => ReturnType;
      markerSetzen: (farbe: string | null) => ReturnType;
    };
  }
}

function farbMark(name: "schriftfarbe" | "marker", tag: "span" | "mark", farben: readonly string[], befehl: "schriftfarbeSetzen" | "markerSetzen") {
  const gueltig = (wert: string | null) => (wert && farben.includes(wert) ? wert : null);
  return Mark.create({
    name,
    // Vor Fett/Kursiv (100) im Schema: die Farbe liegt außen, Fett/Kursiv innen
    priority: 150,
    addAttributes() {
      return {
        farbe: {
          default: farben[0],
          parseHTML: (el: HTMLElement) => gueltig(el.getAttribute("data-farbe")) ?? farben[0],
          renderHTML: (attrs: { farbe?: string }) => ({ "data-farbe": attrs.farbe }),
        },
      };
    },
    parseHTML() {
      return [{
        tag: `${tag}[data-farbe]`,
        getAttrs: (el: HTMLElement) => (gueltig(el.getAttribute("data-farbe")) ? null : false),
      }];
    },
    renderHTML({ HTMLAttributes }) {
      return [tag, mergeAttributes(HTMLAttributes), 0];
    },
    renderMarkdown(node, helfer) {
      const farbe = gueltig((node.attrs?.farbe as string | undefined) ?? null) ?? farben[0];
      return `<${tag} data-farbe="${farbe}">${helfer.renderChildren(node)}</${tag}>`;
    },
    addCommands() {
      return {
        [befehl]: (farbe: string | null) => ({ chain }: CommandProps) => {
          const kette = chain().focus().extendMarkRange(name);
          return gueltig(farbe) ? kette.setMark(name, { farbe }).run() : kette.unsetMark(name).run();
        },
      };
    },
  });
}

export const Schriftfarbe = farbMark("schriftfarbe", "span", SCHRIFTFARBEN, "schriftfarbeSetzen");
export const Marker = farbMark("marker", "mark", MARKERFARBEN, "markerSetzen");
