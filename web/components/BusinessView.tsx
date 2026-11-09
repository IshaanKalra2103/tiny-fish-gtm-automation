"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, LayoutGroup, MotionConfig, motion, type PanInfo } from "motion/react";
import type { NeedItem, OwnerBundle, Tool, TurnEvent } from "@/lib/types";
import { ApiError, getOwner, health, mediaUrl, startTurn, streamTurn } from "@/lib/api";
import { BUSINESS_TYPE_LABELS, INTEGRATION_LABELS, catalog, priceLabel, toolById } from "@/lib/catalog";
import ToolCard from "./ToolCard";
import TrustBreakdown, { BadgePill } from "./TrustBreakdown";
import { Approval, HELPERS, SetupRecordView } from "./SetupPanel";
import OfflineBanner from "./OfflineBanner";
import TurnLog from "./TurnLog";
import ChatBox from "./ChatBox";
import Sheet from "./Sheet";

type Preview = OwnerBundle["previews"][string];
type CardDef =
  | { key: string; kind: "intro" }
  | { key: string; kind: "profile" }
  | { key: string; kind: "job"; need: NeedItem; n: number; tool?: Tool; preview?: Preview }
  | { key: string; kind: "setup" }
  | { key: string; kind: "helpers" };
type SheetState =
  | { kind: "compare"; need: NeedItem }
  | { kind: "trust"; tool: Tool }
  | { kind: "preview"; preview: Preview; name: string }
  | { kind: "chat" }
  | null;

const spring = { type: "spring" as const, stiffness: 320, damping: 32 };

const Icon = {
  x: <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>,
  play: <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden fill="currentColor"><path d="M8 5.5v13l11-6.5z" /></svg>,
  check: <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>,
  chat: <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden fill="currentColor"><path d="M12 3C6.9 3 3 6.5 3 10.8c0 2.4 1.2 4.5 3.2 5.9L5.5 21l4.4-2.5c.7.1 1.4.2 2.1.2 5.1 0 9-3.5 9-7.9S17.1 3 12 3z" /></svg>,
  grid: <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden fill="none" stroke="currentColor" strokeWidth="2.2"><rect x="4" y="4" width="16" height="6" rx="2" /><rect x="4" y="14" width="16" height="6" rx="2" /></svg>,
};

function eventLine(e: TurnEvent): string {
  switch (e.type) {
    case "queued": return e.position > 0 ? `You are number ${e.position} in line. We will start soon.` : "Starting now.";
    case "status": return e.text;
    case "files": return "Updating your page with what we found.";
    case "done": return e.reply;
    case "error": return `Something went wrong: ${e.message}`;
  }
}

function previewSrc(p?: Preview): string | null {
  if (!p || p.status !== "completed") return null;
  return mediaUrl(p.video_url);
}

