import type { Badge, Trust } from "@/lib/types";
import { SIGNAL_LABELS } from "@/lib/catalog";

export const BADGE_TEXT: Record<Badge, string> = {
  verified: "Verified by our team",
  caution: "Use with caution",
  unknown: "Unknown builder",
};
const BADGE_CLASS: Record<Badge, string> = {
  verified: "bg-accent-tint text-accent-dark border-accent",
  caution: "bg-amber-tint text-amber-ink border-[#c9a24a]",
  unknown: "bg-grey-tint text-grey-ink border-[#8a8272]",
};

export function BadgePill({ badge }: { badge: Badge }) {
  return (
    <span data-testid="trust-badge" className={`inline-block border rounded-full px-3 py-0.5 text-sm font-semibold ${BADGE_CLASS[badge]}`}>
      {BADGE_TEXT[badge]}
    </span>
  );
}

export default function TrustBreakdown({ trust }: { trust: Trust }) {
  const entries = Object.entries(trust.signals);
  if (entries.length === 0)
    return <p className="text-soft text-base">The detailed checks for this tool have not been written up yet.</p>;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {entries.map(([key, s]) => (
        <li key={key} className="py-3">
          <div className="flex justify-between gap-4 font-semibold">
            <span>{SIGNAL_LABELS[key] ?? key.replace(/_/g, " ")}</span>
            <span className="whitespace-nowrap">{s.points} / {s.max}</span>
          </div>
          <div className="mt-1 h-2 rounded bg-grey-tint" aria-hidden>
            <div className="h-2 rounded bg-accent" style={{ width: `${s.max ? (s.points / s.max) * 100 : 0}%` }} />
          </div>
          <p className="mt-2 text-base">{s.value}</p>
          {s.evidence_url && (
            <a href={s.evidence_url} target="_blank" rel="noopener noreferrer" className="text-base">
              See the evidence
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}
