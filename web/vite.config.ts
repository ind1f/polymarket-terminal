import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/ws": { target: "http://127.0.0.1:8000", ws: true },
      "/api/rankings": { target: "http://127.0.0.1:8000" },
      "/api/gamma": {
        target: "https://gamma-api.polymarket.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/gamma/, ""),
      },
      "/api/clob": {
        target: "https://clob.polymarket.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/clob/, ""),
      },
    },
  },
});