/** The card's picture: the tool's preview video, or a warm gradient when there is none. */
function CardBackdrop({ src, still }: { src: string | null; still?: boolean }) {
  return (
    <div className="absolute inset-0" aria-hidden>
      {src ? (
        still ? <video src={`${src}#t=0.5`} muted playsInline preload="metadata" className="h-full w-full object-cover" />
          : <video src={src} muted loop autoPlay playsInline preload="auto" className="h-full w-full object-cover" />
      ) : <div className="h-full w-full warm-bg" />}
      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/65 to-black/30" />
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return <span className="glass inline-block rounded-full px-3.5 py-1 text-base font-semibold text-white">{children}</span>;
}

function BigButton({ icon, label, onClick, primary, disabled }: { icon: React.ReactNode; label: string; onClick: () => void; primary?: boolean; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className={`flex-1 min-h-[72px] rounded-2xl flex flex-col items-center justify-center gap-0.5 font-semibold text-base transition-transform active:scale-95 disabled:opacity-50 ${primary ? "bg-accent text-[#1a1109]" : "glass text-white hover:bg-white/20"}`}>
      {icon}<span>{label}</span>
    </button>
  );
}

export default function BusinessView({ ownerId, demo }: { ownerId: string; demo?: OwnerBundle }) {
  const live = !demo;
  const [bundle, setBundle] = useState<OwnerBundle | null>(demo ?? null);
  const [offline, setOffline] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [events, setEvents] = useState<TurnEvent[]>([]);
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(1);
  const [mode, setMode] = useState<"deck" | "overview">("deck");
  const [sheet, setSheet] = useState<SheetState>(null);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
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
    // After the first load, follow the turn that is running now; ?turn= can be an old one after a reload.
    getOwner(ownerId).then(
      (b) => {
        if (gone) return;
        setBundle(b); setLoadError(false);
        const turn = b.active_turn ?? initialTurn;
        if (turn) follow(turn);
      },
      () => {
        if (gone) return;
        setLoadError(true);
        if (initialTurn) follow(initialTurn);
      },
    );
    return () => { gone = true; closeRef.current?.(); };
  }, [live, ownerId, follow, initialTurn]);

  const send = useCallback(async (text: string) => {
    const id = await startTurn(ownerId, text);
    follow(id);
  }, [ownerId, follow]);

  const cards: CardDef[] = useMemo(() => {
    if (!bundle) return [];
    const out: CardDef[] = [];
    if (bundle.profile) out.push({ key: "profile", kind: "profile" });
    else if (live) out.push({ key: "intro", kind: "intro" });
    (bundle.needs?.items ?? []).forEach((need, i) => {
      const c = bundle.compares[need.need_id];
      const tool = c ? toolById(c.recommended_tool_id) : undefined;
      const preview = (tool && bundle.previews[tool.id])
        ?? Object.values(bundle.previews).find((p) => c?.options.some((o) => o.tool_id === p.tool_id));
      out.push({ key: `job-${need.need_id}`, kind: "job", need, n: i + 1, tool, preview });
    });
    out.push({ key: "setup", kind: "setup" });
    out.push({ key: "helpers", kind: "helpers" });
    return out;
  }, [bundle, live]);

  const pending = bundle?.approvals.filter((a) => a.status === "pending") ?? [];
  const records = bundle ? Object.values(bundle.setups) : [];

  // A new approval waiting for the owner becomes the focused card.
  const pendingCount = pending.length;
  const [seenPending, setSeenPending] = useState(pendingCount);
  if (pendingCount !== seenPending) {
    setSeenPending(pendingCount);
    if (live && pendingCount > seenPending) {
      const i = cards.findIndex((c) => c.kind === "setup");
      if (i >= 0) { setIndex(i); setMode("deck"); }
    }
  }

  const at = Math.min(index, Math.max(cards.length - 1, 0));
  const go = useCallback((to: number) => {
    if (to < 0 || to >= cards.length) return;
    setDir(to > at ? 1 : -1); setIndex(to); setActionError("");
  }, [at, cards.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (sheet || mode !== "deck") return;
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      if (e.key === "ArrowRight") go(at + 1);
      if (e.key === "ArrowLeft") go(at - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, at, sheet, mode]);

  const closeSheet = useCallback(() => setSheet(null), []);

  const setItUp = async () => {
    const setupAt = cards.findIndex((c) => c.kind === "setup");
    if (!live) { go(setupAt); return; }
    if (pending.length) { go(setupAt); return; }
    setBusy(true); setActionError("");
    try { await send("Set it up for me"); }
    catch (e) { setActionError(e instanceof ApiError ? e.message : "We could not reach our agent just now. Please try again in a minute."); }
    finally { setBusy(false); }
  };

  // Pinch in with two fingers on the deck to see every card at once, as in the reference video.
  const pinch = useRef<number | null>(null);
  const dist = (t: React.TouchList) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  const onTouchStart = (e: React.TouchEvent) => { pinch.current = e.touches.length === 2 ? dist(e.touches) : null; };
  const onTouchMove = (e: React.TouchEvent) => {
    if (pinch.current && e.touches.length === 2 && dist(e.touches) < pinch.current * 0.7) { pinch.current = null; setMode("overview"); }
  };

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.x < -90 || info.velocity.x < -600) go(at + 1);
    else if (info.offset.x > 90 || info.velocity.x > 600) go(at - 1);
  };

  const profile = bundle?.profile ?? null;
  const items = bundle?.needs?.items ?? [];
  const hours = Math.round(items.reduce((s, n) => s + n.est_hours_saved_week, 0));
  const lastReply = [...(bundle?.messages ?? [])].reverse().find((m) => m.role === "agent");
  const lastEvent = events[events.length - 1];
  const statusLine = [...events].reverse().find((e) => e.type === "status" || e.type === "queued" || e.type === "files");
  const firstNeed = items[0];
  const suggestions = [
    ...items.filter((n) => !bundle?.compares[n.need_id]).slice(0, 2)
      .map((n) => ({ label: `Compare tools for ${n.title.toLowerCase()}`, text: `Compare tools for ${n.title}` })),
    { label: "Show me a preview", text: `Show me a preview of the best tool for ${firstNeed?.title ?? "my first job"}` },
    { label: "Set it up for me", text: "Set it up for me" },
  ];
  const firstPreviewSrc = previewSrc(Object.values(bundle?.previews ?? {})[0]);

  function cardTitle(c: CardDef): string {
    switch (c.kind) {
      case "intro": return "Getting to know you";
      case "profile": return "Here's what we understood";
      case "job": return c.need.title;
      case "setup": return pending.length ? "Ready when you are" : "Getting set up";
      case "helpers": return "Prefer a person?";
    }
  }
  function cardSub(c: CardDef): string {
    switch (c.kind) {
      case "intro": return "Tell us about your business";
      case "profile": return profile ? `${BUSINESS_TYPE_LABELS[profile.business_type] ?? profile.business_type} in ${profile.city}` : "";
      case "job": return `About ${c.need.est_hours_saved_week} ${c.need.est_hours_saved_week === 1 ? "hour" : "hours"} a week`;
      case "setup": return pending.length ? "Waiting for your OK" : records.length ? "See what we set up" : "Nothing happens until you say yes";
      case "helpers": return "Free local help in Maryland";
    }
  }
  function cardSrc(c: CardDef): string | null {
    if (c.kind === "job") return previewSrc(c.preview);
    if (c.kind === "profile") return firstPreviewSrc;
    return null;
  }

  function renderCard(c: CardDef) {
    const src = cardSrc(c);
    if (c.kind === "job") {
      const tool = c.tool;
      const compare = bundle?.compares[c.need.need_id];
      return (
        <>
          <CardBackdrop src={src} />
          <div className="relative h-full flex flex-col p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <Pill>Job {c.n} of {items.length}</Pill>
              {src && <span className="rounded-full bg-black/70 px-3 py-1 text-sm font-semibold text-white">AI-generated preview</span>}
            </div>
            <div className="mt-auto min-h-0 overflow-y-auto -mx-1 px-1 pt-1">
              <h2 className="text-[2rem] sm:text-[2.3rem] font-semibold text-white leading-[1.05]">{c.need.title}</h2>
              <p className="mt-2 text-lg leading-snug text-white/90 line-clamp-2">{c.need.why}</p>
              <p className="mt-2 text-lg font-semibold text-accent-dark">
                About {c.need.est_hours_saved_week} {c.need.est_hours_saved_week === 1 ? "hour" : "hours"} a week
              </p>
              {tool ? (
                <div className="glass-dark mt-3 rounded-2xl px-3.5 pt-3 pb-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <p className="text-lg text-white"><span className="text-white/75">Our pick:</span> <strong>{tool.name}</strong></p>
                    <p className="text-lg text-white/90">{priceLabel(tool)}</p>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <BadgePill badge={tool.trust.badge} />
                    <span className="font-semibold text-white">{tool.trust.score}/100</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4">
                    <button type="button" className="min-h-12 text-base font-semibold text-accent underline underline-offset-4"
                      onClick={() => setSheet({ kind: "compare", need: c.need })}>Compare tools</button>
                    <button type="button" className="min-h-12 text-base font-semibold text-accent underline underline-offset-4"
                      onClick={() => setSheet({ kind: "trust", tool })}>Why we trust it</button>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-white/85">
                  {live ? "We have not compared tools for this job yet." : "We did not compare tools for this job in this example."}
                  {live && <> <button type="button" className="min-h-12 font-semibold text-accent underline underline-offset-4"
                    onClick={() => send(`Compare tools for ${c.need.title}`).catch((e) => setActionError(e instanceof ApiError ? e.message : "We could not reach our agent just now."))}>
                    Compare tools</button></>}
                </p>
              )}
              {actionError && <p role="alert" className="mt-2 rounded-xl bg-black/70 px-3 py-2 font-semibold text-brick">{actionError}</p>}
              <div className="mt-4 flex gap-2.5">
                <BigButton icon={Icon.x} label="Not now" onClick={() => go(at + 1)} />
                <BigButton icon={Icon.play} label="Show me" onClick={() => {
                  if (c.preview && src) setSheet({ kind: "preview", preview: c.preview, name: tool?.name ?? c.preview.tool_id });
                  else if (compare) setSheet({ kind: "compare", need: c.need });
                  else setSheet({ kind: "chat" });
                }} />
                <BigButton icon={Icon.check} label={busy ? "One moment" : "Set it up"} primary disabled={busy || offline} onClick={setItUp} />
              </div>
            </div>
          </div>
        </>
      );
    }
    if (c.kind === "profile" && profile) {
      return (
        <>
          <CardBackdrop src={src} />
          <div className="relative h-full flex flex-col p-5 sm:p-6">
            <div><Pill>Here&apos;s what we understood</Pill></div>
            <div className="mt-auto min-h-0 overflow-y-auto -mx-1 px-1 pt-1">
              <h2 className="text-[2.1rem] sm:text-[2.4rem] font-semibold text-white leading-[1.05]">{profile.name}</h2>
              <p className="mt-2 text-xl text-white">
                {BUSINESS_TYPE_LABELS[profile.business_type] ?? profile.business_type} in {profile.city}, {profile.state}
              </p>
              <p className="mt-2 text-lg leading-snug text-white/85 line-clamp-3">{profile.summary}</p>
              <p className="mt-4 text-base font-semibold text-white/80">Tools you already use</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {profile.uses.length ? profile.uses.map((u) => (
                  <span key={u} className="glass rounded-full px-3 py-1 text-base text-white">{INTEGRATION_LABELS[u] ?? u}</span>
                )) : <span className="text-white/85">None that we could see</span>}
              </div>
              <button type="button" onClick={() => setSheet({ kind: "chat" })}
                className="mt-3 min-h-12 text-lg font-semibold text-accent underline underline-offset-4">Not right? Tell us</button>
              <div className="mt-3 flex">
                <BigButton icon={Icon.check} label={items.length ? `Show me the ${items.length} jobs` : "Next"} primary onClick={() => go(at + 1)} />
              </div>
            </div>
          </div>
        </>
      );
    }
    if (c.kind === "intro") {
      return (
        <>
          <CardBackdrop src={null} />
          <div className="relative h-full flex flex-col p-5 sm:p-6">
            <div><Pill>Getting to know you</Pill></div>
            <div className="mt-auto min-h-0 overflow-y-auto -mx-1 px-1 pt-1">
              <h2 className="text-[2.1rem] font-semibold text-white leading-[1.05]">Tell us about your business</h2>
              <p className="mt-2 text-lg text-white/90">Ask us a question or tell us what takes up your week. We will find the jobs AI can take off your plate.</p>
              <div className="mt-4 flex"><BigButton icon={Icon.chat} label="Ask us" primary onClick={() => setSheet({ kind: "chat" })} /></div>
            </div>
          </div>
        </>
      );
    }
    if (c.kind === "setup") {
      return (
        <>
          <CardBackdrop src={null} />
          <div className="relative h-full flex flex-col p-5 sm:p-6">
            <div><Pill>{pending.length ? "Waiting for your OK" : "Getting set up"}</Pill></div>
            <div className="mt-4 flex-1 overflow-y-auto grid content-end gap-4 text-white">
              {live && pending.map((a) => <Approval key={a.id} ownerId={ownerId} a={a} onTurn={follow} />)}
              {records.map((s) => <SetupRecordView key={s.tool_id} ownerId={ownerId} s={s} live={live} />)}
              {pending.length === 0 && records.length === 0 && (
                <div>
                  <h2 className="text-[2.1rem] font-semibold leading-[1.05]">Nothing happens until you say yes</h2>
                  <p className="mt-3 text-lg text-white/90">
                    {live
                      ? "Pick a job and press Set it up. We will show you exactly what we would do, and wait for your OK."
                      : "Setup runs in a live session. We show you exactly what we would do, and nothing happens until you approve it."}
                  </p>
                </div>
              )}
            </div>
          </div>
        </>
      );
    }
    // helpers
    return (
      <>
        <CardBackdrop src={null} />
        <div className="relative h-full flex flex-col p-5 sm:p-6">
          <div><Pill>Free local help</Pill></div>
          <div className="mt-auto min-h-0 overflow-y-auto -mx-1 px-1 pt-1">
            <h2 className="text-[2.1rem] font-semibold text-white leading-[1.05]">Prefer a person?</h2>
            <p className="mt-1 text-lg text-white/90">Free help in Maryland.</p>
            <ul className="mt-3 grid gap-2">
              {HELPERS.map((h) => (
                <li key={h.name}>
                  <a href={h.url} target="_blank" rel="noopener noreferrer" className="glass-dark block rounded-2xl px-4 py-2.5 no-underline text-white hover:bg-black/60">
                    <span className="block text-lg font-semibold text-accent">{h.name}</span>
                    <span className="block text-base text-white/85 leading-snug">{h.short}</span>
                  </a>
                </li>
              ))}
            </ul>
</div>
          <a href={HELPERS[0].url} target="_blank" rel="noopener noreferrer" className="btn btn-primary mt-3 w-full shrink-0 !min-h-14 text-lg">Find me a local helper</a>
        </div>
      </>
    );
  }

  const current = cards[at];
  const showWorking = active || (!bundle && !loadError);

  return (
    <MotionConfig reducedMotion="user">
      <div data-deck className="mx-auto w-full max-w-[460px] px-4 pt-3 pb-28">
        {offline && live && <div className="mb-4"><OfflineBanner /></div>}

        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="eyebrow truncate">{demo ? "Example business" : "Your business"}</p>
            <h1 className="text-2xl font-semibold mt-0.5 truncate">{profile?.name ?? "Getting to know your business"}</h1>
          </div>
          {bundle && !showWorking && mode === "deck" && (
            <button type="button" className="btn btn-secondary shrink-0 !min-h-12 !px-4" onClick={() => setMode("overview")}>{Icon.grid}See all</button>
          )}
        </div>

        {items.length > 0 && (
          <ul aria-label="At a glance" className="mt-2 grid grid-cols-3 gap-2 text-center">
            <li><span className="block text-[2.3rem] leading-none font-semibold tabular-nums">{items.length}</span><span className="block mt-1 text-base leading-tight text-soft">jobs AI can take on</span></li>
            <li><span className="block text-[2.3rem] leading-none font-semibold tabular-nums">{hours}</span><span className="block mt-1 text-base leading-tight text-soft">hours back each week</span></li>
            <li><span className="block text-[2.3rem] leading-none font-semibold tabular-nums">{catalog.tools.length}</span><span className="block mt-1 text-base leading-tight text-soft">tools we checked</span></li>
          </ul>
        )}
        {!active && lastEvent?.type === "error" && (
          <p role="alert" className="mt-4 rounded-2xl bg-[#3a1d18] px-4 py-3 font-semibold text-brick">{eventLine(lastEvent)}</p>
        )}

        <LayoutGroup>
          {showWorking ? (
            <section aria-live="polite" aria-label="Progress"
              className="relative mt-5 h-[clamp(440px,calc(100dvh-300px),600px)] overflow-hidden rounded-[32px] border border-white/10 shadow-2xl">
              <CardBackdrop src={null} />
              <div className="relative h-full flex flex-col items-center justify-center p-6 text-center">
                <div className="soft-pulse h-20 w-20 rounded-full bg-accent/80 shadow-[0_0_60px_rgba(243,154,76,.6)]" aria-hidden />
                <p className="mt-8 eyebrow !text-white/80">Working on it</p>
                <p className="mt-2 text-2xl font-semibold text-white">{statusLine ? eventLine(statusLine) : "Loading your business..."}</p>
                <p className="mt-3 text-lg text-white/80">This can take a minute or two. You can leave this page open.</p>
              </div>
            </section>
          ) : !bundle ? (
            <div className="card mt-5 p-6">
              <p className="text-lg">We could not load this business page. It may have expired, or our agent may be resting.</p>
              <Link href="/demo" className="btn btn-primary mt-4">See the example businesses</Link>
            </div>
          ) : mode === "overview" ? (
            <section aria-label="All cards" className="mt-5">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold">Everything at a glance</h2>
                <button type="button" className="btn btn-secondary !min-h-12" onClick={() => setMode("deck")}>Back</button>
              </div>
              <ol className="mt-3 grid gap-3">
                {cards.map((c, i) => (
                  <li key={c.key}>
                    <motion.button layoutId={c.key} transition={spring} type="button"
                      data-testid={c.kind === "job" ? "need-item" : undefined}
                      onClick={() => { go(i); setMode("deck"); window.scrollTo({ top: 0 }); }}
                      className={`relative w-full overflow-hidden rounded-[22px] border text-left ${i === at ? "border-accent" : "border-white/10"}`}>
                      <CardBackdrop src={cardSrc(c)} still />
                      <span className="relative flex min-h-[88px] items-center justify-between gap-3 px-5 py-3">
                        <span>
                          <span className="block text-xl font-semibold text-white leading-tight">{cardTitle(c)}</span>
                          <span className="block text-base text-white/85">{cardSub(c)}</span>
                        </span>
                        <span className="shrink-0 text-base font-semibold text-accent">Open</span>
                      </span>
                    </motion.button>
                  </li>
                ))}
              </ol>
            </section>
          ) : current ? (
            <section aria-label="Your cards" className="mt-4" onTouchStart={onTouchStart} onTouchMove={onTouchMove}>
              <div className="relative">
                {/* The stacked edge: more cards are waiting behind this one. */}
                {at < cards.length - 1 && <div aria-hidden className="absolute inset-x-5 -bottom-3 h-12 rounded-b-[28px] bg-[#2b2724] border border-white/10" />}
                {at < cards.length - 2 && <div aria-hidden className="absolute inset-x-10 -bottom-6 h-12 rounded-b-[24px] bg-[#211e1c] border border-white/5" />}
                <AnimatePresence initial={false} mode="popLayout" custom={dir}>
                  <motion.article
                    key={current.key}
                    layoutId={current.key}
                    custom={dir}
                    variants={{
                      enter: (d: number) => ({ x: d * 60, opacity: 0, scale: 0.97 }),
                      center: { x: 0, opacity: 1, scale: 1 },
                      exit: (d: number) => ({ x: d * -320, opacity: 0, rotate: d * -4 }),
                    }}
                    initial="enter" animate="center" exit="exit"
                    transition={spring}
                    drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={0.7} onDragEnd={onDragEnd}
                    aria-roledescription="card" aria-label={`${cardTitle(current)}, ${at + 1} of ${cards.length}`}
                    className="relative h-[clamp(480px,calc(100dvh-318px),640px)] sm:h-[clamp(480px,calc(100dvh-380px),600px)] overflow-hidden rounded-[32px] border border-white/10 bg-[#1f1d1b] shadow-2xl touch-pan-y"
                  >
                    {renderCard(current)}
                  </motion.article>
                </AnimatePresence>
              </div>
              <div className="mt-6 flex items-center gap-4 pr-32">
                <button type="button" className="btn btn-secondary !min-h-12 !px-5" disabled={at === 0} onClick={() => go(at - 1)}>Back</button>
                <p className="text-lg font-semibold tabular-nums" aria-live="polite">{at + 1} of {cards.length}</p>
              </div>
              <p className="mt-2 text-base text-soft pr-32 sm:hidden">Swipe left for the next card, right to go back.</p>
              <p className="mt-2 text-base text-soft hidden sm:block">Use the left and right arrow keys to move between cards.</p>
            </section>
          ) : null}
        </LayoutGroup>

        {lastReply && !active && live && (
          <ul aria-label="Our latest reply" className="mt-5">
            <li className="rounded-2xl rounded-tl-md bg-[#2a2622] border border-white/10 px-4 py-3">
              <span className="block text-sm font-semibold text-accent">MainStreet:</span>
              <button type="button" onClick={() => setSheet({ kind: "chat" })} className="block w-full text-left text-lg line-clamp-4 whitespace-pre-line">{lastReply.text}</button>
            </li>
          </ul>
        )}
      </div>

      <button type="button" onClick={() => setSheet({ kind: "chat" })} aria-label="Ask us a question"
        className="fixed bottom-5 right-5 z-40 flex h-16 items-center gap-2 rounded-full bg-[#2c2825] border border-white/15 px-5 text-lg font-semibold text-white shadow-2xl hover:bg-[#383330]">
        {Icon.chat}<span>Ask us</span>
      </button>

      <AnimatePresence>
        {sheet?.kind === "compare" && (
          <Sheet key="compare" title={`Tools for ${sheet.need.title.toLowerCase()}`} onClose={closeSheet}>
            <div className="grid gap-4">
              {(bundle?.compares[sheet.need.need_id]?.options ?? []).map((o) => {
                const tool = toolById(o.tool_id);
                return tool ? <ToolCard key={o.tool_id} tool={tool} option={o} uses={profile?.uses}
                  recommended={o.tool_id === bundle?.compares[sheet.need.need_id]?.recommended_tool_id} /> : null;
              })}
            </div>
          </Sheet>
        )}
        {sheet?.kind === "trust" && (
          <Sheet key="trust" title={`Why we trust ${sheet.tool.name}`} onClose={closeSheet}>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <BadgePill badge={sheet.tool.trust.badge} /><span className="font-semibold">{sheet.tool.trust.score} out of 100</span>
            </div>
            <p className="text-soft mb-3">We check six things before we list a tool, and a person signs off. Each line links to what we found.</p>
            <TrustBreakdown trust={sheet.tool.trust} />
            <Link href={`/tool/${sheet.tool.id}`} className="mt-4 inline-block">See full details</Link>
          </Sheet>
        )}
        {sheet?.kind === "preview" && (
          <Sheet key="preview" title={`See ${sheet.name} at work`} onClose={closeSheet} full>
            <figure className="flex h-full flex-col">
              <video src={previewSrc(sheet.preview) ?? undefined} autoPlay muted controls playsInline loop
                className="w-full flex-1 min-h-0 rounded-2xl bg-black object-contain" />
              <figcaption className="mt-3 text-lg font-semibold">AI-generated preview of how {sheet.name} would work in your business</figcaption>
            </figure>
          </Sheet>
        )}
        {sheet?.kind === "chat" && (
          <Sheet key="chat" title="Ask us anything" onClose={closeSheet} full>
            {live ? (
              <div className="grid gap-4">
                <TurnLog events={events} active={active} />
                <ChatBox messages={bundle?.messages ?? []} suggestions={suggestions} onSend={send} disabled={offline} />
              </div>
            ) : (
              <div className="grid gap-4">
                <p className="text-soft">This is an example, so you cannot ask questions here. In a live session you can ask anything, or tell us what we got wrong.</p>
                {(bundle?.messages.length ?? 0) > 0 && (
                  <ul className="grid gap-3" aria-label="Conversation">
                    {bundle!.messages.map((m, i) => (
                      <li key={i} className={`whitespace-pre-line rounded-2xl px-4 py-2 max-w-[92%] ${m.role === "owner" ? "bg-accent-tint ml-auto" : "bg-grey-tint"}`}>
                        <span className="sr-only">{m.role === "owner" ? "You: " : "MainStreet: "}</span>{m.text}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Sheet>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
