import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
    headers: {
      // Allow new Function() for the Excel formula engine
      "Content-Security-Policy": "script-src 'self' 'unsafe-eval' 'unsafe-inline'; default-src 'self' 'unsafe-inline' ws: wss: http: https:",
    },
  },
});
