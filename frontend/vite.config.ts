import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the two heaviest vendor libraries into their own cacheable
        // chunks. Pages that use them are React.lazy()'d, so the chunks are
        // fetched only when the route opens. Everything else in
        // node_modules shares one "vendor" chunk.
        manualChunks(id: string) {
          if (id.includes("plotly.js-dist-min")) return "plotly";
          if (id.includes("@xyflow")) return "xyflow";
          if (id.includes("node_modules")) return "vendor";
        },
      },
    },
  },
});