import { execFileSync } from "node:child_process";
import OpenAI from "openai";

export type Turn = { role: "user" | "assistant"; content: string };

const MODEL = process.env.OPENAI_MODEL ?? "gpt-5.6-luna";

const INSTRUCTIONS = `You're texting over iMessage as the assistant for a small growth team building an AI GTM automation machine on TinyFish (trend research, content templates, short-form video, persona QA, publishing).

Write like a real person texting: short, casual, lowercase is fine. No markdown, bullet points or headings. Usually one or two sentences. If you have more to say, split it into at most 3 separate texts with a blank line between them.
Match the other person's tone and language. Use emoji rarely.
Be useful: answer directly, and ask a quick follow-up when it helps.
You can't run campaigns, research trends, make videos or publish anything yet; that's still being wired up. If asked, say it's coming soon instead of pretending.
If someone sincerely asks whether you're a human or an AI, tell them you're an AI assistant.`;

// Temporary: falls back to the macOS Keychain until the key moves into .env.
function apiKey(): string {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY;
  return execFileSync(
    "security",
    ["find-generic-password", "-s", "OPENAI_API_KEY", "-a", "OPENAI_PERSONAL", "-w"],
    { encoding: "utf8" },
  ).trim();
}

const client = new OpenAI({ apiKey: apiKey() });

// Returns the reply split into separate texts (bubbles).
export async function reply(history: Turn[]): Promise<string[]> {
  const request = { model: MODEL, instructions: INSTRUCTIONS, input: history };
  const response = await client.responses
    .create({ ...request, reasoning: { effort: "none" } })
    .catch((err) => {
      // Not every model accepts effort "none"; fall back to the model's default.
      if (err instanceof OpenAI.BadRequestError && err.param?.startsWith("reasoning")) {
        return client.responses.create(request);
      }
      throw err;
    });
  return response.output_text
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 3);
}
