import { defineConfig } from "@playwright/test";

// Production check: the deployed site against the live agent behind the tunnel. Costs one real agent turn.
export default defineConfig({
  testDir: "./tests",
  testMatch: /prod\.spec\.ts/,
  timeout: 600_000,
  reporter: "list",
  use: { baseURL: process.env.PROD_URL ?? "https://mainstreet-ai-five.vercel.app", headless: true },
});
