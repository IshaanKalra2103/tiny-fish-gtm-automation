"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { OwnerBundle, TurnEvent } from "@/lib/types";
import { getOwner, health, startTurn, streamTurn } from "@/lib/api";
import { needById, toolById } from "@/lib/catalog";
import ProfileCard from "./ProfileCard";
import NeedList from "./NeedList";
import ToolCard from "./ToolCard";
import PreviewPlayer from "./PreviewPlayer";
import SetupPanel from "./SetupPanel";
import OfflineBanner from "./OfflineBanner";
import TurnLog from "./TurnLog";
import ChatBox from "./ChatBox";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className="text-3xl font-semibold mb-5">{title}</h2>
      {children}
    </section>
  );
}

export default function BusinessView({ ownerId, demo }: { ownerId: string; demo?: OwnerBundle }) {
  const live = !demo;
  const [bundle, setBundle] = useState<OwnerBundle | null>(demo ?? null);
  const [offline, setOffline] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [events, setEvents] = useState<TurnEvent[]>([]);
  const [active, setActive] = useState(false);
  const closeRef = useRef<(() => void) | null>(null);
  const params = useSearchParams();
  const initialTurn = params.get("turn");

  const refresh = useCallback(async () => {
    try { setBundle(await getOwner(ownerId)); setLoadError(false); } catch { setLoadError(true); }
  }, [ownerId]);

  const follow = useCallback((turnId: string) => {
    closeRef.current?.();
    setEvents([]);
    setActive(true);
    closeRef.current = streamTurn(turnId, (e) => {
      setEvents((prev) => [...prev, e]);
      if (e.type === "files" || e.type === "done") void refresh();
      if (e.type === "done" || e.type === "error") setActive(false);
    });
  }, [refresh]);

  useEffect(() => {
    if (!live) return;
    let gone = false;
    health().then((ok) => { if (!gone) setOffline(!ok); });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    if (initialTurn) follow(initialTurn);
    return () => { gone = true; closeRef.current?.(); };
  }, [live, refresh, follow, initialTurn]);

  const send = async (text: string) => {
    const id = await startTurn(ownerId, text);
    follow(id);
  };

  if (!bundle) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        {offline && <OfflineBanner />}
        {loadError ? (
          <p className="mt-4">We could not load this business page. It may have expired, or our agent may be resting. <a href="/demo">See the example businesses</a>.</p>
        ) : (
          <p className="mt-4">Loading your business...</p>
        )}
        <div className="mt-6"><TurnLog events={events} active={active} /></div>
      </div>
    );
  }

  const profile = bundle.profile;
  const compares = Object.values(bundle.compares);
  const previews = Object.values(bundle.previews);
  const firstNeed = bundle.needs?.items[0];
  const suggestions = [
    ...(bundle.needs?.items ?? [])
      .filter((n) => !bundle.compares[n.need_id])
      .slice(0, 2)
      .map((n) => ({ label: `Compare tools for ${n.title.toLowerCase()}`, text: `Compare tools for ${n.title}` })),
    { label: "Show me a preview", text: `Show me a preview of the best tool for ${firstNeed?.title ?? "my first job"}` },
    { label: "Set it up for me", text: "Set it up for me" },
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      {offline && live && <div className="mb-6"><OfflineBanner /></div>}
      <p className="eyebrow">{demo ? "Example business" : "Your business"}</p>
      <h1 className="text-4xl sm:text-5xl font-semibold mt-1">{profile?.name ?? "Getting to know your business"}</h1>
      {demo && <p className="mt-2 text-soft">This is an example. The business is made up; the results come from our real process.</p>}

      {live && <div className="mt-6"><TurnLog events={events} active={active} /></div>}

      {profile && (
        <Section title="Here's what we understood">
          <ProfileCard profile={profile} onEdit={live ? (t) => send(`Please correct this: ${t}`) : undefined} />
        </Section>
      )}

      {bundle.needs && (
        <Section title="Jobs AI can take off your plate">
          <NeedList needs={bundle.needs} />
        </Section>
      )}

      {compares.map((c) => {
        const need = needById(c.need_id);
        const title = bundle.needs?.items.find((n) => n.need_id === c.need_id)?.title ?? need?.title ?? c.need_id;
        return (
          <Section key={c.need_id} title={`Tools for: ${title}`}>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {c.options.map((o) => {
                const tool = toolById(o.tool_id);
                return tool ? (
                  <ToolCard key={o.tool_id} tool={tool} option={o} uses={profile?.uses}
                    recommended={o.tool_id === c.recommended_tool_id} />
                ) : null;
              })}
            </div>
          </Section>
        );
      })}

      {previews.length > 0 && (
        <Section title="See it in your business">
          <div className="grid gap-5 md:grid-cols-2">
            {previews.map((p) => <PreviewPlayer key={p.tool_id} preview={p} />)}
          </div>
        </Section>
      )}

      <Section title="Getting set up">
        <SetupPanel ownerId={ownerId} bundle={bundle} live={live} onTurn={follow} />
      </Section>

      {live && (
        <Section title="Ask us anything">
          <ChatBox messages={bundle.messages} suggestions={suggestions} onSend={send} disabled={offline} />
        </Section>
      )}
    </div>
  );
}
