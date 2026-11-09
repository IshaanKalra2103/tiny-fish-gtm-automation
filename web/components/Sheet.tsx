"use client";
import { useEffect, useRef } from "react";
import { motion } from "motion/react";

/** A bottom sheet: slides up over a dim backdrop, closes on Escape, the Close button or a tap outside. */
export default function Sheet({ title, onClose, children, full = false }: {
  title: string; onClose: () => void; children: React.ReactNode; full?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <motion.div className="absolute inset-0 bg-black/30" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} />
      <motion.div
        ref={panel}
        role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}
        className={`relative w-full max-w-[560px] bg-white border border-line rounded-t-[28px] shadow-2xl outline-none flex flex-col ${full ? "h-[94dvh]" : "max-h-[88dvh]"}`}
        initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
        transition={{ type: "spring", stiffness: 380, damping: 38 }}
      >
        <div className="mx-auto mt-2.5 h-1.5 w-12 rounded-full bg-ink/15" aria-hidden />
        <div className="flex items-center justify-between gap-4 px-5 pt-2 pb-3">
          <h2 className="text-2xl font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="btn btn-secondary !min-h-11 !px-5">Close</button>
        </div>
        <div className="overflow-y-auto px-5 pb-8 flex-1">{children}</div>
      </motion.div>
    </div>
  );
}
