// Client-safe venue-block constants and types (SCRUM-23): no import of ./api,
// ./auth or anything that touches next/headers, so the "use client" block form
// can import them, following lib/venue-options.ts.
import type { Slot } from "./venue-options";

export const BLOCK_REASONS = ["maintenance", "renovation", "safety", "internal_use"] as const;
export type BlockReason = (typeof BLOCK_REASONS)[number];

// Matches venueService's VenueBlockCreate.reason_detail limit.
export const REASON_DETAIL_MAX = 1000;

export interface VenueBlock {
  id: string;
  venue_id: string;
  start_date: string;
  end_date: string;
  // SCRUM-65: the blocked time on each date; slots are what it touches.
  start_minute: number;
  end_minute: number;
  slots: Slot[];
  reason_category: BlockReason;
  reason_detail: string | null;
  status: "active" | "lifted";
  created_by: string;
  created_at: string;
}

export function reasonLabel(reason: BlockReason): string {
  const words = reason.replace("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// "Maintenance — Air-con repairs", or just "Safety" when there is no detail.
export function blockReasonText(block: Pick<VenueBlock, "reason_category" | "reason_detail">): string {
  const label = reasonLabel(block.reason_category);
  return block.reason_detail ? `${label} — ${block.reason_detail}` : label;
}
