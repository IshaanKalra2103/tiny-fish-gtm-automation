"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createOwner, health, startTurn } from "@/lib/api";
import OfflineBanner from "./OfflineBanner";

export default function Intake() {
  const router = useRouter();
  const [online, setOnline] = useState<boolean | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Reuse an owner whose first turn was refused (busy), so retries do not use up the per-client owner cap.
  const ownerRef = useRef<string | null>(null);

  useEffect(() => {
    let gone = false;
    health().then((ok) => { if (!gone) setOnline(ok); });
    return () => { gone = true; };
  }, []);

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (online === false) { router.push("/demo"); return; }
        if (!text.trim()) return;
        setBusy(true); setError("");
        try {
          const owner = ownerRef.current ?? (ownerRef.current = await createOwner(text.trim()));
          const turn = await startTurn(owner, `Here is my business: ${text.trim()}. What should I try first?`);
          router.push(`/b/${owner}?turn=${turn}`);
        } catch (err) {
          if (err instanceof ApiError && err.status < 500) {
            setError(err.message); // a limit (429) or a bad request: the agent is up, so stay here
          } else {
            setError("We could not reach our agent just now. You can still look at the example businesses.");
            setOnline(false);
          }
          setBusy(false);
        }
      }}
      className="mt-8 grid gap-4"
    >
      {online === false && <OfflineBanner />}
      <label htmlFor="intake" className="text-xl font-semibold">Paste your website</label>
      <input
        id="intake" type="text" className="field !text-xl !min-h-16 !px-5 !rounded-2xl" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="yourshop.com" required={online === true} autoComplete="url"
        aria-describedby="intake-hint"
      />
      <p id="intake-hint" className="-mt-2 text-base text-soft">No website? Write one sentence, like &quot;a 2-van HVAC company in Frederick, MD&quot;.</p>
      {error && <p role="alert" className="text-brick font-semibold">{error}</p>}
      <button className="btn btn-primary w-full !text-xl !min-h-16" disabled={busy}>
        {busy ? "One moment..." : "Show me what AI can do"}
      </button>
    </form>
  );
}
