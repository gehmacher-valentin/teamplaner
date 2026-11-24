// @vitest-environment jsdom
import { Editor } from "@tiptap/core";
import { describe, expect, test } from "vitest";
import { erweiterungen } from "./erweiterungen";
import { imZitat, zitatUmschalten } from "./zitat";

const notiz = (text: string) => new Editor({ content: text, contentType: "markdown", extensions: erweiterungen(true, "") });
const beschreibung = (html: string) => new Editor({ content: html, contentType: "html", extensions: erweiterungen(false, "") });

// Der Editor hängt nach Blöcken einen leeren Absatz an, damit man darunter weiterschreiben kann
const html = (e: Editor) => e.getHTML().replace(/<p><\/p>$/, "");

describe("Zitat-Knopf", () => {
  test("setzt und entfernt ein Zitat, in Notizen als Markdown", () => {
    const e = notiz("Text");
    zitatUmschalten(e);
    expect(e.getMarkdown().trim()).toBe("> Text");
    expect(imZitat(e)).toBe(true);
    zitatUmschalten(e);
    expect(e.getMarkdown().trim()).toBe("Text");
  });

  test("mehrere markierte Absätze ergeben ein Zitat und wieder normalen Text", () => {
    const e = beschreibung("<p>eins</p><p>zwei</p><p>drei</p>");
    e.commands.selectAll();
    zitatUmschalten(e);
    expect(html(e)).toBe("<blockquote><p>eins</p><p>zwei</p><p>drei</p></blockquote>");
    zitatUmschalten(e);
    expect(html(e)).toBe("<p>eins</p><p>zwei</p><p>drei</p>");
  });

  test("gemischte Auswahl wird ein einziges Zitat, ohne Verschachtelung", () => {
    const e = beschreibung("<p>eins</p><blockquote><p>zwei</p></blockquote><p>drei</p>");
    e.commands.selectAll();
    zitatUmschalten(e);
    expect(html(e)).toBe("<blockquote><p>eins</p><p>zwei</p><p>drei</p></blockquote>");
  });

  test("getrennte und verschachtelte Zitate lassen sich gemeinsam entfernen", () => {
    const e = beschreibung("<blockquote><p>eins</p><blockquote><p>zwei</p></blockquote></blockquote><blockquote><p>drei</p></blockquote>");
    e.commands.selectAll();
    zitatUmschalten(e);
    expect(html(e)).toBe("<p>eins</p><p>zwei</p><p>drei</p>");
  });

  test("Listen kommen als Ganzes hinein und heraus", () => {
    const e = beschreibung("<ul><li><p>eins</p></li><li><p>zwei</p></li></ul>");
    e.commands.setTextSelection(4);
    zitatUmschalten(e);
    expect(html(e)).toBe("<blockquote><ul><li><p>eins</p></li><li><p>zwei</p></li></ul></blockquote>");
    zitatUmschalten(e);
    expect(html(e)).toBe("<ul><li><p>eins</p></li><li><p>zwei</p></li></ul>");
  });
});
