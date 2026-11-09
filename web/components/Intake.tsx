"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createOwner, health, startTurn } from "@/lib/api";
import OfflineBanner from "./OfflineBanner";

export default function Intake() {
  const router = useRouter();
  const [online, setOnline] = useState<boolean | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
          const owner = await createOwner(text.trim());
          const turn = await startTurn(owner, `Here is my business: ${text.trim()}. What should I try first?`);
          router.push(`/b/${owner}?turn=${turn}`);
        } catch {
          setError("We could not reach our agent just now. You can still look at the example businesses.");
          setOnline(false);
          setBusy(false);
        }
      }}
      className="mt-8 grid gap-4"
    >
      {online === false && <OfflineBanner />}
      <label htmlFor="intake" className="text-xl font-semibold">
        Paste your website or Google Maps link, or tell us about your business in a sentence
      </label>
      <textarea
        id="intake" rows={3} className="field !text-xl !p-4" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="For example: a 2-van HVAC company in Frederick, MD" required={online === true}
      />
      {error && <p role="alert" className="text-brick font-semibold">{error}</p>}
      <div className="flex flex-wrap gap-3 items-center">
        <button className="btn btn-primary !text-xl !min-h-14 !px-8" disabled={busy}>
          {busy ? "One moment..." : "Show me what AI can do"}
        </button>
        <a href="/demo" className="btn btn-secondary !min-h-14">See an example business</a>
      </div>
    </form>
  );
}
