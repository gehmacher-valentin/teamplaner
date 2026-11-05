// @vitest-environment jsdom
import { Editor } from "@tiptap/core";
import { describe, expect, test } from "vitest";
import { erweiterungen } from "./erweiterungen";
import { hatFormatierung, siehtNachMarkdownAus } from "./markdown";

describe("Markdown beim Einfügen erkennen", () => {
  test.each([
    "## Ablauf\nErst messen, dann bauen",
    "- Verkleidung\n- Bewehrung",
    "1. Messen\n2. Auswerten",
    "Das ist **wichtig**.",
    "Siehe [Plan](https://example.com/plan.pdf)",
    "Befehl `make` ausführen",
    "> Zitat aus der Mail",
  ])("Markdown: %s", (text) => expect(siehtNachMarkdownAus(text)).toBe(true));

  test.each([
    "Normaler Text ohne Auszeichnung.",
    "Stand 3 - 5 cm über Normal",
    "- nur eine Zeile mit Strich",
    "Termin am 1. Mai",
    "2 * 3 = 6 und 4 * 5 = 20",
  ])("kein Markdown: %s", (text) => expect(siehtNachMarkdownAus(text)).toBe(false));

  test("formatiertes HTML (Word, Webseite) hat Vorrang", () => {
    expect(hatFormatierung("<p>Text <strong>fett</strong></p>")).toBe(true);
    expect(hatFormatierung("<meta charset='utf-8'><span>## Titel</span>")).toBe(false);
  });
});

describe("Notizen: Markdown hinein und heraus", () => {
  const notiz = (text: string) => new Editor({ content: text, contentType: "markdown", extensions: erweiterungen(true, "") });

  test("Überschrift, Liste, Link und Tabelle bleiben Markdown", () => {
    const md = notiz("## Messung\n\n- Stand\n- Temperatur\n\n[Plan](https://example.com)\n\n| A | B |\n|---|---|\n| 1 | 2 |").getMarkdown();
    expect(md).toContain("## Messung");
    expect(md).toContain("- Stand\n- Temperatur");
    expect(md).toContain("[Plan](https://example.com)");
    expect(md).toMatch(/\| A +\| B +\|\n\| -+ \| -+ \|\n\| 1 +\| 2 +\|/);
  });

  test("einfacher Zeilenumbruch bleibt ein Umbruch (nl2br)", () => {
    const e = notiz("Zeile eins\nZeile zwei");
    expect(e.getHTML()).toBe("<p>Zeile eins<br>Zeile zwei</p>");
    expect(e.getMarkdown()).toBe("Zeile eins  \nZeile zwei");
  });

  test("ohne Unterstrichen und Durchgestrichen (lassen sich nicht als Markdown speichern)", () => {
    const e = notiz("Text");
    expect(e.schema.marks.underline).toBeUndefined();
    expect(e.schema.marks.strike).toBeUndefined();
  });
});

describe("Beschreibung: HTML", () => {
  test("eingefügtes Markdown wird zu Formatierung, Überschriften zu h3", () => {
    const e = new Editor({ content: "", contentType: "html", extensions: erweiterungen(false, "") });
    e.commands.insertContent("# Ablauf\n\n- **Verkleidung** stellen\n- Beton", { contentType: "markdown" });
    expect(e.getHTML()).toMatch(/^<h3>Ablauf<\/h3><ul><li><p><strong>Verkleidung<\/strong> stellen<\/p><\/li><li><p>Beton<\/p><\/li><\/ul>/);
  });
});
