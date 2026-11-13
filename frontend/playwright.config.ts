import { defineConfig } from "@playwright/test";

// Browser-Tests der wichtigsten Abläufe (e2e/, docs/entwicklung.md). Die Anwendung startet mit
// eigener Datenbank und frischen Demodaten (werkzeuge/e2e-server.sh). Die Tests ändern Daten und
// laufen deshalb nacheinander in einer festen Reihenfolge.
const PORT = process.env.E2E_PORT ?? "8010";
export const BASIS = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.spec.ts",
  globalSetup: "./e2e/einrichten.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  forbidOnly: !!process.env.CI,
  // In der CI ein zweiter Versuch mit Trace, sonst keine Traces (kosten Laufzeit)
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASIS,
    locale: "de-AT",
    timezoneId: "Europe/Vienna",
    viewport: { width: 1680, height: 1000 },
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: process.env.CI ? "on-first-retry" : "off",
    screenshot: "only-on-failure",
    // Anderer Chromium als der von Playwright mitgebrachte, z. B. ein vorinstallierter
    launchOptions: { executablePath: process.env.E2E_CHROMIUM || undefined },
  },
  webServer: {
    command: "bash ../werkzeuge/e2e-server.sh",
    url: `${BASIS}/gesund/`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { E2E_PORT: PORT },
    stdout: "ignore",
    stderr: "pipe",
  },
});
