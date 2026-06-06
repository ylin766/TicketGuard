import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Forward API calls to the backend dev server when available.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    // Use jsdom to simulate a browser environment in tests.
    environment: "jsdom",
    // Run the setup file before each test file.
    setupFiles: ["./src/test/setup.ts"],
    // Allow vitest globals (describe, it, expect) without explicit imports.
    globals: true,
  },
});
