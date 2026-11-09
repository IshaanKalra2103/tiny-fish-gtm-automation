// iMessage relay logic, kept free of Photon so it can be unit tested.
//
// One inbound text becomes one POST /api/imessage {from_hash, text}. The API answers with
// {replies: string[] (<= 3), link}; we send each reply 3 s apart, then the link. A 429 carries
// the text to send the owner in `detail`. Anything else that goes wrong gets SORRY.
//
// Logs carry a short sender hash only: never a phone number, email or message text.
import { createHash } from "node:crypto";

export const SORRY = "Sorry, something broke on our side. Try again in a minute.";
export const GAP_MS = 3_000;
export const TIMEOUT_MS = 300_000; // the API waits up to ~280 s for a turn

/** RELAY_TIMEOUT_MS as a positive number of ms, or undefined to keep TIMEOUT_MS (a cold GCP VM adds ~90 s). */
export function timeoutFromEnv(v: string | undefined): number | undefined {
  const n = Number(v);
  return v && Number.isFinite(n) && n > 0 ? n : undefined;
}
export const MAX_TEXT = 2_000; // the API rejects longer texts with a 422
export const MAX_REPLIES = 3;

/** The parts of a spectrum-ts `Message` the relay reads. */
export interface IncomingLike {
  direction?: string;
  sender?: { id?: string; kind?: string } | undefined;
  content: { type: string; text?: unknown };
}

export type FetchLike = (url: string, init: RequestInit) => Promise<Response>;

export interface RelayDeps {
  apiUrl: string;
  secret?: string | undefined;
  fetch: FetchLike;
  send: (text: string) => Promise<unknown>;
  sleep?: (ms: number) => Promise<void>;
  /** Best effort typing indicator while the agent works; failures are ignored. */
  typing?: (on: boolean) => Promise<unknown>;
  log?: (line: string) => void;
  gapMs?: number;
  timeoutMs?: number;
}

export type Outcome = "ignored" | "replied" | "rate_limited" | "error" | "send_failed";

export const hashSender = (id: string): string => createHash("sha256").update(id, "utf8").digest("hex");

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** The sender id and text to relay, or null for messages we skip (ours, non-text, empty). */
export function relayable(msg: IncomingLike): { senderId: string; text: string } | null {
  if (msg.direction === "outbound" || msg.sender?.kind === "agent") return null;
  if (msg.content?.type !== "text" || typeof msg.content.text !== "string") return null;
  const text = msg.content.text.trim();
  const senderId = (msg.sender?.id ?? "").trim();
  if (!text || !senderId) return null;
  return { senderId, text: text.slice(0, MAX_TEXT) };
}

/** An error whose message is safe to log (no sender id, no text). */
class RelayError extends Error {}

type ApiResult = { kind: "ok"; replies: string[]; link: string } | { kind: "limited"; detail: string };

async function callApi(fromHash: string, text: string, deps: RelayDeps): Promise<ApiResult> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (deps.secret) headers["x-relay-secret"] = deps.secret;
  const res = await deps.fetch(`${deps.apiUrl.replace(/\/+$/, "")}/api/imessage`, {
    method: "POST",
    headers,
    body: JSON.stringify({ from_hash: fromHash, text }),
    signal: AbortSignal.timeout(deps.timeoutMs ?? TIMEOUT_MS),
  });
  const body: any = await res.json().catch(() => null);
  if (res.status === 429) {
    const detail = typeof body?.detail === "string" ? body.detail.trim() : "";
    if (detail) return { kind: "limited", detail };
    throw new RelayError("http 429 without detail");
  }
  if (!res.ok) throw new RelayError(`http ${res.status}`);
  if (!body || !Array.isArray(body.replies)) throw new RelayError("bad reply shape");
  const replies = (body.replies as unknown[])
    .filter((r): r is string => typeof r === "string" && r.trim() !== "")
    .map((r) => r.trim())
    .slice(0, MAX_REPLIES);
  const link = typeof body.link === "string" ? body.link.trim() : "";
  if (!replies.length && !link) throw new RelayError("empty reply");
  return { kind: "ok", replies, link };
}

/** Error name or our own safe message. Never the raw message, which could echo user data. */
const describe = (e: unknown): string =>
  e instanceof RelayError ? e.message : e instanceof Error ? e.name : typeof e;

export const TYPING_TIMEOUT_MS = 3_000;

/** Best effort: errors are ignored and a hung call is abandoned after TYPING_TIMEOUT_MS. */
const quietly = async (fn: () => unknown) => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      Promise.resolve().then(fn),
      new Promise((r) => (timer = setTimeout(r, TYPING_TIMEOUT_MS))),
    ]);
  } catch {
    /* best effort */
  } finally {
    clearTimeout(timer);
  }
};

export async function handleMessage(msg: IncomingLike, deps: RelayDeps): Promise<Outcome> {
  const m = relayable(msg);
  if (!m) return "ignored";
  const log = deps.log ?? ((line: string) => console.log(line));
  const sleep = deps.sleep ?? defaultSleep;
  const gap = deps.gapMs ?? GAP_MS;
  const fromHash = hashSender(m.senderId);
  const tag = fromHash.slice(0, 12);
  const started = Date.now();
  log(`[in] ${tag}`);

  let outgoing: string[];
  let outcome: Outcome;
  await quietly(() => deps.typing?.(true));
  try {
    const r = await callApi(fromHash, m.text, deps);
    if (r.kind === "limited") {
      outgoing = [r.detail];
      outcome = "rate_limited";
    } else {
      outgoing = r.link ? [...r.replies, r.link] : r.replies;
      outcome = "replied";
    }
  } catch (e) {
    log(`[err] ${tag} ${describe(e)}`);
    outgoing = [SORRY];
    outcome = "error";
  } finally {
    await quietly(() => deps.typing?.(false));
  }

  try {
    for (const [i, t] of outgoing.entries()) {
      if (i > 0) await sleep(gap);
      await deps.send(t);
    }
  } catch (e) {
    log(`[send-fail] ${tag} ${describe(e)}`);
    return "send_failed";
  }
  log(`[out] ${tag} ${outcome} texts=${outgoing.length} ${((Date.now() - started) / 1000).toFixed(1)}s`);
  return outcome;
}
