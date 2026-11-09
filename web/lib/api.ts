import type { OwnerBundle, TurnEvent } from "./types";

export const AGENT_URL: string | undefined = process.env.NEXT_PUBLIC_AGENT_API_URL || undefined;

/** The API answered with an error. `message` is its `detail` text when it sent one (429 texts are written for owners). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

function base(): string {
  if (!AGENT_URL) throw new Error("Agent is offline");
  return AGENT_URL.replace(/\/$/, "");
}

export async function health(): Promise<boolean> {
  if (!AGENT_URL) return false;
  const ctl = new AbortController();
  // An uncached /api/health runs `docker image inspect`, which can take seconds on colima.
  const timer = setTimeout(() => ctl.abort(), 6000);
  try {
    const r = await fetch(`${base()}/api/health`, { signal: ctl.signal });
    if (!r.ok) return false;
    const j = await r.json();
    return j?.ok === true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function post<T>(path: string, body: unknown): Promise<{ status: number; json: T | null }> {
  const r = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let json: T | null = null;
  try { json = (await r.json()) as T; } catch { /* no body */ }
  return { status: r.status, json };
}

function apiError(status: number, json: unknown, fallback: string): ApiError {
  const detail = (json as { detail?: unknown } | null)?.detail;
  return new ApiError(typeof detail === "string" && detail ? detail : fallback, status);
}

export async function createOwner(source: string): Promise<string> {
  const { status, json } = await post<{ owner_id: string }>("/api/owners", { source });
  if (status >= 400 || !json?.owner_id) throw apiError(status, json, "We could not start just now. Please try again in a minute.");
  return json.owner_id;
}

export async function startTurn(ownerId: string, text: string): Promise<string> {
  const { status, json } = await post<{ turn_id: string }>(`/api/owners/${ownerId}/turns`, { text, channel: "web" });
  if (status >= 400 || !json?.turn_id) throw apiError(status, json, "We could not send that. Please try again in a minute.");
  return json.turn_id;
}

/**
 * Follow a turn by polling (the Cloudflare quick tunnel buffers SSE until the stream ends).
 * Same callback interface as the old EventSource version; returns a stop function.
 */
export function streamTurn(turnId: string, onEvent: (e: TurnEvent) => void): () => void {
  if (!AGENT_URL) return () => {};
  let stopped = false, next = 0, fails = 0, failingSince = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const stop = () => { stopped = true; clearTimeout(timer); };
  const tick = async () => {
    if (stopped) return;
    const ctl = new AbortController();
    const abort = setTimeout(() => ctl.abort(), 10_000);
    try {
      const r = await fetch(`${base()}/api/turns/${turnId}/poll?after=${next}`, { cache: "no-store", signal: ctl.signal });
      if (r.status === 404) { if (!stopped) onEvent({ type: "error", message: "We could not find that request. Please send it again." }); stop(); return; }
      if (!r.ok) throw new Error(`http ${r.status}`);
      const j = (await r.json()) as { events: TurnEvent[]; next: number; done: boolean };
      fails = 0; failingSince = 0;
      for (const e of j.events) {
        if (stopped) return;
        onEvent(e);
        if (e.type === "done" || e.type === "error") { stop(); return; }
      }
      next = j.next;
      if (j.done) { stop(); return; }
    } catch {
      if (stopped) return;
      fails += 1;
      failingSince ||= Date.now();
      if (Date.now() - failingSince >= 60_000) {
        onEvent({ type: "error", message: "We lost the connection to the agent." });
        stop();
        return;
      }
    } finally {
      clearTimeout(abort);
    }
    if (!stopped) timer = setTimeout(tick, fails >= 3 ? 5000 : 1500);
  };
  void tick();
  return stop;
}

export async function getOwner(ownerId: string): Promise<OwnerBundle> {
  const r = await fetch(`${base()}/api/owners/${ownerId}`);
  if (!r.ok) throw new Error("Not found");
  return (await r.json()) as OwnerBundle;
}

export async function decide(
  ownerId: string,
  approvalId: string,
  decision: "approve" | "reject",
): Promise<{ turn_id?: string; already?: string }> {
  const { status, json } = await post<{ turn_id?: string; detail?: string }>(`/api/owners/${ownerId}/approvals/${approvalId}`, { decision });
  if (status === 409) return { already: json?.detail ?? "Already decided" };
  if (status >= 400) throw apiError(status, json, "That did not go through. Please try again in a minute.");
  return json ?? {};
}

export async function revealPassword(ownerId: string, toolId: string): Promise<string | null> {
  const r = await fetch(`${base()}/api/owners/${ownerId}/password/${toolId}`);
  if (r.status === 410) return null;
  if (!r.ok) throw new Error("Could not fetch");
  const j = (await r.json()) as { password?: string };
  return j.password ?? null;
}

export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith("/media/")) return AGENT_URL ? `${base()}${path}` : null;
  return path;
}
