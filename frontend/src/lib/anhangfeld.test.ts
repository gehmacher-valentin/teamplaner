import { describe, expect, it } from "vitest";
import { endung, groesse, zuGross } from "./anhangfeld";

describe("Anhang-Kachel vor dem Hochladen", () => {
  it("Endung und Größe wie auf dem Server (dateiendung, dateigroesse)", () => {
    expect(endung("Zeichnung.PDF")).toBe("PDF");
    expect(endung("archiv.tar.gz")).toBe("GZ");
    expect(endung("modell.sldprt2")).toBe("SLDPR");
    expect(endung("README")).toBe("");
    expect(groesse(0)).toBe("0 B");
    expect(groesse(1023)).toBe("1023 B");
    expect(groesse(48200)).toBe("47,1 KB");
    expect(groesse(3 * 1024 * 1024)).toBe("3,0 MB");
  });

  it("zu groß erst über der Grenze, ohne Grenze nie", () => {
    expect(zuGross({ size: 1024 * 1024 }, 1)).toBe(false);
    expect(zuGross({ size: 1024 * 1024 + 1 }, 1)).toBe(true);
    expect(zuGross({ size: 10 ** 9 }, 0)).toBe(false);
  });
});
