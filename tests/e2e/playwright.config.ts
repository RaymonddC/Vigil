import { defineConfig, devices } from "@playwright/test";

/**
 * Vigil E2E Playwright config.
 *
 * Assumes all services are already running (make demo):
 *   - HAPI FHIR at :8080
 *   - FastAPI proxy at :8000
 *   - MCP server at :7001
 *   - A2A agent at :9000
 *   - Next.js at :3000
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: false, // Sequential — click-through order matters
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "junit" : "html",
  timeout: 30_000,

  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    video: "on", // Video-recordable per I1 acceptance criteria
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
