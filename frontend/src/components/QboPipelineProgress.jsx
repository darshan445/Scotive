"use client";
import { Loader2 } from "lucide-react";
import { SiQuickbooks } from "react-icons/si";

/**
 * Sticky dashboard progress while QBO conversation match + status re-eval runs
 * in the background (does not block Next / import).
 */
export function QboPipelineProgress({ pipeline }) {
    if (!pipeline) return null;
    const status = pipeline.status;
    if (status !== "queued" && status !== "running") return null;

    const total = Number(pipeline.total || 0);
    const examined = Number(pipeline.examined || 0);
    const matched = Number(pipeline.matched || 0);
    const phase = pipeline.phase || "matching";

    let detail = "Starting…";
    if (phase === "deciding_status") {
        detail = matched
            ? `Updating status from Gmail for ${matched} matched invoice${matched === 1 ? "" : "s"}…`
            : "Updating invoice status from Gmail…";
    } else if (total > 0) {
        detail = `Checking conversations · ${examined} of ${total}`;
        if (matched > 0) {
            detail += ` · ${matched} thread${matched === 1 ? "" : "s"} found`;
        }
    } else if (phase === "matching" || status === "running") {
        detail = "Finding Gmail conversations for QuickBooks invoices…";
    }

    const pct = total > 0 ? Math.min(100, Math.round((examined / total) * 100)) : null;

    return (
        <div
            className="rounded-xl border border-border bg-card px-4 py-4 space-y-3"
            data-testid="qbo-pipeline-progress"
            role="status"
            aria-live="polite"
        >
            <div className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-muted border border-border flex-shrink-0">
                    <SiQuickbooks className="w-5 h-5 text-[#2CA01C]" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-heading font-semibold text-foreground">
                        <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
                        Syncing QuickBooks with Gmail
                    </div>
                    <div className="text-sm text-muted-foreground mt-0.5">{detail}</div>
                </div>
            </div>
            {pct != null ? (
                <div className="h-1.5 rounded-full bg-muted overflow-hidden" data-testid="qbo-pipeline-bar">
                    <div
                        className="h-full bg-[#2CA01C]/80 transition-[width] duration-500 ease-out"
                        style={{ width: `${pct}%` }}
                    />
                </div>
            ) : null}
        </div>
    );
}
