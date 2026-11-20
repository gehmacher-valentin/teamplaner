// @vitest-environment jsdom
import { Editor } from "@tiptap/core";
import { describe, expect, it } from "vitest";
import { erweiterungen } from "./erweiterungen";

function editor(markdown: boolean, inhalt: string) {
  return new Editor({
    element: document.createElement("div"),
    extensions: erweiterungen(markdown, ""),
    content: inhalt,
    contentType: markdown ? "markdown" : "html",
  });
}

describe("Schriftfarbe und Marker", () => {
  it("Beschreibung (HTML): setzen, lesen und entfernen", () => {
    const e = editor(false, "<p>Achtung wichtig</p>");
    e.commands.setTextSelection({ from: 1, to: 8 });
    e.commands.schriftfarbeSetzen("rot");
    e.commands.setTextSelection({ from: 9, to: 16 });
    e.commands.markerSetzen("gelb");
    expect(e.getHTML()).toBe('<p><span data-farbe="rot">Achtung</span> <mark data-farbe="gelb">wichtig</mark></p>');
    e.commands.setTextSelection({ from: 2, to: 2 });
    e.commands.schriftfarbeSetzen(null);
    expect(e.getHTML()).toBe('<p>Achtung <mark data-farbe="gelb">wichtig</mark></p>');
  });

  it("unbekannte Farben und Inline-Styles werden nicht übernommen", () => {
    const e = editor(false, '<p><span data-farbe="pink" style="color:red">a</span><mark style="x">b</mark></p>');
    expect(e.getHTML()).toBe("<p>ab</p>");
  });

  it("Notiz (Markdown): als HTML im Text, nach dem Laden wieder da", () => {
    const e = editor(true, "Termin fix und offen");
    e.commands.setTextSelection({ from: 8, to: 11 });
    e.commands.schriftfarbeSetzen("gruen");
    e.commands.setTextSelection({ from: 16, to: 21 });
    e.commands.markerSetzen("rosa");
    const md = e.getMarkdown();
    expect(md).toBe('Termin <span data-farbe="gruen">fix</span> und <mark data-farbe="rosa">offen</mark>');
    const neu = editor(true, md);
    expect(neu.getHTML()).toBe('<p>Termin <span data-farbe="gruen">fix</span> und <mark data-farbe="rosa">offen</mark></p>');
  });
});
