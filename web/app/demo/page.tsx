import Link from "next/link";
import type { Metadata } from "next";
import { DEMO_BUSINESSES, demoBundles } from "@/data/demo";

export const metadata: Metadata = { title: "Example businesses" };

export default function DemoPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-4xl sm:text-5xl font-semibold">Five example businesses</h1>
      <p className="mt-3 max-w-2xl text-soft">
        These are made-up Maryland businesses. Open one to see what we found, which tools we compared, and what a finished setup looks like.
      </p>
      <ul className="mt-8 grid gap-5 sm:grid-cols-2">
        {DEMO_BUSINESSES.map((b) => {
          const ready = !!demoBundles[b.slug];
          const inner = (
            <>
              <p className="eyebrow">{b.kind}</p>
              <h2 className="text-2xl font-semibold mt-1">{b.name}</h2>
              <p className="text-soft">{b.place}</p>
              <p className={`mt-4 font-semibold ${ready ? "text-ink" : "text-muted"}`}>{ready ? "See what AI can do for them" : "Coming soon"}</p>
            </>
          );
          return (
            <li key={b.slug}>
              {ready ? (
                <Link href={`/b/demo-${b.slug}`} className="card p-6 block h-full text-ink hover:no-underline hover:!border-ink/20 transition-colors">{inner}</Link>
              ) : (
                <div className="card p-6 h-full opacity-70">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
