import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
// Connectivity smoke test only. In production, iMessage is handled by the harness:
// Paperclip's native imessage-photon channel routes each conversation to a harness agent
// (see connect_paperclip.py). Don't run this while that channel is connected, or both
// consumers will reply.
// Docs: https://photon.codes/docs/spectrum-ts
const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [
    // imessage
    imessage.config(),
  ],
});

// `app.messages` is an async iterable. Each tick yields a `space` (the
// conversation) and an inbound `message`. Reply by awaiting `space.send(...)`.
for await (const [space, message] of app.messages) {
  console.log(`[in] ${message.platform} ${message.content.type}`);
  if (message.content.type === "text") {
    await space.send(`echo: ${message.content.text}`);
    console.log(`[out] echoed to ${message.platform}`);
  }
}
