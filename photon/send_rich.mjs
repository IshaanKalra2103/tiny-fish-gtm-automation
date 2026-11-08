// Native iMessage UI from the project's Photon line: text (optionally with a screen effect), rich link
// previews, inline media (video/image) and native polls. Used by harness/chat_relay.py so the founder's
// thread is the campaign dashboard.
//
//   node --env-file=photon/.env photon/send_rich.mjs --to +15551234567 \
//     [--text "..."] [--effect confetti|fireworks|spotlight|gentle] [--link https://...] \
//     [--file clip.mp4 ...] [--poll "Question?" --option "A" --option "B" ...] [--card card.json]
//
// --card: an iMessage app-card bubble (the balloon Apple Polls uses). card.json holds the layout:
//   {"caption", "subcaption", "trailingCaption", "trailingSubcaption", "imageTitle", "imageSubtitle",
//    "summary", "image": "/path/to.jpg", "url": "https://..."}
//
// Sends the card first, then text, link, files, poll. Send-only (Paperclip's Photon receiver owns the inbound stream). Prints one JSON line.
import { existsSync, readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { Spectrum, attachment, poll, richlink, text } from "spectrum-ts";
import { customizedMiniApp, effect, imessage } from "@spectrum-ts/imessage";

const EFFECTS = {
  confetti: "com.apple.messages.effect.CKConfettiEffect",
  fireworks: "com.apple.messages.effect.CKFireworksEffect",
  spotlight: "com.apple.messages.effect.CKSpotlightEffect",
  gentle: "com.apple.MobileSMS.expressivesend.gentle",
};
const { values } = parseArgs({
  options: {
    to: { type: "string" },
    text: { type: "string" },
    effect: { type: "string" },
    link: { type: "string" },
    file: { type: "string", multiple: true, default: [] },
    poll: { type: "string" },
    option: { type: "string", multiple: true, default: [] },
    card: { type: "string", multiple: true, default: [] },
  },
});
const fail = (error) => {
  console.log(JSON.stringify({ ok: false, error }));
  process.exit(1);
};
if (!values.to || !/^\+\d{8,15}$/.test(values.to)) fail("--to must be an E.164 number");
if (values.effect && !EFFECTS[values.effect]) fail(`unknown --effect ${values.effect}`);
if (values.poll && values.option.length < 2) fail("--poll needs at least two --option");
const missing = values.file.filter((p) => !existsSync(p));
if (missing.length) fail(`file not found: ${missing.join(", ")}`);

const app = await Spectrum({
  projectId: process.env.PROJECT_ID,
  projectSecret: process.env.PROJECT_SECRET,
  providers: [imessage.config()],
  options: { logLevel: "warn" },
});
const sent = [];
try {
  const im = imessage(app);
  const dm = await im.space.create(await im.user(values.to));
  for (const c of values.card) {
    const spec = JSON.parse(readFileSync(c, "utf8"));
    const { image, url, ...layout } = spec;
    if (image) layout.image = new Uint8Array(readFileSync(image));
    await dm.send(customizedMiniApp({
      // Photon only allows its own Spectrum extension on this endpoint (same identity its `app` content uses).
      appName: "Spectrum", teamId: "P8XT6232SL", extensionBundleId: "codes.photon.Spectrum.MessagesExtension",
      appStoreId: 6777616651,
      url: url || "https://tinyfish.ai", layout,
    }));
    sent.push("card");
  }
  if (values.text) {
    await dm.send(values.effect ? effect(text(values.text), EFFECTS[values.effect]) : text(values.text));
    sent.push(values.effect ? `text+${values.effect}` : "text");
  }
  if (values.link) { await dm.send(richlink(values.link)); sent.push("richlink"); }
  for (const f of values.file) { await dm.send(attachment(f)); sent.push("file"); }
  if (values.poll) { await dm.send(poll(values.poll, ...values.option)); sent.push("poll"); }
  console.log(JSON.stringify({ ok: true, sent }));
} catch (e) {
  console.log(JSON.stringify({ ok: false, sent, error: e instanceof Error ? e.message : String(e) }));
  process.exitCode = 1;
} finally {
  await app.stop();
}
