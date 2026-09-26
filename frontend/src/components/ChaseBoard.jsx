"use client";
import { useMemo } from "react";
import Link from "next/link";
import { ExternalLink, Play } from "lucide-react";
import { InvoiceOverflowMenu, resumeInvoiceTracking } from "@/components/InvoiceOverflowMenu";
import { CheckBackControl } from "@/components/WaitUntilControl";
import { Button } from "@/components/ui/button";
import { formatMoney, formatOpenTotals } from "@/components/LedgerCard";
import { historyLedgerInvoices, historyLedgerSummary, outstandingBalance } from "@/lib/ledgerInvoices";
import {
    cadenceLine,
    dueMeta,
    gmailSearchUrl,
    invoiceNumber,
    latestActivity,
    needsYouInvoices,
    remainingLabel,
    stoppedInvoices,
    stoppedOnLabel,
    watchingInvoices,
    autoReminderInvoices,
} from "@/lib/chase";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";

function ClientCell({ inv }) {
    const name = inv.counterparty_name || inv.counterparty_email || "Unknown";
    return (
        <div className="min-w-[132px]">
            <Link
                href={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
                onClick={(e) => e.stopPropagation()}
                className="text-sm font-semibold text-foreground hover:underline"
                data-testid="ledger-client-link"
            >
                {name}
            </Link>
        </div>
    );
}

function DueCell({ inv }) {
    const meta = dueMeta(inv);
    const tone =
        meta.tone === "rose"
            ? "text-rose-600"
            : meta.tone === "amber"
              ? "text-amber-700"
              : "text-muted-foreground";
    return (
        <div className="min-w-[88px]">
            <div className="text-sm tabular-nums">{meta.due}</div>
            {meta.relative ? <div className={`text-[11px] mt-0.5 ${tone}`}>{meta.relative}</div> : null}
        </div>
    );
}

function AmountCell({ inv }) {
    const left = remainingLabel(inv);
    return (
        <div className="text-right">
            <div className="text-sm font-medium tabular-nums">{formatMoney(inv.amount, inv.currency || "USD")}</div>
            {left ? <div className="text-[11px] text-emerald-700 mt-0.5">{left}</div> : null}
        </div>
    );
}

function StoryCell({ inv, watching }) {
    const line = watching ? cadenceLine(inv) : latestActivity(inv);
    return (
        <div className="min-w-[220px] max-w-[380px]" data-testid={watching ? "chase-cadence" : "chase-activity"}>
            <div className="text-sm font-medium text-foreground leading-snug">{line.title}</div>
            {line.quote ? (
                <div className="mt-0.5 text-[12px] leading-snug text-muted-foreground italic line-clamp-2">
                    “{line.quote}”
                </div>
            ) : line.detail ? (
                <div className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{line.detail}</div>
            ) : null}
        </div>
    );
}

function NeedsYouActions({ inv, onReview }) {
    return (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
            <Button size="sm" onClick={() => onReview(inv)} data-testid="ledger-follow-up">
                Review
            </Button>
        </div>
    );
}

function StoppedActions({ inv, onChanged }) {
    const url = gmailThreadUrl(inv.source_thread_id);
    return (
        <div className="flex flex-nowrap items-center justify-end gap-1.5 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
            <CheckBackControl
                invoice={inv}
                label="Check back"
                testId="restart-chasing"
                onChanged={onChanged}
            />
            {url ? (
                <Button size="sm" variant="ghost" asChild data-testid="view-gmail-thread">
                    <a href={url} target="_blank" rel="noopener noreferrer">
                        View in Gmail <ExternalLink className="w-3 h-3 ml-1" />
                    </a>
                </Button>
            ) : null}
        </div>
    );
}

function WatchingActions({ inv, onChanged }) {
    return (
        <div className="flex flex-nowrap items-center justify-end gap-1.5 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
            <CheckBackControl invoice={inv} label="Edit date" defaultDate={inv.expected_pay_date} onChanged={onChanged} />
            <Button
                size="sm"
                variant="outline"
                onClick={() => resumeInvoiceTracking(inv._id, { onChanged })}
                data-testid="ledger-resume-tracking"
            >
                <Play className="w-3.5 h-3.5 mr-1" />
                Resume
            </Button>
            <InvoiceOverflowMenu invoice={inv} onChanged={onChanged} />
        </div>
    );
}

function AutoReminderActions({ inv, onChanged }) {
    const search = inv.unmatched ? gmailSearchUrl(inv.invoice_ref) : null;
    return (
        <div className="flex flex-nowrap items-center justify-end gap-1.5 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
            {search ? (
                <Button size="sm" variant="outline" asChild data-testid="match-thread">
                    <a href={search} target="_blank" rel="noopener noreferrer">
                        Match thread <ExternalLink className="w-3 h-3 ml-1" />
                    </a>
                </Button>
            ) : null}
            <InvoiceOverflowMenu invoice={inv} onChanged={onChanged} />
        </div>
    );
}

function settledDate(inv) {
    if (!inv.paid_at) return "—";
    try {
        return new Date(inv.paid_at).toLocaleDateString(undefined, { day: "numeric", month: "short" });
    } catch {
        return "—";
    }
}

function settledStatus(inv) {
    if (inv.books_status === "voided") return "Voided";
    if (inv.paid_via === "quickbooks") return "Paid via QBO";
    if (inv.paid_via === "manual") return "Marked paid";
    return inv.chase_result || "Paid";
}

function PaidActions({ inv }) {
    const url = gmailThreadUrl(inv.source_thread_id);
    if (!url) return null;
    return (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
            <Button size="sm" variant="ghost" asChild data-testid="view-gmail-thread">
                <a href={url} target="_blank" rel="noopener noreferrer">
                    View thread in Gmail <ExternalLink className="w-3 h-3 ml-1" />
                </a>
            </Button>
        </div>
    );
}

function ChaseRow({ inv, variant, onChanged, onReview }) {
    const onClock = variant === "watching" || variant === "auto_reminders";
    const line = onClock ? cadenceLine(inv) : null;
    const rowTone =
        variant === "needs_you"
            ? "border-l-[3px] border-l-rose-500"
            : variant === "stopped"
              ? "border-l-[3px] border-l-stone-400"
              : variant === "watching"
                ? "border-l-[3px] border-l-sky-400"
                : line?.state === "unmatched"
                  ? "border-l-[3px] border-l-amber-400"
                  : "border-l-[3px] border-l-transparent";
    return (
        <tr
            className={`border-b border-border/70 hover:bg-muted/30 transition-colors ${variant === "needs_you" ? "cursor-pointer" : ""} ${rowTone}`}
            onClick={() => (variant === "needs_you" ? onReview?.(inv) : null)}
            data-testid={variant === "stopped" ? "ledger-row-stopped" : "ledger-row"}
        >
            <td className="px-4 py-3.5 align-middle">
                <ClientCell inv={inv} />
            </td>
            <td className="px-4 py-3.5 align-middle">
                <div className="text-sm font-medium tabular-nums" data-testid="ledger-subject">
                    {invoiceNumber(inv)}
                </div>
            </td>
            {variant === "paid" ? (
                <>
                    <td className="px-4 py-3.5 align-middle text-right">
                        <AmountCell inv={inv} />
                    </td>
                    <td className="px-4 py-3.5 align-middle text-sm tabular-nums" data-testid="paid-settled-date">
                        {settledDate(inv)}
                    </td>
                    <td className="px-4 py-3.5 align-middle text-sm text-muted-foreground" data-testid="paid-settled-status">
                        {settledStatus(inv)}
                    </td>
                    <td className="px-3 py-3.5 align-middle">
                        <PaidActions inv={inv} />
                    </td>
                </>
            ) : variant === "stopped" ? (
                <>
                    <td className="px-4 py-3.5 align-middle text-right">
                        <AmountCell inv={inv} />
                    </td>
                    <td className="px-4 py-3.5 align-middle text-sm text-muted-foreground" data-testid="stopped-on">
                        {stoppedOnLabel(inv)}
                    </td>
                    <td className="px-3 py-3.5 align-middle whitespace-nowrap">
                        <StoppedActions inv={inv} onChanged={onChanged} />
                    </td>
                </>
            ) : (
                <>
                    <td className="px-4 py-3.5 align-middle">
                        <DueCell inv={inv} />
                    </td>
                    <td className="px-4 py-3.5 align-middle">
                        <AmountCell inv={inv} />
                    </td>
                    <td className="px-4 py-3.5 align-middle">
                        <StoryCell inv={inv} watching={onClock} />
                    </td>
                    <td className="px-3 py-3.5 align-middle whitespace-nowrap">
                        {variant === "watching" ? (
                            <WatchingActions inv={inv} onChanged={onChanged} />
                        ) : variant === "auto_reminders" ? (
                            <AutoReminderActions inv={inv} onChanged={onChanged} />
                        ) : (
                            <NeedsYouActions inv={inv} onReview={onReview} />
                        )}
                    </td>
                </>
            )}
        </tr>
    );
}

const COPY = {
    needs_you: {
        emptyTitle: "Nothing needs you",
        emptyBody: "A client reply, a check-back date that came due, or a Firm email to approve lands here.",
        columns: ["Client", "Invoice", "Due", "Amount", "Latest activity", ""],
    },
    watching: {
        emptyTitle: "Nothing you're watching",
        emptyBody: "When you pick a check-back date, the invoice waits here until that day — or until they reply.",
        columns: ["Client", "Invoice", "Due", "Amount", "Status", ""],
    },
    auto_reminders: {
        emptyTitle: "No automatic reminders running",
        emptyBody: "Silent invoices sit here while Friendly reminders send from your inbox. You don't need to touch them.",
        columns: ["Client", "Invoice", "Due", "Amount", "Status", ""],
    },
    stopped: {
        emptyTitle: "Nothing stopped",
        emptyBody: "Stop chasing when a thread is going to court or was handled offline. Pick a date when you want Scotive to check back.",
        columns: ["Client", "Invoice", "Amount", "Stopped", ""],
    },
    paid: {
        emptyTitle: "Nothing collected yet",
        emptyBody: "When QuickBooks hits $0, the chase ends and the row archives here.",
        columns: ["Client", "Invoice", "Amount", "Date settled", "Status", ""],
    },
};

export function ChaseBoard({ ledger, variant, onChanged, onReview }) {
    const all = ledger?.invoices ?? [];
    const invoices = useMemo(() => {
        if (variant === "paid") return historyLedgerInvoices(all);
        if (variant === "watching") return watchingInvoices(all);
        if (variant === "auto_reminders") return autoReminderInvoices(all);
        if (variant === "stopped") return stoppedInvoices(all);
        return needsYouInvoices(all);
    }, [all, variant]);
    const recovered = useMemo(() => historyLedgerSummary(all), [all]);
    const openByCur = useMemo(() => {
        const totals = {};
        for (const inv of invoices) {
            const cur = (inv.currency || "USD").toUpperCase();
            totals[cur] = (totals[cur] || 0) + outstandingBalance(inv);
        }
        return totals;
    }, [invoices]);

    const copy = COPY[variant];

    if (!invoices.length) {
        return (
            <div className="rounded-xl border border-dashed border-border bg-card px-8 py-16 text-center" data-testid="ledger-empty">
                <h3 className="font-heading text-lg">{copy.emptyTitle}</h3>
                <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">{copy.emptyBody}</p>
            </div>
        );
    }

    return (
        <div className="rounded-xl border border-border bg-card overflow-hidden" data-testid={`ledger-card-${variant}`}>
            {variant === "paid" ? (
                <div className="px-5 py-3 border-b border-border flex items-baseline justify-between gap-3 bg-emerald-50/40">
                    <div className="text-xs font-medium text-emerald-900">Total collected</div>
                    <div className="stat-number text-lg font-semibold tabular-nums text-emerald-900" data-testid="ledger-total">
                        {formatOpenTotals(recovered.totalsByCurrency)}
                    </div>
                </div>
            ) : null}
            <table className="w-full">
                <thead>
                    <tr className="border-b border-border bg-muted/40 text-left">
                        {copy.columns.map((col) => (
                            <th
                                key={col || "actions"}
                                className={`px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground ${
                                    col === "Amount" ? "text-right" : ""
                                } ${col === "" ? "w-[1%] whitespace-nowrap" : ""}`}
                            >
                                {col || <span className="sr-only">Actions</span>}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {invoices.map((inv) => (
                        <ChaseRow
                            key={inv._id}
                            inv={inv}
                            variant={variant}
                            onChanged={onChanged}
                            onReview={onReview}
                        />
                    ))}
                </tbody>
            </table>
            {variant !== "paid" ? (
                <div className="px-5 py-2.5 text-[11px] text-muted-foreground border-t border-border bg-muted/20">
                    {invoices.length} invoice{invoices.length === 1 ? "" : "s"} · {formatOpenTotals(openByCur)}
                </div>
            ) : null}
        </div>
    );
}
