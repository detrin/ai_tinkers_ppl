import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Python backend runs on 8000. In dev, Vite proxies both the REST API and
// the WebSocket there, so the browser sees a single origin and CORS never
// enters the picture.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // Relative asset paths, so the build works both at the web root and under
  // the /ui/ prefix the Python backend serves it from.
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
