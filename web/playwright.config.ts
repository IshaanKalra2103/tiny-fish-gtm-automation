import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testIgnore: /live\.spec\.ts/,
  timeout: 30_000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:3101" },
  webServer: {
    command: "NEXT_PUBLIC_AGENT_API_URL=http://127.0.0.1:9 pnpm build && pnpm start -p 3101",
    url: "http://127.0.0.1:3101",
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
