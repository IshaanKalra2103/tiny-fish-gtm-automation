import raw from "@/data/catalog.json";
import type { Catalog, CatalogNeed, Tool, BusinessType } from "./types";

export const catalog = raw as unknown as Catalog;

export const toolById = (id: string): Tool | undefined => catalog.tools.find((t) => t.id === id);
export const needById = (id: string): CatalogNeed | undefined => catalog.needs.find((n) => n.id === id);
export const toolsFor = (need: string, type?: BusinessType | string): Tool[] =>
  catalog.tools.filter(
    (t) =>
      t.status === "approved" &&
      t.need_ids.includes(need as never) &&
      (!type || t.business_types.includes(type as BusinessType)),
  );

export const BUSINESS_TYPE_LABELS: Record<string, string> = {
  restaurant: "Restaurant",
  coffee_shop: "Coffee shop",
  hvac: "HVAC",
  landscaping: "Landscaping",
  salon: "Salon",
  other: "Other",
};
export const INTEGRATION_LABELS: Record<string, string> = {
  square: "Square", toast: "Toast", clover: "Clover", google_business: "Google Business Profile",
  quickbooks: "QuickBooks", facebook: "Facebook", instagram: "Instagram", yelp: "Yelp",
  gmail: "Gmail", outlook: "Outlook", website: "Your website", sms: "Text messages",
};
export const SIGNAL_LABELS: Record<string, string> = {
  identity: "Who is behind it",
  longevity: "How long it has been around",
  data_handling: "How it handles your data",
  pricing_transparency: "Honest pricing",
  independent_reviews: "Independent reviews",
  viability: "Likely to be around next year",
};
export const priceLabel = (t: Tool): string =>
  t.price.free_plan ? "Free plan" : t.price.from_usd_month != null ? `from $${t.price.from_usd_month}/mo` : "Ask for a price";
