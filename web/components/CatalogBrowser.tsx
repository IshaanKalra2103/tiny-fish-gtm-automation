"use client";
import { useMemo, useState } from "react";
import { BUSINESS_TYPE_LABELS, catalog } from "@/lib/catalog";
import ToolCard from "./ToolCard";

export default function CatalogBrowser() {
  const [type, setType] = useState("");
  const [job, setJob] = useState("");
  const [badge, setBadge] = useState("");
  const [free, setFree] = useState(false);
  const [unvetted, setUnvetted] = useState(false);

  const types = useMemo(
    () => Array.from(new Set(catalog.tools.flatMap((t) => t.business_types))).sort(),
    [],
  );
  const shown = catalog.tools.filter(
    (t) =>
      t.status === "approved" &&
      (unvetted || t.trust.badge !== "unknown") &&
      (!type || t.business_types.includes(type as never)) &&
      (!job || t.need_ids.includes(job as never)) &&
      (!badge || t.trust.badge === badge) &&
      (!free || t.price.free_plan),
  );

  return (
    <div className="mt-8">
      <div className="card p-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label htmlFor="f-type" className="font-semibold block mb-1">Business type</label>
          <select id="f-type" className="field" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All businesses</option>
            {types.map((t) => <option key={t} value={t}>{BUSINESS_TYPE_LABELS[t] ?? t}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-job" className="font-semibold block mb-1">Job</label>
          <select id="f-job" className="field" value={job} onChange={(e) => setJob(e.target.value)}>
            <option value="">All jobs</option>
            {catalog.needs.map((n) => <option key={n.id} value={n.id}>{n.title}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-badge" className="font-semibold block mb-1">Trust badge</label>
          <select id="f-badge" className="field" value={badge} onChange={(e) => setBadge(e.target.value)}>
            <option value="">Any</option>
            <option value="verified">Verified by our team</option>
            <option value="caution">Use with caution</option>
            {unvetted && <option value="unknown">Unknown builder</option>}
          </select>
        </div>
        <label className="flex items-center gap-3 min-h-12 font-semibold">
          <input type="checkbox" className="size-6 accent-[#111214]" checked={free} onChange={(e) => setFree(e.target.checked)} />
          Free plan only
        </label>
        <label className="flex items-center gap-3 min-h-12 font-semibold">
          <input type="checkbox" className="size-6 accent-[#111214]" checked={unvetted} onChange={(e) => { setUnvetted(e.target.checked); if (!e.target.checked && badge === "unknown") setBadge(""); }} />
          Show unvetted tools
        </label>
      </div>
      {unvetted && (
        <p role="alert" className="mt-4 rounded-2xl border border-amber-ink/20 bg-amber-tint text-amber-ink px-4 py-3">
          Careful: tools marked &quot;Unknown builder&quot; scored under 50 or we could not find out who makes them. We do not recommend them.
        </p>
      )}
      <p className="mt-6 text-muted" aria-live="polite">{shown.length} {shown.length === 1 ? "tool" : "tools"}</p>
      <div className="mt-3 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {shown.map((t) => <ToolCard key={t.id} tool={t} />)}
      </div>
      {shown.length === 0 && <p className="mt-4">No tools match those choices. Try clearing a filter.</p>}
    </div>
  );
}
