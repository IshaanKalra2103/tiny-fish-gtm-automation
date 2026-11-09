import type { OwnerBundle, TurnEvent } from "./types";

export const AGENT_URL: string | undefined = process.env.NEXT_PUBLIC_AGENT_API_URL || undefined;

function base(): string {
  if (!AGENT_URL) throw new Error("Agent is offline");
  return AGENT_URL.replace(/\/$/, "");
}

export async function health(): Promise<boolean> {
  if (!AGENT_URL) return false;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 2000);
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

export async function createOwner(source: string): Promise<string> {
  const { status, json } = await post<{ owner_id: string }>("/api/owners", { source });
  if (status >= 400 || !json) throw new Error("Could not start");
  return json.owner_id;
}

export async function startTurn(ownerId: string, text: string): Promise<string> {
  const { status, json } = await post<{ turn_id: string }>(`/api/owners/${ownerId}/turns`, { text, channel: "web" });
  if (status >= 400 || !json) throw new Error("Could not send");
  return json.turn_id;
}

export function streamTurn(turnId: string, onEvent: (e: TurnEvent) => void): () => void {
  if (!AGENT_URL) return () => {};
  const es = new EventSource(`${base()}/api/turns/${turnId}/events`);
  const close = () => es.close();
  es.onmessage = (m) => {
    try {
      const e = JSON.parse(m.data) as TurnEvent;
      onEvent(e);
      if (e.type === "done" || e.type === "error") close();
    } catch { /* ignore bad frame */ }
  };
  es.onerror = () => {
    onEvent({ type: "error", message: "We lost the connection to the agent." });
    close();
  };
  return close;
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
  if (status >= 400) throw new Error("Could not record your answer");
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
