"use client";
import { useState } from "react";
import type { Message } from "@/lib/types";
import { ApiError } from "@/lib/api";

export default function ChatBox({
  messages, suggestions, onSend, disabled,
}: {
  messages: Message[];
  suggestions: { label: string; text: string }[];
  onSend: (text: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async (t: string) => {
    if (!t.trim() || busy) return;
    setBusy(true); setError("");
    try {
      await onSend(t.trim()); setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We could not reach our agent just now. Please try again in a minute.");
    } finally { setBusy(false); }
  };
  return (
    <div className="card p-5 sm:p-6">
      {messages.length > 0 && (
        <ul className="grid gap-3 mb-5 max-h-96 overflow-y-auto" aria-label="Conversation">
          {messages.map((m, i) => (
            <li key={i} className={`whitespace-pre-line rounded-lg px-4 py-2 max-w-[92%] ${m.role === "owner" ? "bg-accent-tint ml-auto" : "bg-grey-tint"}`}>
              <span className="sr-only">{m.role === "owner" ? "You: " : "MainStreet: "}</span>{m.text}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2 mb-4">
        {suggestions.map((s) => (
          <button key={s.label} type="button" className="btn btn-secondary" disabled={disabled || busy} onClick={() => send(s.text)}>
            {s.label}
          </button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label htmlFor="chat-input" className="sr-only">Ask a follow-up</label>
        <input id="chat-input" className="field" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Ask a follow-up question" disabled={disabled || busy} />
        <button className="btn btn-primary" disabled={disabled || busy || !text.trim()}>{busy ? "Sending..." : "Send"}</button>
      </form>
      {error && <p role="alert" className="mt-3 text-brick font-semibold">{error}</p>}
    </div>
  );
}
