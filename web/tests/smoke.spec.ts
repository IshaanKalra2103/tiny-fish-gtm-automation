import { test, expect } from "@playwright/test";

test("demo flow", async ({ page }) => {
  await page.goto("/demo");
  await page.getByRole("link", { name: /Bean & Brick Coffee/ }).click();
  await expect(page).toHaveURL(/\/b\/demo-coffee/);
  expect(await page.getByTestId("need-item").count()).toBeGreaterThanOrEqual(3);
  const cards = page.getByTestId("tool-card");
  expect(await cards.count()).toBeGreaterThanOrEqual(2);
  const n = await cards.count();
  for (let i = 0; i < n; i++) await expect(cards.nth(i).getByTestId("trust-badge")).toBeVisible();
  await expect(page.getByText("Simulated owner test: 8/10 (simulated)").first()).toBeVisible();
  await expect(page.locator("video").first()).toBeAttached();
});

test("offline intake", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByText("Our live agent is resting right now. You can still explore five example businesses and the full tool catalog."),
  ).toBeVisible();
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect(page).toHaveURL(/\/demo/);
});

test("catalog filters", async ({ page }) => {
  await page.goto("/catalog");
  await page.getByLabel("Business type").selectOption({ label: "Coffee shop" });
  await page.getByLabel("Free plan only").check();
  const cards = page.getByTestId("tool-card");
  await expect(cards.first()).toBeVisible();
  const n = await cards.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) await expect(cards.nth(i).getByTestId("price")).toHaveText("Free plan");
});
