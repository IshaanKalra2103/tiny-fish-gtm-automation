// Headless screen recordings of the MainStreet AI site for the demo film.
// usage: node video/tools/rec_screens.mjs <take> [--phone] [--base URL] [--site URL] [--out DIR]
// takes: deck, helper, catalog, intake, approval, setup
// Desktop: 1440x810 CSS at DPR 4/3 -> 1920x1080 video. Phone: 390x844 at DPR 3.
import { createRequire } from "node:module";
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
const { chromium } = createRequire("/Users/ishaankalra/Documents/projects/aisb-hackathon/web/package.json")("@playwright/test");

const args = process.argv.slice(2);
const take = args[0];
const phone = args.includes("--phone");
const base = args.includes("--base") ? args[args.indexOf("--base") + 1] : "https://mainstreet-ai-five.vercel.app";
const API = "http://127.0.0.1:8787";
const BEAN = "o_392fa2d482";
const OUT = args.includes("--out") ? args[args.indexOf("--out") + 1] : "/Users/ishaankalra/Documents/projects/aisb-hackathon/footage/screens/";
mkdirSync(OUT, { recursive: true });

const big = args.includes("--big");
const vp = phone ? { width: 390, height: 844 } : big ? { width: 1152, height: 648 } : { width: 1440, height: 810 };
const dpr = phone ? 3 : big ? 5 / 3 : 4 / 3;
const size = phone ? { width: 1170, height: 2532 } : { width: 1920, height: 1080 };

// A visible cursor with a click pulse (headless recordings have no pointer).
const CURSOR = `
(() => {
  const mk = () => {
    if (document.getElementById("__cur")) return;
    const c = document.createElement("div"); c.id = "__cur";
    c.style.cssText = "position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(17,18,20,.82);border:2.5px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.35);z-index:2147483647;pointer-events:none;transition:transform .12s ease;transform:translate(-100px,-100px)";
    document.documentElement.appendChild(c);
    let x = -100, y = -100;
    addEventListener("mousemove", e => { x = e.clientX; y = e.clientY; c.style.transform = "translate(" + x + "px," + y + "px)"; }, true);
    addEventListener("mousedown", () => { c.style.transform = "translate(" + x + "px," + y + "px) scale(.7)"; }, true);
    addEventListener("mouseup", () => { c.style.transform = "translate(" + x + "px," + y + "px)"; }, true);
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", mk); else mk();
})();`;

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: dpr, isMobile: phone, hasTouch: phone,
  recordVideo: { dir: OUT, size }, colorScheme: "light", reducedMotion: "no-preference" });
await ctx.addInitScript(CURSOR);
const page = await ctx.newPage();
const marks = []; const t0 = Date.now();
const mark = (label) => { marks.push({ t: +((Date.now() - t0) / 1000).toFixed(2), label }); console.log(marks.at(-1)); };
const wait = (ms) => page.waitForTimeout(ms);
let mx = vp.width / 2, my = vp.height / 2;
async function moveTo(loc) {
  await loc.scrollIntoViewIfNeeded();
  const b = await loc.boundingBox();
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y, { steps: 28 }); mx = x; my = y;
  await wait(250);
}
async function click(loc, label) {
  if (phone) { await loc.scrollIntoViewIfNeeded(); mark(label); await loc.tap(); return; }
  await moveTo(loc); mark(label); await page.mouse.down(); await wait(90); await page.mouse.up();
}
const next = async (label) => { mark(label); await page.keyboard.press("ArrowRight"); };
const closeSheet = async () => { await page.keyboard.press("Escape"); await wait(900); };

async function toCard(re, max = 10) {
  for (let i = 0; i < max; i++) {
    if (await page.getByText(re).first().isVisible().catch(() => false)) return true;
    await page.keyboard.press("ArrowRight"); await wait(700);
  }
  return false;
}

