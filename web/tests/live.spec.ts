import { test, expect } from "@playwright/test";

test("live intake: owner page streams the agent reply", async ({ page, request }) => {
  const health = await (await request.get("http://127.0.0.1:8788/api/health")).json();
  expect(health.ok).toBe(true);
  await page.goto("/");
  await page.getByLabel(/Paste your website/).fill("A two-chair barber shop in Hyattsville, MD");
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect(page).toHaveURL(/\/b\/o_[0-9a-f]{10}/);
  await expect(page.getByText("This is the offline test agent.").first()).toBeVisible({ timeout: 20_000 });
});
