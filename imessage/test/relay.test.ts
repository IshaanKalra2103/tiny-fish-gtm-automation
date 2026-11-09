// Unit tests for the relay handler: fake fetch, send and sleep, no Photon, no network.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { GAP_MS, handleMessage, hashSender, type IncomingLike, type RelayDeps, SORRY } from "../src/relay.ts";

const PHONE = "+14105550123";
const TEXT = "I run a hair salon in Westminster MD, what AI could help me?";
const msg = (over: Partial<IncomingLike> = {}): IncomingLike => ({
  direction: "inbound",
  sender: { id: PHONE },
  content: { type: "text", text: TEXT },
  ...over,
});

type Call = { url: string; init: RequestInit };

function harness(respond: (call: Call) => Response | Promise<Response>, over: Partial<RelayDeps> = {}) {
  const calls: Call[] = [];
  const events: string[] = []; // sends and sleeps, in order
  const logs: string[] = [];
  const deps: RelayDeps = {
    apiUrl: "http://api.test/",
    secret: "s3cret",
    fetch: async (url, init) => {
      const call = { url, init };
      calls.push(call);
      return respond(call);
    },
    send: async (t) => void events.push(`send:${t}`),
    sleep: async (ms) => void events.push(`sleep:${ms}`),
    log: (l) => void logs.push(l),
    ...over,
  };
  return { deps, calls, events, logs };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

test("hashSender is sha256 hex of the sender id", () => {
  assert.equal(hashSender(PHONE), createHash("sha256").update(PHONE).digest("hex"));
  assert.match(hashSender(PHONE), /^[0-9a-f]{64}$/);
});

test("posts {from_hash, text} with the relay secret, then sends replies 3 s apart and the link", async () => {
  const h = harness(() => json(200, { replies: ["one", "two"], link: "https://web.test/b/o_abc" }));
  assert.equal(await handleMessage(msg(), h.deps), "replied");

  assert.equal(h.calls.length, 1);
  const { url, init } = h.calls[0]!;
  assert.equal(url, "http://api.test/api/imessage");
  assert.equal(init.method, "POST");
  const headers = init.headers as Record<string, string>;
  assert.equal(headers["x-relay-secret"], "s3cret");
  assert.equal(headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(init.body as string), { from_hash: hashSender(PHONE), text: TEXT });
  assert.ok(init.signal instanceof AbortSignal, "the call has a timeout signal");

  assert.deepEqual(h.events, [
    "send:one", `sleep:${GAP_MS}`, "send:two", `sleep:${GAP_MS}`, "send:https://web.test/b/o_abc",
  ]);
  assert.equal(GAP_MS, 3000);
});

test("no secret header when no secret is configured", async () => {
  const h = harness(() => json(200, { replies: ["hi"], link: "L" }), { secret: undefined });
  await handleMessage(msg(), h.deps);
  assert.equal((h.calls[0]!.init.headers as Record<string, string>)["x-relay-secret"], undefined);
});

test("keeps at most 3 replies and trims blanks", async () => {
  const h = harness(() => json(200, { replies: ["a", " ", "b", "c", "d"], link: "L" }));
  await handleMessage(msg(), h.deps);
  assert.deepEqual(h.events.filter((e) => e.startsWith("send:")), ["send:a", "send:b", "send:c", "send:L"]);
});

test("a 429 sends its detail text", async () => {
  const h = harness(() => json(429, { detail: "Give me a few seconds between texts." }));
  assert.equal(await handleMessage(msg(), h.deps), "rate_limited");
  assert.deepEqual(h.events, ["send:Give me a few seconds between texts."]);
});

for (const [name, respond] of [
  ["a 500", () => json(500, { detail: "Internal Server Error" })],
  ["a 401 (wrong relay secret)", () => json(401, { detail: "Unknown relay" })],
  ["a 422", () => json(422, { detail: [{ msg: "bad" }] })],
  ["a 429 without detail", () => json(429, {})],
  ["a non-JSON 200", () => new Response("<html>", { status: 200 })],
  ["a 200 with the wrong shape", () => json(200, { reply: "x" })],
  ["a 200 with nothing to send", () => json(200, { replies: [], link: "" })],
  ["a network error", () => Promise.reject(new TypeError("fetch failed"))],
  ["a timeout", () => Promise.reject(new DOMException("The operation timed out.", "TimeoutError"))],
] as const) {
  test(`${name} sends the sorry text`, async () => {
    const h = harness(respond as () => Response | Promise<Response>);
    assert.equal(await handleMessage(msg(), h.deps), "error");
    assert.deepEqual(h.events, [`send:${SORRY}`]);
  });
}

test("ignores our own outgoing messages, non-text, empty text and unknown senders", async () => {
  const cases: IncomingLike[] = [
    msg({ direction: "outbound" }),
    msg({ sender: { id: "+15550000000", kind: "agent" } }),
    msg({ content: { type: "attachment" } }),
    msg({ content: { type: "reaction", text: "love" } }),
    msg({ content: { type: "text", text: "   " } }),
    msg({ sender: undefined }),
    msg({ sender: { id: "" } }),
  ];
  for (const c of cases) {
    const h = harness(() => json(200, { replies: ["x"], link: "L" }));
    assert.equal(await handleMessage(c, h.deps), "ignored");
    assert.equal(h.calls.length, 0);
    assert.deepEqual(h.events, []);
  }
});

test("long texts are cut to the API's 2000 characters", async () => {
  const h = harness(() => json(200, { replies: ["ok"], link: "L" }));
  await handleMessage(msg({ content: { type: "text", text: "x".repeat(5000) } }), h.deps);
  assert.equal(JSON.parse(h.calls[0]!.init.body as string).text.length, 2000);
});

test("logs carry only a hash prefix, never the number or the text", async () => {
  for (const respond of [
    () => json(200, { replies: ["ok"], link: "L" }),
    () => Promise.reject(new Error(`could not reach ${PHONE}: ${TEXT}`)),
  ]) {
    const h = harness(respond as () => Promise<Response>);
    await handleMessage(msg(), h.deps);
    assert.ok(h.logs.length >= 2);
    for (const line of h.logs) {
      assert.ok(!line.includes(PHONE) && !line.includes("4105550123"), `number leaked: ${line}`);
      assert.ok(!line.includes("salon"), `text leaked: ${line}`);
      assert.ok(line.includes(hashSender(PHONE).slice(0, 12)));
    }
  }
});

test("a failing send is logged and does not throw", async () => {
  const h = harness(() => json(200, { replies: ["a", "b"], link: "L" }), {
    send: async () => {
      throw new Error(`send to ${PHONE} failed`);
    },
  });
  assert.equal(await handleMessage(msg(), h.deps), "send_failed");
  assert.ok(h.logs.some((l) => l.startsWith("[send-fail]")));
  assert.ok(h.logs.every((l) => !l.includes(PHONE)));
});

test("typing indicator is on while waiting and off before sending; its errors are ignored", async () => {
  const order: string[] = [];
  const h = harness(
    () => {
      order.push("fetch");
      return json(200, { replies: ["a"], link: "L" });
    },
    {
      typing: async (on) => {
        order.push(on ? "typing-on" : "typing-off");
        throw new Error("UnsupportedError");
      },
      send: async (t) => void order.push(`send:${t}`),
    },
  );
  assert.equal(await handleMessage(msg(), h.deps), "replied");
  assert.deepEqual(order, ["typing-on", "fetch", "typing-off", "send:a", "send:L"]);
});

test("a typing call that never settles does not block the reply", async () => {
  const h = harness(() => json(200, { replies: ["a"], link: "L" }), {
    typing: (on) => (on ? new Promise(() => {}) : Promise.resolve()),
  });
  const started = Date.now();
  assert.equal(await handleMessage(msg(), h.deps), "replied");
  assert.ok(Date.now() - started < 4_500, "gave up on typing after ~3 s");
  assert.deepEqual(h.events, ["send:a", `sleep:${GAP_MS}`, "send:L"]);
});
