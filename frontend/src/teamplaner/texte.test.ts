// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { kurzTag, langDatum, personentageText } from "./logik";
import { t } from "./texte";

afterEach(() => {
  document.documentElement.lang = "";
});

describe("Übersetzung (Vollständigkeit der Schlüssel prüft TypeScript)", () => {
  it("nutzt Deutsch als Vorgabe und setzt Werte ein", () => {
    expect(t("woche", { n: 1 })).toBe("1 Woche");
    expect(kurzTag("2026-10-21")).toBe("Mi");
    expect(langDatum("2026-10-21")).toBe("21.10.2026");
  });

  it("folgt dem lang-Attribut der Seite", () => {
    document.documentElement.lang = "en";
    expect(t("tage_doppelt", { n: 2 })).toBe("2 days double-booked");
    expect(kurzTag("2026-10-21")).toBe("Wed");
    expect(langDatum("2026-10-21")).toBe("21/10/2026");
    expect(personentageText(1, null)).toBe("1 day");
  });

  it("fällt bei unbekannter Sprache auf Deutsch zurück", () => {
    document.documentElement.lang = "fr";
    expect(t("heute")).toBe("Heute");
  });
});
