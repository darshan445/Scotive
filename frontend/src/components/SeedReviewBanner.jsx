"use client";
import { Mail } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Sticky dashboard banner for deferred Gmail seed review (QBO→dashboard path).
 * Only shown when seed finished with Gmail leftovers — not while scanning.
 */
export function SeedReviewBanner({
    pendingCount = 0,
    reviewing = false,
    busy = false,
    onReview,
    onDiscard,
}) {
    if (pendingCount <= 0) return null;

    return (
        <div
            className="rounded-xl border border-border bg-card px-4 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            data-testid="seed-review-banner"
            role="status"
        >
            <div className="flex items-start gap-3 min-w-0">
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-muted border border-border flex-shrink-0">
                    <Mail className="w-4 h-4 text-foreground" />
                </span>
                <div className="min-w-0">
                    <div className="text-sm font-heading font-semibold text-foreground">
                        We found {pendingCount} invoice{pendingCount === 1 ? "" : "s"} in Gmail
                    </div>
                    <div className="text-sm text-muted-foreground mt-0.5">
                        Review which are still unpaid, or discard to skip.
                    </div>
                </div>
            </div>
            {!reviewing ? (
                <div className="flex items-center gap-2 flex-shrink-0">
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={onDiscard}
                        data-testid="seed-review-discard"
                    >
                        Discard
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        disabled={busy}
                        onClick={onReview}
                        data-testid="seed-review-confirm"
                    >
                        Review &amp; confirm
                    </Button>
                </div>
            ) : null}
        </div>
    );
}
