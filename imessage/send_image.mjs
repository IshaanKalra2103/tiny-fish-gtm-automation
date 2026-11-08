// Send images (and optional text) from the project's Photon iMessage line into a user's DM.
// Used by the harness to make the iMessage thread the campaign dashboard (stage cards, thumbnails, clips).
//
//   node --env-file=photon/.env photon/send_image.mjs --to +15551234567 --image card.png [--image b.png] [--text "..."]
//
// Plain ESM (no tsx) so it runs under the harness container's node too. Send-only: it never reads the inbound
// stream, and Paperclip's Photon receiver replays from its own checkpoint, so the two don't compete.
// Prints one JSON line; exits 1 on failure.
import { existsSync } from "node:fs";
import { parseArgs } from "node:util";
import { Spectrum, attachment } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

const { values } = parseArgs({
  options: {
    to: { type: "string" },
    image: { type: "string", multiple: true, default: [] },
    text: { type: "string" },
  },
});
const fail = (error) => {
  console.log(JSON.stringify({ ok: false, error }));
  process.exit(1);
};
if (!values.to || !/^\+\d{8,15}$/.test(values.to)) fail("--to must be an E.164 number like +15551234567");
const missing = values.image.filter((p) => !/^https?:\/\//.test(p) && !existsSync(p));
if (missing.length) fail(`image not found: ${missing.join(", ")}`);
if (!values.image.length && !values.text) fail("nothing to send: pass --image and/or --text");

const app = await Spectrum({
  projectId: process.env.PROJECT_ID,
  projectSecret: process.env.PROJECT_SECRET,
  providers: [imessage.config()],
  options: { logLevel: "warn" },
});
try {
  const im = imessage(app);
  const dm = await im.space.create(await im.user(values.to));
  if (values.text) await dm.send(values.text);
  for (const img of values.image) await dm.send(attachment(/^https?:\/\//.test(img) ? new URL(img) : img));
  console.log(JSON.stringify({ ok: true, to: values.to.replace(/\d(?=\d{2})/g, "•"), images: values.image.length,
                               text: Boolean(values.text) }));
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: e instanceof Error ? e.message : String(e) }));
  process.exitCode = 1;
} finally {
  await app.stop();
}
