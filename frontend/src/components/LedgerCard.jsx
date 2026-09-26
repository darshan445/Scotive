"use client";
import { useMemo, Fragment, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Send } from "lucide-react";
import { InvoiceOverflowMenu, resumeInvoiceTracking } from "@/components/InvoiceOverflowMenu";
import { AddDueDateButton, NO_DUE_DATE_LABEL } from "@/components/AddDueDateButton";
import { WaitUntilControl } from "@/components/WaitUntilControl";
import { Button } from "@/components/ui/button";
import { LedgerCardSkeleton } from "@/components/PageSkeletons";
import {
    historyLedgerInvoices,
    historyLedgerSummary,
    groupInvoicesByClient,
    outstandingBalance,
} from "@/lib/ledgerInvoices";
import {
    chaseReason,
    followUpLabel,
    invoiceBucket,
    isSleepingInvoice,
    needsYouInvoices,
    remainingLabel,
    watchingInvoices,
    stoppedInvoices,
    BUCKETS,
} from "@/lib/chase";
import { invoiceSubject, isJunkInvoiceRef } from "@/lib/invoiceCopy";
import { navigateToInvoice } from "@/lib/invoiceNavigation";

export function formatMoney(n, currency = "USD") {
    if (n == null) return "—";
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(n));
    } catch { return `$${Number(n).toFixed(2)}`; }
}

export function formatOpenTotals(totalsByCurrency) {
    if (totalsByCurrency == null) return formatMoney(0);
    if (typeof totalsByCurrency === "number") return formatMoney(totalsByCurrency);
    const entries = Object.entries(totalsByCurrency).filter(([, v]) => Number(v) > 0);
    if (entries.length === 0) return formatMoney(0);
    return entries.map(([cur, amt]) => formatMoney(amt, cur)).join(" + ");
}

export { NO_DUE_DATE_LABEL };

export function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return iso; }
}

function RowActions({ inv, variant, onChanged, onFollowUp }) {
    const bucket = invoiceBucket(inv);
    if (variant === "paid") return null;
    return (
        <div className="flex flex-wrap items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
            {bucket === BUCKETS.needs_you ? (
                <>
                    <Button size="sm" onClick={() => onFollowUp(inv)} data-testid="ledger-follow-up">
                        <Send className="w-3.5 h-3.5 mr-1" />
                        {followUpLabel(inv)}
                    </Button>
                    <WaitUntilControl invoice={inv} onChanged={onChanged} compact />
                    <Button size="sm" variant="ghost" onClick={() => resumeInvoiceTracking(inv._id, { onChanged })} data-testid="ledger-resume">
                        Resume
                    </Button>
                </>
            ) : null}
            {bucket === BUCKETS.stopped ? (
                <Button size="sm" variant="outline" onClick={() => resumeInvoiceTracking(inv._id, { onChanged })} data-testid="ledger-resume-tracking">
                    Resume cadence
                </Button>
            ) : null}
            {bucket === BUCKETS.watching && isSleepingInvoice(inv) ? (
                <Button size="sm" variant="ghost" onClick={() => resumeInvoiceTracking(inv._id, { onChanged })} data-testid="ledger-resume-sleep">
                    Resume now
                </Button>
            ) : null}
        </div>
    );
}

