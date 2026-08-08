import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 30000,
  use: { baseURL: process.env.ROOST_E2E_BASE_URL || "http://localhost:8199" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
