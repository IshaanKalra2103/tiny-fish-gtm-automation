// Raw-CDP spike: connect to a TinyFish Browser session, capture vertical screenshots while scrolling.
import { writeFileSync, mkdirSync } from "node:fs";
const [cdpUrl, outDir] = process.argv.slice(2); // argv: cdpUrl outDir url shots
mkdirSync(outDir, { recursive: true });
const ws = new WebSocket(cdpUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const msgId = ++id; pending.set(msgId, { res, rej });
  ws.send(JSON.stringify({ id: msgId, method, params, ...(sessionId && { sessionId }) }));
});
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } };
ws.onopen = async () => {
  try {
    const t0 = Date.now();
    const { targetInfos } = await send("Target.getTargets");
    const page = targetInfos.find((t) => t.type === "page");
    console.log("page target:", page?.url);
    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
    await send("Emulation.setDeviceMetricsOverride", { width: 540, height: 960, deviceScaleFactor: 2, mobile: true }, sessionId);
    await send("Page.navigate", { url: process.argv[4] }, sessionId);
    await new Promise((r) => setTimeout(r, 6000));
    for (let i = 0; i < Number(process.argv[5] || 4); i++) {
      const { data } = await send("Page.captureScreenshot", { format: "jpeg", quality: 85 }, sessionId);
      writeFileSync(`${outDir}/shot_${i}.jpg`, Buffer.from(data, "base64"));
      await send("Runtime.evaluate", { expression: "window.scrollBy(0, 900)" }, sessionId);
      await new Promise((r) => setTimeout(r, 1500));
    }
    const { result } = await send("Runtime.evaluate", { expression: "document.title + ' | ' + document.querySelector('h1')?.innerText" }, sessionId);
    console.log("title/h1:", result.value, `| ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  } catch (err) { console.error("ERR", err.message); }
  ws.close();
};
ws.onerror = (e) => { console.error("WS error", e.message); process.exit(1); };