export function LedgerCard({ ledger, onChanged, variant = "needs_you", onFollowUp }) {
    const router = useRouter();
    const [groupByClient, setGroupByClient] = useState(false);
    const allInvoices = ledger?.invoices ?? [];
    const isHistory = variant === "paid";
    const isStopped = variant === "stopped";
    const invoices = useMemo(() => {
        if (isHistory) return historyLedgerInvoices(allInvoices);
        if (isStopped) return stoppedInvoices(allInvoices);
        if (variant === "watching") return watchingInvoices(allInvoices);
        return needsYouInvoices(allInvoices);
    }, [allInvoices, isHistory, isStopped, variant]);
    const clientGroups = useMemo(
        () => (!isHistory && groupByClient ? groupInvoicesByClient(invoices) : null),
        [invoices, isHistory, groupByClient],
    );
    const historySummary = useMemo(() => historyLedgerSummary(allInvoices), [allInvoices]);
    const openTotals = useMemo(() => {
        if (isHistory) return historySummary.totalsByCurrency;
        const totals = {};
        for (const inv of invoices) {
            const cur = (inv.currency || "USD").toUpperCase();
            totals[cur] = Math.round(((totals[cur] || 0) + outstandingBalance(inv)) * 100) / 100;
        }
        return totals;
    }, [invoices, isHistory, historySummary.totalsByCurrency]);

    if (!ledger) return <LedgerCardSkeleton />;

    const emptyCopy = {
        needs_you: ["Nothing needs you.", "When a client replies, the invoice lands here. Cadence stays off until you follow up, wait, resume, or stop."],
        watching: ["Nothing you're watching.", "When you pick a check-back date, the invoice waits here until that day — or until they reply."],
        auto_reminders: ["No automatic reminders running.", "Silent invoices sit here while Friendly reminders send from your inbox."],
        paid: ["No paid invoices yet.", "When QuickBooks marks one paid, chase dies and the row moves here."],
        stopped: ["Nothing stopped.", "Stop chasing when a thread is sensitive. You can still send a draft by hand."],
    }[variant] || ["Nothing here.", ""];

    function openInvoice(inv) {
        navigateToInvoice(router, null, inv._id);
    }

    function followUp(inv) {
        if (onFollowUp) onFollowUp(inv);
        else openInvoice(inv);
    }

    return (
        <div className="space-y-6" data-testid={`ledger-card-${variant}`}>
            {invoices.length > 0 ? (
                <div className="surface-card p-6 md:p-7">
                    <div className="eyebrow">
                        {variant === "needs_you" ? "Your move" : variant === "watching" ? "On the clock" : variant === "stopped" ? "Stopped" : "Collected"}
                    </div>
                    <div className="mt-1 flex items-baseline gap-4 flex-wrap">
                        <span className="stat-number font-bold text-4xl md:text-[2.75rem]" data-testid="ledger-total">
                            {isHistory ? formatOpenTotals(openTotals) : invoices.length}
                        </span>
                        <span className="text-muted-foreground text-sm">
                            {isHistory
                                ? `${historySummary.paidCount} paid invoice${historySummary.paidCount === 1 ? "" : "s"}`
                                : `${invoices.length} invoice${invoices.length === 1 ? "" : "s"} · ${formatOpenTotals(openTotals)}`}
                        </span>
                    </div>
                </div>
            ) : null}

            {invoices.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center" data-testid="ledger-empty">
                    <h3 className="font-heading font-semibold text-lg">{emptyCopy[0]}</h3>
                    <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">{emptyCopy[1]}</p>
                </div>
            ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="ledger-table-wrapper">
                    {!isHistory ? (
                        <div className="px-4 py-3 border-b border-border flex justify-end bg-muted/20">
                            <button
                                type="button"
                                onClick={() => setGroupByClient((v) => !v)}
                                className={
                                    groupByClient
                                        ? "h-8 rounded-md px-2.5 text-xs font-semibold border border-foreground bg-foreground text-background"
                                        : "h-8 rounded-md px-2.5 text-xs font-medium border border-border bg-card hover:bg-muted"
                                }
                                data-testid="ledger-group-by-client"
                            >
                                Group by client
                            </button>
                        </div>
                    ) : null}
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border bg-muted/40 text-left">
                                <th className="px-4 py-3 type-label text-muted-foreground">Client</th>
                                <th className="px-4 py-3 type-label text-muted-foreground">Invoice</th>
                                <th className="px-4 py-3 type-label text-muted-foreground text-right">Amount</th>
                                <th className="px-4 py-3 type-label text-muted-foreground">Why</th>
                                <th className="px-4 py-3 type-label text-muted-foreground w-[1%] whitespace-nowrap"><span className="sr-only">Actions</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {(clientGroups || [{ key: "_flat", invoices, name: null }]).map((group) => (
                                <Fragment key={group.key}>
                                    {group.name ? (
                                        <tr className="bg-muted/50 border-b border-border" data-testid="ledger-client-group">
                                            <td colSpan={5} className="px-4 py-2">
                                                <div className="flex items-baseline justify-between gap-3">
                                                    <div className="text-xs font-semibold">
                                                        {group.name}
                                                        <span className="ml-2 font-normal text-muted-foreground">
                                                            · {group.invoices.length}
                                                        </span>
                                                    </div>
                                                    <div className="font-mono tabular-nums text-xs text-muted-foreground">
                                                        {Object.entries(group.subtotals || {})
                                                            .map(([cur, amt]) => formatMoney(amt, cur))
                                                            .join(" + ")}
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : null}
                                    {group.invoices.map((inv) => {
                                        const subject = invoiceSubject(inv);
                                        const ref = (inv.invoice_ref || "").trim();
                                        const reason = chaseReason(inv);
                                        const left = remainingLabel(inv);
                                        return (
                                            <tr
                                                key={inv._id}
                                                className={`border-b border-border/60 hover:bg-muted/30 transition-colors cursor-pointer ${
                                                    invoiceBucket(inv) === BUCKETS.needs_you
                                                        ? "border-l-[3px] border-l-rose-400"
                                                        : isSleepingInvoice(inv)
                                                          ? "border-l-[3px] border-l-sky-300"
                                                          : ""
                                                }`}
                                                onClick={() => openInvoice(inv)}
                                                data-testid="ledger-row"
                                            >
                                                <td className="px-4 py-3 align-top">
                                                    <Link
                                                        href={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
                                                        onClick={(e) => e.stopPropagation()}
                                                        className="text-sm font-medium hover:underline"
                                                        data-testid="ledger-client-link"
                                                    >
                                                        {inv.counterparty_name || inv.counterparty_email || "Unknown"}
                                                    </Link>
                                                    {inv.counterparty_name && inv.counterparty_email ? (
                                                        <div className="text-[11px] font-mono text-muted-foreground break-all max-w-[220px]">{inv.counterparty_email}</div>
                                                    ) : null}
                                                </td>
                                                <td className="px-4 py-3 align-top">
                                                    <div className="text-sm text-foreground break-words whitespace-normal max-w-[280px]" data-testid="ledger-subject">
                                                        {subject}
                                                    </div>
                                                    {ref && !isJunkInvoiceRef(ref) && ref !== subject ? (
                                                        <div className="text-[11px] font-mono text-muted-foreground mt-0.5">{ref}</div>
                                                    ) : null}
                                                </td>
                                                <td className="px-4 py-3 align-top text-right font-mono tabular-nums text-sm">
                                                    <div>{formatMoney(inv.amount, inv.currency || "USD")}</div>
                                                    {left ? (
                                                        <div className="text-[11px] text-emerald-700 mt-0.5">{left}</div>
                                                    ) : null}
                                                </td>
                                                <td className="px-4 py-3 align-top">
                                                    <div className="flex flex-col gap-1 min-w-[200px] max-w-[320px]">
                                                        <div className="text-sm font-medium text-foreground">{reason.title}</div>
                                                        {inv.reason_quote && invoiceBucket(inv) === BUCKETS.needs_you ? (
                                                            <div className="text-[12px] text-muted-foreground italic line-clamp-2">“{inv.reason_quote}”</div>
                                                        ) : !inv.due_date && variant === "watching" ? (
                                                            <AddDueDateButton invoiceId={inv._id} onChanged={onChanged} />
                                                        ) : reason.detail ? (
                                                            <div className="text-[12px] text-muted-foreground">{reason.detail}</div>
                                                        ) : null}
                                                    </div>
                                                </td>
                                                <td className="px-3 py-3 align-top">
                                                    <div className="flex items-start justify-end gap-1">
                                                        <RowActions inv={inv} variant={variant} onChanged={onChanged} onFollowUp={followUp} />
                                                        <InvoiceOverflowMenu invoice={inv} onChanged={onChanged} />
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
