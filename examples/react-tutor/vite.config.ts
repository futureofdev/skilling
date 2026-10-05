import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss(), react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          markdown: ["react-markdown", "remark-gfm"],
          chat: ["ai", "@ai-sdk/react"],
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"] },
});
