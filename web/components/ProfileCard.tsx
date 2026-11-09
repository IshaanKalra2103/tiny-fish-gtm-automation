"use client";
import { useState } from "react";
import type { Profile } from "@/lib/types";
import { BUSINESS_TYPE_LABELS, INTEGRATION_LABELS } from "@/lib/catalog";

export default function ProfileCard({ profile, onEdit }: { profile: Profile; onEdit?: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="card p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-2xl font-semibold">{profile.name}</h3>
        <p className="text-soft">
          {BUSINESS_TYPE_LABELS[profile.business_type] ?? profile.business_type} in {profile.city}, {profile.state}
        </p>
      </div>
      <p className="mt-3">{profile.summary}</p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 text-base">
        <div>
          <dt className="eyebrow">Size</dt>
          <dd>{profile.size}</dd>
        </div>
        <div>
          <dt className="eyebrow">Tools you already use</dt>
          <dd className="flex flex-wrap gap-1.5 mt-1">
            {profile.uses.length ? profile.uses.map((u) => <span key={u} className="chip">{INTEGRATION_LABELS[u] ?? u}</span>) : "None that we could see"}
          </dd>
        </div>
        {profile.pains.length > 0 && (
          <div className="sm:col-span-2">
            <dt className="eyebrow">What seems to slow you down</dt>
            <dd>
              <ul className="list-disc pl-5 mt-1">{profile.pains.map((p) => <li key={p}>{p}</li>)}</ul>
            </dd>
          </div>
        )}
      </dl>
      {onEdit && (
        <form
          className="mt-5 border-t border-line pt-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!text.trim()) return;
            setBusy(true);
            try { await onEdit(text.trim()); setText(""); } finally { setBusy(false); }
          }}
        >
          <label htmlFor="profile-edit" className="font-semibold">Something not right? Tell us what to change.</label>
          <textarea id="profile-edit" className="field mt-2" rows={2} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="For example: we also do catering, and we use Toast, not Square." />
          <button className="btn btn-secondary mt-3" disabled={busy || !text.trim()}>
            {busy ? "Sending..." : "Update what you understood"}
          </button>
        </form>
      )}
    </div>
  );
}
