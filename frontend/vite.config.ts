import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Ausgabe nach static/dist; Django liefert die Dateien über {% static %} aus.
// Einstiegspunkte haben feste Namen, Hashes vergibt Django (ManifestStaticFilesStorage).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: "/static/dist/",
  build: {
    outDir: resolve(__dirname, "../static/dist"),
    emptyOutDir: true,
    sourcemap: mode === "development",
    minify: mode !== "development",
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/main.ts"),
        teamplaner: resolve(__dirname, "src/teamplaner/index.tsx"),
        editor: resolve(__dirname, "src/editor/index.ts"),
        gantt: resolve(__dirname, "src/gantt/index.tsx"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: (info) =>
          info.names?.some((n) => n.endsWith(".css")) ? "[name][extname]" : "assets/[name]-[hash][extname]",
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
}));
