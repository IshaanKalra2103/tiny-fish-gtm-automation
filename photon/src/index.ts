import { Spectrum, type Message, type Space } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
import { reply, type Turn } from "./llm.ts";
// Spectrum bridges a single agent loop to many messaging interfaces.
// Each provider in `providers` adds an interface (terminal TUI, iMessage, …).
// Docs: https://photon.codes/docs/spectrum-ts
const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [
    // imessage
    imessage.config(),
  ],
});

const MAX_TURNS = 30;
const histories = new Map<string, Turn[]>();
// Messages within one conversation are handled in order; conversations run in parallel.
const queues = new Map<string, Promise<void>>();

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function handle(space: Space, message: Message) {
  if (message.content.type !== "text") return;

  const history = histories.get(space.id) ?? [];
  history.push({ role: "user", content: message.content.text });

  await space.read(message);
  await space.startTyping();
  try {
    const texts = await reply(history.slice(-MAX_TURNS));
    for (const [i, text] of texts.entries()) {
      if (i > 0) {
        await space.startTyping();
        await sleep(Math.min(2500, 40 * text.length));
      }
      await space.send(text);
    }
    history.push({ role: "assistant", content: texts.join("\n\n") });
    console.log(`[out] ${texts.length} text(s) to ${message.platform}`);
  } catch (err) {
    console.error(`[err] reply failed: ${err instanceof Error ? err.message : String(err)}`);
    await space.send("sorry, having trouble replying right now. try again in a bit");
  } finally {
    await space.stopTyping();
  }
  histories.set(space.id, history.slice(-MAX_TURNS));
}

// `app.messages` is an async iterable. Each tick yields a `space` (the
// conversation) and an inbound `message`.
for await (const [space, message] of app.messages) {
  console.log(`[in] ${message.platform} ${message.content.type}`);
  const next = (queues.get(space.id) ?? Promise.resolve())
    .then(() => handle(space, message))
    .catch((err) => console.error(`[err] ${err instanceof Error ? err.message : String(err)}`));
  queues.set(space.id, next);
}
