import type { TurnEvent } from "@/lib/types";

export default function TurnLog({ events, active }: { events: TurnEvent[]; active: boolean }) {
  if (events.length === 0 && !active) return null;
  const lines = events.map((e) => {
    switch (e.type) {
      case "queued": return e.position > 0 ? `You are number ${e.position} in line. We will start soon.` : "Starting now.";
      case "status": return e.text;
      case "files": return "Updated your page with new results.";
      case "done": return e.reply;
      case "error": return `Something went wrong: ${e.message}`;
    }
  });
  return (
    <section aria-live="polite" aria-label="Progress" className="card p-5 border-accent">
      <p className="eyebrow !text-accent">{active ? "Working on it" : "Finished"}</p>
      <ul className="mt-2 grid gap-1.5">
        {lines.map((l, i) => <li key={i}>{l}</li>)}
        {active && <li className="text-soft">Still working. This can take a minute or two.</li>}
      </ul>
    </section>
  );
}
