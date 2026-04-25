import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Repo name; used for GitHub Pages base path.
const REPO_NAME = "igcse-study-agent";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? `/${REPO_NAME}/` : "/",
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2022",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    port: 5173,
    strictPort: false,
  },
}));
