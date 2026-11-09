import type { Needs } from "@/lib/types";

export default function NeedList({ needs }: { needs: Needs }) {
  return (
    <ol className="grid gap-4">
      {needs.items.map((n, i) => (
        <li key={n.need_id} data-testid="need-item" className="card p-5 flex gap-4">
          <span className="font-serif text-3xl text-accent leading-none" aria-hidden>{i + 1}</span>
          <div className="flex-1">
            <h3 className="text-xl font-semibold">{n.title}</h3>
            <p className="mt-1">{n.why}</p>
            <p className="mt-2 text-base font-semibold text-accent-dark">
              About {n.est_hours_saved_week} {n.est_hours_saved_week === 1 ? "hour" : "hours"} saved each week
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
