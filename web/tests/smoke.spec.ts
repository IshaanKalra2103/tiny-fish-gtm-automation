import { test, expect } from "@playwright/test";

test("demo flow", async ({ page }) => {
  await page.goto("/demo");
  await page.getByRole("link", { name: /Bean & Brick Coffee/ }).click();
  await expect(page).toHaveURL(/\/b\/demo-coffee/);
  // The owner page is a deck of cards; "See all" shows every job at once.
  await page.getByRole("button", { name: "See all" }).click();
  expect(await page.getByTestId("need-item").count()).toBeGreaterThanOrEqual(3);
  await page.getByTestId("need-item").first().click();
  await page.getByRole("button", { name: "Compare tools" }).click();
  const cards = page.getByTestId("tool-card");
  expect(await cards.count()).toBeGreaterThanOrEqual(2);
  const n = await cards.count();
  for (let i = 0; i < n; i++) await expect(cards.nth(i).getByTestId("trust-badge")).toBeVisible();
  await expect(page.getByText(/Simulated owner test: \d+\/10 \(simulated\)/).first()).toBeVisible();
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

// Live-page behavior against a mocked API: the offline build points at http://127.0.0.1:9.
const API = "http://127.0.0.1:9";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type", "access-control-allow-methods": "GET,POST" };
const BUNDLE = { owner_id: "o_test000001", source: "x", profile: null, needs: null, compares: {}, previews: {}, setups: {}, approvals: [], messages: [] };
const BUSY_ALL = "We're busy right now. Try again in a few minutes.";

type Handler = (method: string, path: string) => { status?: number; body: unknown; delayMs?: number } | undefined;
async function mockApi(page: import("@playwright/test").Page, handler: Handler) {
  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const url = new URL(req.url());
    const r = handler(req.method(), url.pathname + url.search);
    if (!r) return route.abort();
    if (r.delayMs) await new Promise((ok) => setTimeout(ok, r.delayMs));
    return route.fulfill({ status: r.status ?? 200, headers: CORS, contentType: "application/json", body: JSON.stringify(r.body) });
  });
}

test("owner page follows the active turn, not the old ?turn=", async ({ page }) => {
  let polls = 0;
  await mockApi(page, (m, p) => {
    if (p === "/api/health") return { body: { ok: true } };
    if (p === "/api/owners/o_test000001") return { body: { ...BUNDLE, active_turn: "t_aaaaaaaaaaaa" } };
    if (p.startsWith("/api/turns/t_bbbbbbbbbbbb/poll")) return { body: { events: [{ type: "done", reply: "OLD REPLY" }], next: 1, done: true } };
    if (p.startsWith("/api/turns/t_aaaaaaaaaaaa/poll")) {
      polls += 1;
      if (polls === 1) return { status: 502, body: {} }; // one tunnel hiccup is not "lost the connection"
      return { body: { events: [{ type: "status", text: "Checking our vetted tools" }], next: 1, done: false } };
    }
  });
  await page.goto("/b/o_test000001?turn=t_bbbbbbbbbbbb");
  await expect(page.getByText("Checking our vetted tools")).toBeVisible();
  await expect(page.getByText("OLD REPLY")).toHaveCount(0);
  await expect(page.getByText(/lost the connection/)).toHaveCount(0);
});

test("chat shows the API's 429 detail", async ({ page }) => {
  await mockApi(page, (m, p) => {
    if (p === "/api/health") return { body: { ok: true } };
    if (p === "/api/owners/o_test000001") return { body: { ...BUNDLE, active_turn: null } };
    if (m === "POST" && p === "/api/owners/o_test000001/turns") return { status: 429, body: { detail: BUSY_ALL } };
  });
  await page.goto("/b/o_test000001");
  await page.getByRole("button", { name: "Ask us a question" }).click();
  await page.getByLabel("Ask a follow-up").fill("hello");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("alert").filter({ hasText: BUSY_ALL })).toBeVisible();
});

test("intake shows a 429 detail and retries instead of going to the demo", async ({ page }) => {
  let owners = 0;
  const capped = "You've started a lot of businesses today. Open one from earlier, or try the examples.";
  await mockApi(page, (m, p) => {
    if (p === "/api/health") return { body: { ok: true } };
    if (m === "POST" && p === "/api/owners") { owners += 1; return { status: 429, body: { detail: capped } }; }
  });
  await page.goto("/");
  await page.getByLabel(/Paste your website/).fill("a coffee shop in Baltimore");
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect(page.getByText(capped)).toBeVisible();
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect.poll(() => owners).toBe(2);
  await expect(page).not.toHaveURL(/\/demo/);
});

test("intake reuses the new owner when the first turn is refused", async ({ page }) => {
  let owners = 0, turns = 0;
  await mockApi(page, (m, p) => {
    if (p === "/api/health") return { body: { ok: true } };
    if (m === "POST" && p === "/api/owners") { owners += 1; return { body: { owner_id: "o_test000001" } }; }
    if (m === "POST" && p === "/api/owners/o_test000001/turns") { turns += 1; return { status: 429, body: { detail: BUSY_ALL } }; }
  });
  await page.goto("/");
  await page.getByLabel(/Paste your website/).fill("a coffee shop in Baltimore");
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect(page.getByText(BUSY_ALL)).toBeVisible();
  await page.getByRole("button", { name: "Show me what AI can do" }).click();
  await expect.poll(() => turns).toBe(2);
  expect(owners).toBe(1);
});

test("a slow health check (3 s) does not mark the site offline", async ({ page }) => {
  await mockApi(page, (m, p) => {
    if (p === "/api/health") return { body: { ok: true }, delayMs: 3000 };
  });
  await page.goto("/");
  await page.waitForTimeout(4500);
  await expect(page.getByText(/Our live agent is resting/)).toHaveCount(0);
});
