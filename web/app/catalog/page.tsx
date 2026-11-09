import type { Metadata } from "next";
import CatalogBrowser from "@/components/CatalogBrowser";

export const metadata: Metadata = { title: "Tool catalog" };

export default function Page() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-4xl sm:text-5xl font-semibold">Tool catalog</h1>
      <p className="mt-3 max-w-2xl text-soft">Every tool here was read, scored and checked by a person before it was listed.</p>
      <CatalogBrowser />
    </div>
  );
}
