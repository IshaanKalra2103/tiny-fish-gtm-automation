import { notFound } from "next/navigation";
import type { Metadata } from "next";
import Link from "next/link";
import { catalog, toolById, needById } from "@/lib/catalog";
import ToolCard from "@/components/ToolCard";

export function generateStaticParams() {
  return catalog.tools.map((t) => ({ id: t.id }));
}

export async function generateMetadata({ params }: PageProps<"/tool/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: toolById(id)?.name ?? "Tool" };
}

export default async function Page({ params }: PageProps<"/tool/[id]">) {
  const { id } = await params;
  const tool = toolById(id);
  if (!tool) notFound();
  const jobs = tool.need_ids.map((n) => needById(n)?.title ?? n);
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link href="/catalog" className="text-base font-semibold text-muted">Back to the catalog</Link>
      <h1 className="text-4xl sm:text-5xl font-semibold mt-3">{tool.name}</h1>
      <p className="text-soft mt-1">Made by {tool.vendor}. <a href={tool.url} target="_blank" rel="noopener noreferrer" className="font-semibold">Visit their site</a></p>
      <p className="mt-2">Good for: {jobs.join(", ")}</p>
      <div className="mt-6">
        <ToolCard tool={tool} detailLink={false} expanded />
      </div>
      {tool.sim_test && (
        <section className="mt-10">
          <h2 className="text-2xl font-semibold">About the simulated owner test</h2>
          <p className="mt-2 text-soft">A practice run by our software, not a real customer. It shows how easy the tool is to start with.</p>
          <dl className="mt-3 grid gap-2">
            <div><dt className="eyebrow">Who played the owner</dt><dd>{tool.sim_test.persona}</dd></div>
            <div><dt className="eyebrow">The task</dt><dd>{tool.sim_test.task}</dd></div>
            <div><dt className="eyebrow">What happened</dt><dd>{tool.sim_test.notes}</dd></div>
          </dl>
        </section>
      )}
      {tool.sources.length > 0 && (
        <section className="mt-10">
          <h2 className="text-2xl font-semibold">Where our information comes from</h2>
          <ul className="mt-3 list-disc pl-5 break-all text-muted">
            {tool.sources.map((s) => <li key={s}><a href={s} target="_blank" rel="noopener noreferrer">{s}</a></li>)}
          </ul>
        </section>
      )}
      {tool.reviewed_by && (
        <p className="mt-10 text-soft">Reviewed by {tool.reviewed_by}{tool.reviewed_at ? ` on ${tool.reviewed_at}` : ""}</p>
      )}
    </div>
  );
}
