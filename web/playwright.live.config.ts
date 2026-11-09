import { defineConfig } from "@playwright/test";

// Live contract check: real API (fake agent runner, temp workspaces) + web built against it.
const tmp = process.env.LIVE_TMP ?? "/tmp/ms-live";
export default defineConfig({
  testDir: "./tests",
  testMatch: /live\.spec\.ts/,
  timeout: 60_000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3102" },
  webServer: [
    {
      command: `cd .. && MS_RUNNER=fake MS_API_PORT=8788 MS_WORKSPACES=${tmp}/ws MS_BUDGET_DIR=${tmp}/budget MS_WEB_ORIGINS=http://127.0.0.1:3102 MS_WEB_URL=http://127.0.0.1:3102 uv run msapi`,
      url: "http://127.0.0.1:8788/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "NEXT_PUBLIC_AGENT_API_URL=http://127.0.0.1:8788 pnpm build && pnpm start -p 3102",
      url: "http://127.0.0.1:3102",
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
