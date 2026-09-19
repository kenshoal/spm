import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "node e2e/support/auth-api.mjs",
      url: "http://127.0.0.1:8104/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "node e2e/support/event-request-api.mjs",
      url: "http://127.0.0.1:8103/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        AUTH_SERVICE_URL: "http://127.0.0.1:8104",
        EVENT_REQUEST_API_URL: "http://127.0.0.1:8103",
      },
    },
  ],
});
