"use client";
import { useState } from "react";
import type { OwnerBundle } from "@/lib/types";
import { toolById } from "@/lib/catalog";
import { decide, revealPassword } from "@/lib/api";

const HELPERS = [
  { name: "Maryland SBDC", url: "https://www.marylandsbdc.org", what: "Free one-on-one business advice from the Maryland Small Business Development Center." },
  { name: "SCORE", url: "https://www.score.org/find-mentor", what: "Free mentors who have run their own businesses." },
  { name: "SBA Baltimore District Office", url: "https://www.sba.gov/district/baltimore", what: "The U.S. Small Business Administration office that serves Maryland." },
];

const STATUS_TEXT: Record<string, string> = {
  planned: "Planned",
  awaiting_approval: "Waiting for your OK",
  running: "Setting it up now",
  needs_owner: "We need you for one step",
  done: "Done",
  failed: "This did not work",
};

function Approval({ ownerId, a, onTurn }: { ownerId: string; a: OwnerBundle["approvals"][number]; onTurn: (id: string) => void }) {
  const [state, setState] = useState<"idle" | "busy" | "sent" | "already" | "error">("idle");
  const [already, setAlready] = useState("");
  const name = toolById(a.tool_id)?.name ?? a.tool_id;
  const go = async (d: "approve" | "reject") => {
    setState("busy");
    try {
      const r = await decide(ownerId, a.id, d);
      if (r.already) {
        setAlready(/approved/i.test(r.already) ? "You already said yes to this." : /rejected/i.test(r.already) ? "You already said not now to this." : "You already answered this.");
        setState("already");
      }
      else { setState("sent"); if (r.turn_id) onTurn(r.turn_id); }
    } catch { setState("error"); }
  };
  return (
    <div className="card p-5 border-2 border-accent">
      <h3 className="text-xl font-semibold">Ready to set up {name}</h3>
      <p className="mt-2">{a.summary}</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <button className="btn btn-primary" disabled={state !== "idle"} onClick={() => go("approve")}>Yes, set it up</button>
        <button className="btn btn-secondary" disabled={state !== "idle"} onClick={() => go("reject")}>Not now</button>
      </div>
      {state === "sent" && <p className="mt-3 text-accent-dark font-semibold">Thank you. We are on it.</p>}
      {state === "already" && <p className="mt-3 font-semibold">{already}</p>}
      {state === "error" && <p className="mt-3 text-brick font-semibold">That did not go through. Please try again in a minute.</p>}
    </div>
  );
}

function Record({ ownerId, s, live }: { ownerId: string; s: OwnerBundle["setups"][string]; live: boolean }) {
  const [pw, setPw] = useState<string | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const name = toolById(s.tool_id)?.name ?? s.tool_id;
  return (
    <div className="card p-5">
      <p className="eyebrow">{name}</p>
      <h3 className="text-xl font-semibold mt-1">{STATUS_TEXT[s.status] ?? s.status}</h3>
      {s.status === "needs_owner" && s.handoff_reason && <p className="mt-2">{s.handoff_reason}</p>}
      {s.streaming_url?.startsWith("http") && s.status !== "done" && (
        <p className="mt-2"><a href={s.streaming_url} target="_blank" rel="noopener noreferrer">Watch live</a></p>
      )}
      {(s.login_url || s.username) && (
        <dl className="mt-3 grid gap-2 text-base">
          {s.login_url && (<div><dt className="eyebrow">Log in at</dt><dd><a href={s.login_url} target="_blank" rel="noopener noreferrer" className="break-all">{s.login_url}</a></dd></div>)}
          {s.username && (<div><dt className="eyebrow">Username</dt><dd className="break-all">{s.username}</dd></div>)}
          {live && s.has_password && (
            <div>
              <dt className="eyebrow">Password</dt>
              <dd>
                {pw === undefined && (
                  <button className="btn btn-secondary" disabled={busy} onClick={async () => {
                    setBusy(true);
                    try { setPw(await revealPassword(ownerId, s.tool_id)); } catch { setPw(null); } finally { setBusy(false); }
                  }}>Show password once</button>
                )}
                {typeof pw === "string" && (<><code className="bg-grey-tint px-2 py-1 rounded break-all">{pw}</code><p className="text-soft mt-1">Write it down or save it now. We will not show it again.</p></>)}
                {pw === null && <p>Already shown. For safety we only show it once. Use &quot;forgot password&quot; on the login page if you lost it.</p>}
              </dd>
            </div>
          )}
        </dl>
      )}
      {s.configured.length > 0 && (
        <div className="mt-4"><p className="font-semibold">What we set up</p><ul className="list-disc pl-5">{s.configured.map((c) => <li key={c}>{c}</li>)}</ul></div>
      )}
      {s.next_steps.length > 0 && (
        <div className="mt-4"><p className="font-semibold">What is next for you</p><ol className="list-decimal pl-5">{s.next_steps.map((c) => <li key={c}>{c}</li>)}</ol></div>
      )}
    </div>
  );
}

export default function SetupPanel({ ownerId, bundle, live, onTurn }: { ownerId: string; bundle: OwnerBundle; live: boolean; onTurn: (id: string) => void }) {
  const pending = bundle.approvals.filter((a) => a.status === "pending");
  const records = Object.values(bundle.setups);
  return (
    <div className="grid gap-4">
      {live && pending.map((a) => <Approval key={a.id} ownerId={ownerId} a={a} onTurn={onTurn} />)}
      {records.map((s) => <Record key={s.tool_id} ownerId={ownerId} s={s} live={live} />)}
      {!live && records.length === 0 && <p className="text-soft">In a live session, we can set a tool up for you after you say yes.</p>}
      <div className="card p-5">
        <h3 className="text-xl font-semibold">Find me a local helper</h3>
        <p className="mt-1 text-soft">Prefer a real person? These public organizations help Maryland small businesses, often for free.</p>
        <ul className="mt-3 grid gap-3 sm:grid-cols-3">
          {HELPERS.map((h) => (
            <li key={h.name}>
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="font-semibold">{h.name}</a>
              <p className="text-base text-soft">{h.what}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
