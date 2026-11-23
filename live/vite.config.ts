/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 로컬 개발: /api 는 python -m livelab.dev_server (127.0.0.1:8787) 로 넘긴다.
export default defineConfig({
  plugins: [react()],
  server: { port: 5199, proxy: { "/api": "http://127.0.0.1:8787" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
