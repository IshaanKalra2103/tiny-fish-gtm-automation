export type BusinessType = "restaurant" | "coffee_shop" | "hvac" | "landscaping" | "salon" | "other";
export type NeedId =
  | "missed-calls" | "reviews" | "social-posts" | "booking" | "website-chat"
  | "books" | "marketing-msgs" | "quotes" | "menu-inventory";
export type Integration =
  | "square" | "toast" | "clover" | "google_business" | "quickbooks" | "facebook"
  | "instagram" | "yelp" | "gmail" | "outlook" | "website" | "sms";
export type Badge = "verified" | "caution" | "unknown";

export interface Price {
  free_plan: boolean;
  from_usd_month?: number | null;
  pricing_url?: string | null;
  notes: string;
}
export interface ToolSetup {
  minutes: number;
  difficulty: "easy" | "medium" | "hard";
  agent_setup: boolean;
  playbook?: string | null;
}
export interface Signal {
  points: number;
  max: number;
  value: string;
  evidence_url?: string | null;
}
export interface Trust {
  score: number;
  badge: Badge;
  signals: Record<string, Signal>;
}
export interface SimTest {
  score: number;
  persona: string;
  task: string;
  notes: string;
  label: "simulated";
}
export interface Tool {
  id: string;
  name: string;
  vendor: string;
  url: string;
  need_ids: NeedId[];
  business_types: BusinessType[];
  what_it_does: string;
  price: Price;
  setup: ToolSetup;
  integrations: Integration[];
  trust: Trust;
  sim_test?: SimTest | null;
  sources: string[];
  status: "approved" | "pending" | "rejected";
  reviewed_by?: string | null;
  reviewed_at?: string | null;
}
export interface Profile {
  name: string;
  business_type: BusinessType;
  city: string;
  state: string;
  size: string;
  website?: string | null;
  uses: Integration[];
  pains: string[];
  summary: string;
}
export interface NeedItem {
  need_id: NeedId;
  title: string;
  why: string;
  est_hours_saved_week: number;
}
export interface Needs {
  items: NeedItem[];
}
export interface CompareOption {
  tool_id: string;
  fit_sentence: string;
  works_with: Integration[];
}
export interface Compare {
  need_id: NeedId;
  options: CompareOption[];
  recommended_tool_id: string;
}
export interface Preview {
  tool_id: string;
  prompt: string;
  status: "completed" | "failed" | "capped";
  video_file?: string | null;
  cost_usd: number;
}
export interface SetupRecord {
  tool_id: string;
  status: "planned" | "awaiting_approval" | "running" | "needs_owner" | "done" | "failed";
  approval_id?: string | null;
  run_id?: string | null;
  streaming_url?: string | null;
  inbox?: string | null;
  login_url?: string | null;
  username?: string | null;
  password?: string | null;
  configured: string[];
  next_steps: string[];
  handoff_reason?: string | null;
}
export interface Approval {
  id: string;
  tool_id: string;
  summary: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decided_at?: string | null;
}
export interface CatalogNeed {
  id: NeedId;
  title: string;
  plain: string;
}
export interface Catalog {
  version: number;
  generated_at: string;
  needs: CatalogNeed[];
  type_needs: Record<string, NeedId[]>;
  tools: Tool[];
}
export interface Message {
  role: "owner" | "agent";
  text: string;
  channel: "web" | "imessage";
  at: string;
}
export interface OwnerBundle {
  owner_id: string;
  source: string;
  profile: Profile | null;
  needs: Needs | null;
  compares: Record<string, Compare>;
  previews: Record<string, Preview & { video_url: string | null }>;
  setups: Record<string, SetupRecord & { has_password: boolean }>;
  approvals: Approval[];
  messages: Message[];
  active_turn?: string | null;
}
export type TurnEvent =
  | { type: "queued"; position: number }
  | { type: "status"; text: string }
  | { type: "files"; kinds: string[] }
  | { type: "done"; reply: string }
  | { type: "error"; message: string };
