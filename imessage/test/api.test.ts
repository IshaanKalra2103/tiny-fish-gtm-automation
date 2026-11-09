// Drives the relay handler against a real local API with the fake agent. Real fetch, fake send.
// Skipped unless RELAY_TEST_API_URL is set:
//
//   (repo root) MS_RUNNER=fake MS_API_PORT=8788 MS_WORKSPACES=$TMP/ws MS_BUDGET_DIR=$TMP/budget \
//               MS_RELAY_SECRET=test uv run msapi
//   (imessage)  RELAY_TEST_API_URL=http://127.0.0.1:8788 RELAY_TEST_SECRET=test npm test
import assert from "node:assert/strict";
import { randomInt } from "node:crypto";
import { setTimeout as wait } from "node:timers/promises";
import { test } from "node:test";
import { handleMessage, type IncomingLike, type RelayDeps, SORRY } from "../src/relay.ts";

const API = process.env.RELAY_TEST_API_URL;
const SECRET = process.env.RELAY_TEST_SECRET ?? "test";
const skip = API ? false : "set RELAY_TEST_API_URL to run against a local API";

const text = (senderId: string, body: string): IncomingLike => ({
  direction: "inbound",
  sender: { id: senderId },
  content: { type: "text", text: body },
});
const newSender = () => `+1410${randomInt(1_000_000, 10_000_000)}`;

function deps(sent: string[], over: Partial<RelayDeps> = {}): RelayDeps {
  return {
    apiUrl: API!,
    secret: SECRET,
    fetch: (url, init) => fetch(url, init),
    send: async (t) => void sent.push(t),
    sleep: async () => {},
    log: () => {},
    ...over,
  };
}

test("a text gets the agent's replies and then the owner's page link", { skip }, async () => {
  const sent: string[] = [];
  const out = await handleMessage(text(newSender(), "I run a hair salon in Westminster MD, what AI could help me?"), deps(sent));
  assert.equal(out, "replied");
  assert.ok(sent.length >= 2 && sent.length <= 4, `1-3 replies plus a link, got ${sent.length}`);
  assert.match(sent.at(-1)!, /\/b\/o_[0-9a-z]+$/);
  assert.ok(!sent.slice(0, -1).some((t) => t.includes("/b/o_")), "replies don't repeat the link");
});

test("the same sender gets the same page; a second text inside 5 s gets the 429 detail", { skip }, async () => {
  const who = newSender();
  const first: string[] = [];
  assert.equal(await handleMessage(text(who, "hello"), deps(first)), "replied");
  const second: string[] = [];
  assert.equal(await handleMessage(text(who, "hello again"), deps(second)), "rate_limited");
  assert.deepEqual(second, ["Give me a few seconds between texts."]);
  await wait(5_200); // the API's min gap between texts
  const third: string[] = [];
  assert.equal(await handleMessage(text(who, "and again"), deps(third)), "replied");
  assert.equal(third.at(-1), first.at(-1), "same sender, same page link");
  const other: string[] = [];
  await handleMessage(text(newSender(), "hello"), deps(other));
  assert.notEqual(other.at(-1), first.at(-1), "another sender gets another page");
});

test("a wrong relay secret gets the sorry text", { skip }, async () => {
  const sent: string[] = [];
  assert.equal(await handleMessage(text(newSender(), "hi"), deps(sent, { secret: "wrong" })), "error");
  assert.deepEqual(sent, [SORRY]);
});

test("an API that is down gets the sorry text", { skip }, async () => {
  const sent: string[] = [];
  const out = await handleMessage(text(newSender(), "hi"), deps(sent, { apiUrl: "http://127.0.0.1:9" }));
  assert.equal(out, "error");
  assert.deepEqual(sent, [SORRY]);
});
