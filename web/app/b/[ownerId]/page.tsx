import { Suspense } from "react";
import { notFound } from "next/navigation";
import BusinessView from "@/components/BusinessView";
import { demoBundles } from "@/data/demo";

export function generateStaticParams() {
  return Object.keys(demoBundles).map((slug) => ({ ownerId: `demo-${slug}` }));
}

export default async function Page({ params }: PageProps<"/b/[ownerId]">) {
  const { ownerId } = await params;
  if (ownerId.startsWith("demo-")) {
    const bundle = demoBundles[ownerId.slice(5)];
    if (!bundle) notFound();
    return (
      <Suspense>
        <BusinessView ownerId={ownerId} demo={bundle} />
      </Suspense>
    );
  }
  return (
    <Suspense>
      <BusinessView ownerId={ownerId} />
    </Suspense>
  );
}
