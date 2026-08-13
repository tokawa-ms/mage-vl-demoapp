/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    pool: "threads",
    maxWorkers: 1,
  },
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": "http://backend:8000",
      "/healthz": "http://backend:8000",
      "/readyz": "http://backend:8000",
    },
  },
});
