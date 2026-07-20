import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Matches inspect_ai conventions: stable filenames, base "", dev proxy to backend
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    minify: false,
    sourcemap: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/index.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name].[ext]",
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:7576",
    },
  },
});
