"use client";
import { useState } from "react";
import Link from "next/link";
import type { CompareOption, Tool } from "@/lib/types";
import { INTEGRATION_LABELS, priceLabel } from "@/lib/catalog";
import TrustBreakdown, { BadgePill } from "./TrustBreakdown";

interface Props {
  tool: Tool;
  option?: CompareOption;
  recommended?: boolean;
  uses?: string[];
  detailLink?: boolean;
  expanded?: boolean;
}

export default function ToolCard({ tool, option, recommended, uses = [], detailLink = true, expanded = false }: Props) {
  const [open, setOpen] = useState(expanded);
  const works = option?.works_with?.length ? option.works_with : tool.integrations;
  const panelId = `why-${tool.id}`;
  return (
    <article
      data-testid="tool-card"
      className={`card p-5 flex flex-col gap-3 ${recommended ? "border-2 border-accent" : ""}`}
    >
      {recommended && <p className="eyebrow !text-accent">Our pick for you</p>}
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-xl font-semibold">{tool.name}</h3>
        <span data-testid="price" className="font-semibold whitespace-nowrap">{priceLabel(tool)}</span>
      </div>
      <p>{option?.fit_sentence ?? tool.what_it_does}</p>
      {option && <p className="text-soft text-base">{tool.what_it_does}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <BadgePill badge={tool.trust.badge} />
        <span className="font-semibold">{tool.trust.score}/100</span>
      </div>
      {tool.sim_test && (
        <p className="text-base">Simulated owner test: {tool.sim_test.score}/10 (simulated)</p>
      )}
      <p className="text-base text-soft">
        About {tool.setup.minutes} minutes to set up, {tool.setup.difficulty === "easy" ? "easy" : tool.setup.difficulty === "medium" ? "some effort" : "needs a helper"}.
      </p>
      {works.length > 0 && (
        <div>
          <p className="text-sm text-soft">Works with</p>
          <ul className="flex flex-wrap gap-1.5 mt-1">
            {works.map((w) => (
              <li key={w} className={`chip ${uses.includes(w) ? "!bg-accent-tint !text-accent-dark font-semibold" : ""}`}>
                {INTEGRATION_LABELS[w] ?? w}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!expanded && (
        <button
          type="button"
          className="text-left text-accent underline min-h-11 self-start cursor-pointer"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? "Hide why this score" : "Why this score"}
        </button>
      )}
      {open && (
        <div id={panelId}>
          <TrustBreakdown trust={tool.trust} />
        </div>
      )}
      {detailLink && (
        <Link href={`/tool/${tool.id}`} className="text-base self-start">See full details</Link>
      )}
    </article>
  );
}