try {
  if (take === "deck") {
    await page.goto(`${base}/b/demo-coffee`, { waitUntil: "networkidle" });
    mark("understood card"); await page.mouse.move(mx, my); await wait(4000);
    await next("job 1"); await wait(3500);
    await click(page.getByRole("button", { name: "Compare tools" }).first(), "compare open"); await wait(4500);
    for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 160); await wait(1300); }
    await wait(1500); mark("compare close"); await closeSheet();
    await click(page.getByRole("button", { name: "Why we trust it" }).first(), "trust open"); await wait(3500);
    for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 140); await wait(1700); }
    await wait(1500); mark("trust close"); await closeSheet();
    await click(page.getByRole("button", { name: "Show me", exact: true }).first(), "preview open"); await wait(11000);
    mark("preview close"); await closeSheet();
    await next("job 2"); await wait(2500);
    await next("job 3"); await wait(2500);
    await click(page.getByRole("button", { name: "See all" }).first(), "overview"); await wait(4000);
  } else if (take === "helper") {
    await page.goto(`${base}/b/demo-coffee`, { waitUntil: "networkidle" });
    await toCard(/Prefer a person|local helper/i); mark("helper card"); await wait(5000);
  } else if (take === "catalog") {
    await page.goto(`${base}/catalog`, { waitUntil: "networkidle" });
    mark("catalog top"); await wait(2500);
    for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 260); await wait(500); }
    mark("catalog scrolled"); await wait(1500);
  } else if (take === "intake") {
    const site = args.includes("--site") ? args[args.indexOf("--site") + 1] : "https://www.wivellshvac.com/";
    await page.goto(`${base}/`, { waitUntil: "networkidle" }); await wait(1500);
    const box = page.getByLabel(/Paste your website/);
    await click(box, "focus box"); await page.keyboard.type(site, { delay: 70 }); await wait(800);
    await click(page.getByRole("button", { name: "Show me what AI can do" }), "submit");
    await page.waitForURL(/\/b\/o_/, { timeout: 60_000 }); mark("owner page " + page.url());
    // Wait for the jobs: the deck shows "Job 1 of" once needs exist.
    const jobs = page.getByRole("button", { name: /Show me the \d+ jobs?/ }).first();
    await jobs.waitFor({ state: "visible", timeout: 240_000 }).catch(() => mark("no jobs button"));
    mark("results"); await page.mouse.move(mx, my); await wait(5000);
    await click(jobs, "job 1"); await wait(5000);
    await next("job 2"); await wait(3500);
    await next("job 3"); await wait(3000);
  } else if (take === "approval" || take === "setup") {
    // Same owner, real data. "approval" replays the approval as it stood before Ishaan approved it.
    const real = await (await fetch(`${API}/api/owners/${BEAN}`)).json();
    if (take === "approval") {
      const b = structuredClone(real);
      b.approvals = b.approvals.map((a) => ({ ...a, status: "pending" })); b.setups = {}; b.active_turn = null;
      await page.route(new RegExp(`/api/owners/${BEAN}$`), (r) => r.request().method() === "GET"
        ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) }) : r.continue());
      await page.route(new RegExp(`/api/owners/${BEAN}/approvals/`), (r) =>
        r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
    }
    await page.goto(`${base}/b/${BEAN}`, { waitUntil: "networkidle" }); await wait(1500);
    if (take === "approval") {
      await toCard(/Ready to set up/); mark("approval card"); await wait(4500);
      await click(page.getByRole("button", { name: "Yes, set it up" }), "yes"); await wait(4000);
    } else {
      await toCard(/We need you for one step/); mark("setup record"); await wait(7000);
      await page.mouse.wheel(0, 300); await wait(3000);
    }
  } else if (take === "probe") {
    await page.goto(`${base}/b/demo-coffee`, { waitUntil: "networkidle" }); await wait(1500);
  } else { console.log("unknown take"); }
} catch (e) { mark("ERROR " + e.message.split("\n")[0]); }
await page.screenshot({ path: `${OUT}${take}${phone ? "-phone" : ""}-last.png` });
const vid = page.video(); await ctx.close(); await browser.close();
const src = await vid.path(); const dst = `${OUT}${take}${phone ? "-phone" : ""}.webm`;
renameSync(src, dst); writeFileSync(dst.replace(/\.webm$/, ".marks.json"), JSON.stringify(marks, null, 1));
console.log("saved", dst, ((Date.now() - t0) / 1000).toFixed(1) + "s");
