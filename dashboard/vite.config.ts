/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const gateway = process.env.MICROPRICE_GATEWAY ?? "http://127.0.0.1:8765";

export default defineConfig({
  // Hosted demo builds may live under a sub-path, such as /Microprice/ on GitHub Pages.
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": gateway,
      "/live": { target: gateway.replace("http", "ws"), ws: true },
    },
  },
  build: { sourcemap: false },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
