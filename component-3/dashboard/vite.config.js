import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard talks to the real Component 3 FastAPI service. In development the
// browser only ever calls same-origin "/api/v1/..." and Vite forwards it, so the
// backend needs no CORS change. Override the target with DASHBOARD_API_TARGET.
const apiTarget = process.env.DASHBOARD_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.js"],
    css: false,
  },
});
