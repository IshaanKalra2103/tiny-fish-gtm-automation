import Intake from "@/components/Intake";
import { APP_NAME, TAGLINE } from "@/lib/brand";
import { SIGNAL_LABELS } from "@/lib/catalog";

const STEPS = [
  ["You tell us about your business", "Paste your website or write one sentence. That is all we need."],
  ["We pick the jobs", "We find three to five jobs where AI could save you real hours each week."],
  ["We compare vetted tools", "For each job you see two or three tools side by side, with their price and a trust score."],
  ["We set it up, if you say yes", "We show you exactly what we would do. Nothing happens until you approve it."],
];
const SIGNALS: [string, string][] = [
  ["identity", "A real company with named people and an address."],
  ["longevity", "Around long enough to have a track record."],
  ["data_handling", "A clear privacy policy that says your customers' data is not used to train models."],
  ["pricing_transparency", "Prices you can see without calling a salesperson."],
  ["independent_reviews", "Good ratings from people who are not the vendor."],
  ["viability", "Still being updated, with no sign it is shutting down."],
];

export default function Home() {
  return (
    <>
      <section className="mx-auto max-w-3xl px-4 pt-14 pb-12">
        <p className="eyebrow">{APP_NAME}</p>
        <h1 className="text-4xl sm:text-6xl font-semibold mt-2">Find the AI tools worth your time, and let us set them up.</h1>
        <p className="mt-4 text-xl text-soft">{TAGLINE}</p>
        <Intake />
      </section>

      <section className="border-t border-line bg-card">
        <div className="mx-auto max-w-5xl px-4 py-14">
          <h2 className="text-3xl font-semibold">How it works</h2>
          <ol className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(([t, d], i) => (
              <li key={t}>
                <span className="font-serif text-4xl text-accent">{i + 1}</span>
                <h3 className="text-xl font-semibold mt-1">{t}</h3>
                <p className="text-soft mt-1">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto max-w-5xl px-4 py-14">
          <h2 className="text-3xl font-semibold">Every tool is vetted</h2>
          <p className="mt-3 max-w-2xl text-soft">
            Before a tool is listed, we check six things and a person signs off. Each tool gets a score out of 100, and you can open it to see the evidence behind every point.
          </p>
          <ul className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {SIGNALS.map(([k, d]) => (
              <li key={k} className="card p-5">
                <h3 className="text-lg font-semibold">{SIGNAL_LABELS[k]}</h3>
                <p className="text-soft text-base mt-1">{d}</p>
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap gap-3">
            <span className="inline-block border rounded-full px-3 py-0.5 text-sm font-semibold bg-accent-tint text-accent-dark border-accent">Verified by our team</span>
            <span className="inline-block border rounded-full px-3 py-0.5 text-sm font-semibold bg-amber-tint text-amber-ink border-[#c9a24a]">Use with caution</span>
            <span className="inline-block border rounded-full px-3 py-0.5 text-sm font-semibold bg-grey-tint text-grey-ink border-[#8a8272]">Unknown builder</span>
          </div>
          <p className="mt-3 text-soft max-w-2xl text-base">
            Verified means 75 or more and approved by a person. Caution means 50 to 74. Unknown builder means under 50, or we could not tell who makes it; those are hidden unless you ask to see them.
          </p>
        </div>
      </section>
    </>
  );
}
