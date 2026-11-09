import { test, expect } from "@playwright/test";

test("production intake: a real agent turn reaches the owner page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/offline/i)).toHaveCount(0);
  await page.getByPlaceholder(/HVAC company/).fill(process.env.BIZ_URL ?? "https://mainstreet-demo-sites.vercel.app/diner/");
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect(page).toHaveURL(/\/b\/o_[0-9a-f]{10}/);
  const reply = page.locator("li", { hasText: "MainStreet:" }).first();
  await expect(reply).toBeVisible({ timeout: 540_000 });
  console.log("OWNER", page.url());
  console.log("REPLY", (await reply.innerText()).slice(0, 400));
  await page.screenshot({ path: process.env.SHOT ?? "test-results/prod.png", fullPage: true });
});
