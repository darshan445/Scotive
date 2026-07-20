import { useMemo, Fragment, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { PlusCircle } from "lucide-react";
import { ManualInvoiceDialog } from "@/components/ManualInvoiceDialog";
import { InvoiceOverflowMenu } from "@/components/InvoiceOverflowMenu";
import { AddDueDateButton, NO_DUE_DATE_LABEL } from "@/components/AddDueDateButton";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

import {
    openLedgerInvoices,
    historyLedgerInvoices,
    historyLedgerSummary,
    pausedLedgerInvoices,
    groupInvoicesByClient,
    outstandingBalance,
    STATUS_FILTER_CHIPS,
    SORT_OPTIONS,
} from "@/lib/ledgerInvoices";
import { invoiceSubject, invoiceStatusDisplay, isJunkInvoiceRef, hasPendingPaymentClaim } from "@/lib/invoiceCopy";
import { navigateToInvoice } from "@/lib/invoiceNavigation";
import { resumeInvoiceTracking } from "@/components/InvoiceOverflowMenu";
import { Button } from "@/components/ui/button";
import { LedgerCardSkeleton } from "@/components/PageSkeletons";

const STATUS_STYLES = {
    invoiced: "bg-gray-100 text-gray-700 border-gray-200",
    overdue: "bg-red-50 text-red-700 border-red-200",
    promised: "bg-yellow-50 text-yellow-800 border-yellow-200",
    promise_broken: "bg-orange-50 text-orange-700 border-orange-200",
    disputed: "bg-purple-50 text-purple-700 border-purple-200",
    partially_paid: "bg-green-50 text-green-700 border-green-200",
    paid_unconfirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    paid: "bg-green-50 text-green-700 border-green-200",
    written_off: "bg-gray-100 text-gray-500 border-gray-200",
    stale: "bg-stone-100 text-stone-600 border-stone-200",
};

function StatusPill({ inv }) {
    const status = inv?.status || "invoiced";
    const hasClaim = inv?.disputed_claim_amount != null && Number(inv.disputed_claim_amount) > 0;
    const pendingPay = hasPendingPaymentClaim(inv);
    let styleKey = status;
    if (pendingPay && (status === "disputed" || hasClaim)) styleKey = "paid_unconfirmed";
    else if (status === "partially_paid" && hasClaim) styleKey = "disputed";
    const cls = STATUS_STYLES[styleKey] || STATUS_STYLES.invoiced;
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${cls}`} data-testid="invoice-status-pill">
            {invoiceStatusDisplay(inv)}
        </span>
    );
}

export function formatMoney(n, currency = "USD") {
    if (n == null) return "—";
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(n));
    } catch { return `$${Number(n).toFixed(2)}`; }
}

/** Render open balances grouped by currency — never sums across currencies. */
export function formatOpenTotals(totalsByCurrency) {
    if (totalsByCurrency == null) return formatMoney(0);
    if (typeof totalsByCurrency === "number") {
        return formatMoney(totalsByCurrency);
    }
    const entries = Object.entries(totalsByCurrency).filter(([, v]) => Number(v) > 0);
    if (entries.length === 0) return formatMoney(0);
    return entries.map(([cur, amt]) => formatMoney(amt, cur)).join(" + ");
}

export { NO_DUE_DATE_LABEL };

export function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return iso; }
}

export function LedgerCard({ ledger, onChanged, variant = "open" }) {
    const navigate = useNavigate();
    const location = useLocation();
    const [manualOpen, setManualOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState("all");
    const [sortKey, setSortKey] = useState("due_soonest");
    const [groupByClient, setGroupByClient] = useState(false);
    const isHistory = variant === "paid";
    const isPaused = variant === "paused";
    const allInvoices = ledger?.invoices ?? [];
    const invoices = useMemo(
        () => {
            if (isHistory) return historyLedgerInvoices(allInvoices);
            if (isPaused) return pausedLedgerInvoices(allInvoices);
            return openLedgerInvoices(allInvoices, { statusFilter, sort: sortKey });
        },
        [allInvoices, isHistory, isPaused, statusFilter, sortKey],
    );
    const clientGroups = useMemo(
        () => (!isHistory && !isPaused && groupByClient ? groupInvoicesByClient(invoices) : null),
        [invoices, isHistory, isPaused, groupByClient],
    );
    const historySummary = useMemo(
        () => historyLedgerSummary(allInvoices),
        [allInvoices],
    );
    // Unfiltered open list — keeps status chips visible even when a chip has zero matches.
    const openUnfiltered = useMemo(
        () => (isHistory || isPaused ? [] : openLedgerInvoices(allInvoices)),
        [allInvoices, isHistory, isPaused],
    );
    const showOpenToolbar = !isHistory && !isPaused && openUnfiltered.length > 0;

    // Derive You're Owed from all open invoices so unconfirmed claims never
    // reduce the total (independent of the status filter chip).
    const openTotals = useMemo(() => {
        if (isHistory || isPaused) return ledger?.totals_by_currency ?? ledger?.total_open;
        const totals = {};
        for (const inv of openUnfiltered) {
            const cur = (inv.currency || "USD").toUpperCase();
            totals[cur] = Math.round(((totals[cur] || 0) + outstandingBalance(inv)) * 100) / 100;
        }
        return totals;
    }, [openUnfiltered, isHistory, isPaused, ledger?.totals_by_currency, ledger?.total_open]);

    if (!ledger) return <LedgerCardSkeleton />;
    const { client_count = 0 } = ledger;
    const filterEmpty = showOpenToolbar && invoices.length === 0 && statusFilter !== "all";
    const showListShell = showOpenToolbar || invoices.length > 0;

    return (
        <div className="space-y-6" data-testid={isHistory ? "ledger-card-paid" : isPaused ? "ledger-card-paused" : "ledger-card"}>
            <div className="surface-card p-6 md:p-7">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        {isHistory ? (
                            <>
                                <div className="eyebrow">Collected</div>
                                <div className="mt-1 flex items-baseline gap-4 flex-wrap">
                                    <span className="stat-number font-bold text-4xl md:text-[2.75rem] tracking-tight text-emerald-700" data-testid="ledger-paid-total">
                                        {formatOpenTotals(historySummary.totalsByCurrency)}
                                    </span>
                                    <span className="text-muted-foreground text-sm" data-testid="ledger-paid-meta">
                                        {historySummary.paidCount > 0
                                            ? `${historySummary.paidCount} paid invoice${historySummary.paidCount === 1 ? "" : "s"}`
                                            : "No paid invoices yet"}
                                        {historySummary.clientCount > 0
                                            ? ` across ${historySummary.clientCount} client${historySummary.clientCount === 1 ? "" : "s"}`
                                            : ""}
                                        {historySummary.writtenOffCount > 0
                                            ? ` · ${historySummary.writtenOffCount} written off`
                                            : ""}
                                    </span>
                                </div>
                            </>
                        ) : isPaused ? (
                            <>
                                <div className="eyebrow">Paused</div>
                                <div className="mt-1 flex items-baseline gap-4 flex-wrap">
                                    <span className="stat-number font-bold text-4xl md:text-[2.75rem] tracking-tight" data-testid="ledger-paused-count">
                                        {invoices.length}
                                    </span>
                                    <span className="text-muted-foreground text-sm">
                                        invoice{invoices.length === 1 ? "" : "s"} off active lists — resume anytime
                                    </span>
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="eyebrow">You&apos;re owed</div>
                                <div className="mt-1 flex items-baseline gap-4 flex-wrap">
                                    <span className="stat-number font-bold text-4xl md:text-[2.75rem] tracking-tight" data-testid="ledger-total">
                                        {formatOpenTotals(openTotals)}
                                    </span>
                                    <span className="text-muted-foreground text-sm" data-testid="ledger-client-count">
                                        across {client_count} client{client_count === 1 ? "" : "s"}
                                    </span>
                                </div>
                            </>
                        )}
                    </div>
                    {!isHistory && !isPaused ? (
                        <button
                            onClick={() => setManualOpen(true)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3.5 py-2 text-sm font-medium hover:bg-muted transition-colors"
                            data-testid="track-manual-button-header">
                            <PlusCircle className="w-4 h-4" /> Track manually
                        </button>
                    ) : null}
                </div>
            </div>

            {!showListShell ? (
                <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center" data-testid="ledger-empty">
                    <h3 className="font-heading font-semibold text-lg">
                        {isHistory
                            ? "No paid invoices yet."
                            : isPaused
                              ? "Nothing paused."
                              : "No open invoices."}
                    </h3>
                    <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">
                        {isHistory
                            ? "When you mark invoices paid, they move here for your records."
                            : isPaused
                              ? "Pause tracking from the ⋯ menu when you want an invoice off active lists without marking it paid."
                              : "Scotive is watching your sent mail — send your next invoice like you always do and it will appear here."}
                    </p>
                    {!isHistory && !isPaused ? (
                        <button
                            onClick={() => setManualOpen(true)}
                            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card text-sm font-medium hover:bg-muted transition-colors"
                            data-testid="track-manual-button">
                            <PlusCircle className="w-4 h-4" /> Track a payment manually
                        </button>
                    ) : null}
                </div>
            ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="ledger-table-wrapper">
                    {showOpenToolbar ? (
                        <div className="px-4 py-3 border-b border-border flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-muted/20" data-testid="ledger-toolbar">
                            <div className="flex flex-wrap gap-1.5" data-testid="ledger-status-filters">
                                {STATUS_FILTER_CHIPS.map((chip) => (
                                    <button
                                        key={chip.key}
                                        type="button"
                                        onClick={() => setStatusFilter(chip.key)}
                                        className={
                                            statusFilter === chip.key
                                                ? "rounded-full px-2.5 py-1 text-[11px] font-semibold border border-foreground bg-foreground text-background"
                                                : "rounded-full px-2.5 py-1 text-[11px] font-medium border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-muted"
                                        }
                                        data-testid={`ledger-filter-${chip.key}`}
                                    >
                                        {chip.label}
                                    </button>
                                ))}
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <Select value={sortKey} onValueChange={setSortKey}>
                                    <SelectTrigger className="h-8 w-[160px] text-xs" data-testid="ledger-sort">
                                        <SelectValue placeholder="Sort" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {SORT_OPTIONS.map((o) => (
                                            <SelectItem key={o.key} value={o.key}>{o.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
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
                        </div>
                    ) : null}
                    {invoices.length === 0 ? (
                        <div className="p-10 text-center" data-testid="ledger-empty">
                            <h3 className="font-heading font-semibold text-lg">
                                {filterEmpty ? "No invoices match this filter." : "No open invoices."}
                            </h3>
                            <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">
                                {filterEmpty
                                    ? "Try another status chip or clear the filter."
                                    : "Scotive is watching your sent mail — send your next invoice like you always do and it will appear here."}
                            </p>
                            {filterEmpty ? (
                                <button
                                    type="button"
                                    onClick={() => setStatusFilter("all")}
                                    className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card text-sm font-medium hover:bg-muted transition-colors"
                                    data-testid="ledger-clear-filter"
                                >
                                    Show all
                                </button>
                            ) : null}
                        </div>
                    ) : (
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border bg-muted/40 text-left">
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Client</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Invoice</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Amount</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                    {isHistory ? "Closed" : isPaused ? "Status" : "Due / Promise"}
                                </th>
                                {isPaused ? (
                                    <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                        <span className="sr-only">Resume</span>
                                    </th>
                                ) : null}
                                <th className="w-10 px-2 py-3"><span className="sr-only">Actions</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {(clientGroups || [{ key: "_flat", invoices, name: null }]).map((group) => (
                                <Fragment key={group.key}>
                                    {group.name ? (
                                        <tr className="bg-muted/50 border-b border-border" data-testid="ledger-client-group">
                                            <td colSpan={isPaused ? 7 : 6} className="px-4 py-2">
                                                <div className="flex items-baseline justify-between gap-3">
                                                    <div className="text-xs font-semibold">
                                                        {group.name}
                                                        {group.email && group.name !== group.email ? (
                                                            <span className="ml-2 font-mono font-normal text-muted-foreground">{group.email}</span>
                                                        ) : null}
                                                        <span className="ml-2 font-normal text-muted-foreground">
                                                            · {group.invoices.length} invoice{group.invoices.length === 1 ? "" : "s"}
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
                                        return (
                                            <tr
                                                key={inv._id}
                                                className="border-b border-border/60 hover:bg-muted/30 transition-colors cursor-pointer"
                                                onClick={() => navigateToInvoice(navigate, location, inv._id)}
                                                data-testid="ledger-row"
                                            >
                                                <td className="px-4 py-3 align-top">
                                                    <Link
                                                        to={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
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
                                                    <div className="text-sm text-foreground break-words whitespace-normal max-w-[320px]" data-testid="ledger-subject">
                                                        {subject}
                                                    </div>
                                                    {ref && !isJunkInvoiceRef(ref) && ref !== subject ? (
                                                        <div className="text-[11px] font-mono text-muted-foreground mt-0.5">{ref}</div>
                                                    ) : null}
                                                </td>
                                                <td className="px-4 py-3 align-top text-right font-mono tabular-nums text-sm">
                                                    <div>{formatMoney(inv.amount, inv.currency || "USD")}</div>
                                                    {!hasPendingPaymentClaim(inv)
                                                        && (inv.status === "partially_paid" || Number(inv.paid_amount || 0) > 0.005)
                                                        && inv.balance_remaining != null
                                                        && Number(inv.balance_remaining) < Number(inv.amount || 0)
                                                        && Number(inv.balance_remaining) > 0.005 ? (
                                                        <div className="text-[11px] text-green-700 mt-0.5" data-testid="ledger-balance-remaining">
                                                            {formatMoney(inv.balance_remaining, inv.currency || "USD")} left
                                                        </div>
                                                    ) : null}
                                                </td>
                                                <td className="px-4 py-3 align-top">
                                                    <StatusPill inv={inv} />
                                                </td>
                                                <td className="px-4 py-3 align-top text-sm text-muted-foreground">
                                                    {isHistory ? (
                                                        <span>
                                                            {inv.paid_at
                                                                ? `Paid ${formatDate(inv.paid_at)}`
                                                                : inv.status === "written_off"
                                                                  ? `Written off ${formatDate(inv.status_updated_at)}`
                                                                  : formatDate(inv.status_updated_at)}
                                                        </span>
                                                    ) : inv.status === "stale" ? (
                                                        <span>No activity 120+ days</span>
                                                    ) : inv.promise_date ? (
                                                        <span>Promised {formatDate(inv.promise_date)}</span>
                                                    ) : inv.due_date ? (
                                                        <span>{formatDate(inv.due_date)}</span>
                                                    ) : (
                                                        <AddDueDateButton
                                                            invoiceId={inv._id}
                                                            onChanged={onChanged}
                                                        />
                                                    )}
                                                </td>
                                                {isPaused ? (
                                                    <td className="px-4 py-3 align-top" onClick={(e) => e.stopPropagation()}>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            data-testid="ledger-resume-tracking"
                                                            onClick={() => resumeInvoiceTracking(inv._id, { onChanged })}
                                                        >
                                                            Resume
                                                        </Button>
                                                    </td>
                                                ) : null}
                                                <td className="px-2 py-3 align-top">
                                                    <InvoiceOverflowMenu
                                                        invoice={inv}
                                                        onChanged={onChanged}
                                                    />
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </Fragment>
                            ))}
                        </tbody>
                    </table>
                    )}
                </div>
            )}
            <ManualInvoiceDialog
                open={manualOpen}
                onOpenChange={setManualOpen}
                onCreated={() => onChanged?.()}
            />
        </div>
    );
}
