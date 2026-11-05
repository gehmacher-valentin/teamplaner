import { describe, expect, it } from "vitest";
import { restzeit } from "./sitzungsfrist";

describe("Restzeit der Admin-Sitzung", () => {
  it("zeigt Minuten, in den letzten fünf Minuten Sekunden", () => {
    expect(restzeit(3600)).toBe("60 min");
    expect(restzeit(3599)).toBe("60 min");
    expect(restzeit(301)).toBe("6 min");
    expect(restzeit(300)).toBe("5:00");
    expect(restzeit(65)).toBe("1:05");
    expect(restzeit(0.4)).toBe("0:00");
    expect(restzeit(-20)).toBe("0:00");
  });
});
