"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function RefreshArrangementReviews() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button type="button" disabled={pending} onClick={() => startTransition(() => router.refresh())}
      className="min-h-11 rounded-lg border border-[#cfd9d4] px-4 py-2 text-sm font-semibold text-[#0f6b5b] disabled:opacity-60">
      {pending ? "Refreshing…" : "Refresh reviews"}
    </button>
  );
}
