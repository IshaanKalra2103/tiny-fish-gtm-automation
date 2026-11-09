// MainStreet AI iMessage relay: Photon line -> POST /api/imessage -> replies back to the thread.
// All message logic lives in relay.ts; this file only wires Photon to it.
//
//   AGENT_API_URL=http://127.0.0.1:8787 MS_RELAY_SECRET=... npm start
//
// Only one consumer may read the Photon line. Stop any other (e.g. the old gtm-paperclip
// container) first, or both will reply.
// Docs: https://photon.codes/docs/spectrum-ts
import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
import { handleMessage } from "./relay.ts";

const apiUrl = process.env.AGENT_API_URL || "http://127.0.0.1:8787";
const secret = process.env.MS_RELAY_SECRET || undefined;
const projectId = process.env.PROJECT_ID;
const projectSecret = process.env.PROJECT_SECRET;

if (!projectId || !projectSecret) {
  console.error("[relay] PROJECT_ID / PROJECT_SECRET missing. Put them in imessage/.env (from the Photon dashboard).");
  process.exit(1);
}
if (!secret) console.warn("[relay] MS_RELAY_SECRET is not set; the API will reject calls if it has one.");

const app = await Spectrum({
  projectId,
  projectSecret,
  providers: [imessage.config()],
  options: { logLevel: "warn" },
});

let stopping = false;
const shutdown = async (signal: string) => {
  if (stopping) return;
  stopping = true;
  console.log(`[relay] ${signal}, stopping`);
  await app.stop().catch(() => {});
  process.exit(0);
};
process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));

console.log(`[relay] listening, agent API ${apiUrl}`);

// Each message is handled on its own so a slow turn (up to ~280 s) never blocks other senders.
for await (const [space, message] of app.messages) {
  void handleMessage(message, {
    apiUrl,
    secret,
    fetch: (url, init) => fetch(url, init),
    send: (text) => space.send(text),
    typing: (on) => (on ? space.startTyping() : space.stopTyping()),
  }).catch((e) => console.error(`[relay] handler crashed: ${e instanceof Error ? e.name : typeof e}`));
}
console.error("[relay] Photon message stream ended");
process.exit(1);
