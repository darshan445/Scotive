import { useMemo, Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, Calendar, MoreHorizontal, PlusCircle, Send } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { toast } from "sonner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ChaseDialog } from "@/components/ChaseDialog";
import { ManualInvoiceDialog } from "@/components/ManualInvoiceDialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

import { invoiceDisplayRef, isJunkInvoiceRef, statusLabel, invoiceStatusDisplay, formatLastFollowUp, lastFollowUpSentAt } from "@/lib/invoiceCopy";
import { openLedgerInvoices, historyLedgerInvoices, historyLedgerSummary } from "@/lib/ledgerInvoices";
import { InvoiceTimeline } from "@/components/InvoiceTimeline";
import { useWorkspaceVersion } from "@/lib/workspaceRefresh";

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
    const status = inv?.status;
    const hasClaim = inv?.disputed_claim_amount != null && Number(inv.disputed_claim_amount) > 0;
    const partial = status === "partially_paid"
        || (Number(inv?.paid_amount || 0) > 0.005
            && Number(inv?.balance_remaining ?? inv?.amount ?? 0) > 0.005);
    const styleKey = (status === "partially_paid" && hasClaim) ? "disputed"
        : (status === "disputed" && partial) ? "disputed"
        : (status || "invoiced");
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

export const NO_DUE_DATE_LABEL = "No due date — please add one";

export function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return iso; }
}

const CONFIRM_COPY = {
    mark_paid: {
        title: "Mark this invoice as paid?",
        body: "This closes the balance and moves the row to your paid history. You can undo this for a few seconds after.",
        confirmLabel: "Mark paid",
        toast: "Marked paid",
        destructive: false,
    },
    write_off: {
        title: "Write off this invoice?",
        body: "The client will no longer be chased and the amount stops counting toward what you're owed. You can undo this for a few seconds after.",
        confirmLabel: "Write off",
        toast: "Written off",
        destructive: true,
    },
};

export function LedgerCard({ ledger, onChanged, variant = "open" }) {
    const workspaceVersion = useWorkspaceVersion();
    const [expanded, setExpanded] = useState(null);
    const [chaseInvoice, setChaseInvoice] = useState(null);
    const [confirm, setConfirm] = useState(null); // { invoice, action }
    const [manualOpen, setManualOpen] = useState(false);
    const [dueDateEdit, setDueDateEdit] = useState(null); // invoice
    const [dueDateValue, setDueDateValue] = useState("");
    const [dueDateBusy, setDueDateBusy] = useState(false);
    const isHistory = variant === "paid";
    const allInvoices = ledger?.invoices ?? [];
    const invoices = useMemo(
        () => (isHistory ? historyLedgerInvoices(allInvoices) : openLedgerInvoices(allInvoices)),
        [allInvoices, isHistory],
    );
    const historySummary = useMemo(
        () => historyLedgerSummary(allInvoices),
        [allInvoices],
    );
    if (!ledger) return null;
    const { totals_by_currency, total_open, client_count = 0 } = ledger;
    const openTotals = totals_by_currency ?? total_open;

    async function act(id, action) {
        try {
            await api.post(`/invoices/${id}/action`, { action });
            toast.success("Updated");
            await onChanged?.();
        } catch (e) { toast.error(extractError(e)); }
    }

    async function saveDueDate() {
        if (!dueDateEdit || !dueDateValue) return;
        setDueDateBusy(true);
        try {
            await api.post(`/invoices/${dueDateEdit._id}/action`, {
                action: "set_due_date",
                due_date: dueDateValue,
            });
            toast.success("Due date saved");
            setDueDateEdit(null);
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setDueDateBusy(false);
        }
    }

    function openDueDateEditor(inv) {
        setDueDateEdit(inv);
        setDueDateValue(inv.due_date ? String(inv.due_date).slice(0, 10) : "");
    }

    async function runDestructive(invoice, action) {
        const copy = CONFIRM_COPY[action];
        try {
            await api.post(`/invoices/${invoice._id}/action`, { action });
            toast.success(copy.toast, {
                duration: 5000,
                action: {
                    label: "Undo",
                    onClick: async () => {
                        try {
                            await api.post(`/invoices/${invoice._id}/action`, { action: "undo" });
                            toast.success("Reverted");
                            await onChanged?.();
                        } catch (e) {
                            toast.error(extractError(e));
                        }
                    },
                },
            });
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setConfirm(null);
        }
    }
    return (
        <div className="space-y-6" data-testid={isHistory ? "ledger-card-paid" : "ledger-card"}>
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
                    {!isHistory ? (
                        <button
                            onClick={() => setManualOpen(true)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3.5 py-2 text-sm font-medium hover:bg-muted transition-colors"
                            data-testid="track-manual-button-header">
                            <PlusCircle className="w-4 h-4" /> Track manually
                        </button>
                    ) : null}
                </div>
            </div>

            {invoices.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center" data-testid="ledger-empty">
                    <h3 className="font-heading font-semibold text-lg">
                        {isHistory ? "No paid invoices yet." : "No open invoices."}
                    </h3>
                    <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">
                        {isHistory
                            ? "When you mark invoices paid, they move here for your records."
                            : "Scotive is watching your sent mail — send your next invoice like you always do and it will appear here."}
                    </p>
                    {!isHistory ? (
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
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border bg-muted/40 text-left">
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-6" />
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Client</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Invoice</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Amount</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                    {isHistory ? "Closed" : "Due / Promise"}
                                </th>
                                <th className="px-2 py-3 w-8" />
                            </tr>
                        </thead>
                        <tbody>
                            {invoices.map((inv) => {
                                const isOpen = expanded === inv._id;
                                const followUpLine = !isHistory ? formatLastFollowUp(lastFollowUpSentAt(inv)) : null;
                                return (
                                    <Fragment key={inv._id}>
                                        <tr
                                            className="border-b border-border/60 hover:bg-muted/30 transition-colors cursor-pointer"
                                            onClick={() => setExpanded(isOpen ? null : inv._id)}
                                            data-testid="ledger-row">
                                            <td className="px-3 py-3 align-top">
                                                <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${isOpen ? "rotate-90" : ""}`} />
                                            </td>
                                            <td className="px-4 py-3 align-top">
                                                <Link to={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
                                                      onClick={(e) => e.stopPropagation()}
                                                      className="text-sm font-medium hover:underline"
                                                      data-testid="ledger-client-link">
                                                    {inv.counterparty_name || inv.counterparty_email || "Unknown"}
                                                </Link>
                                                {inv.counterparty_name && inv.counterparty_email ? (
                                                    <div className="text-[11px] font-mono text-muted-foreground truncate max-w-[220px]">{inv.counterparty_email}</div>
                                                ) : null}
                                            </td>
                                            <td className="px-4 py-3 align-top">
                                                <div className="text-xs text-foreground break-words max-w-[240px]">{invoiceDisplayRef(inv)}</div>
                                                {inv.source_subject && invoiceDisplayRef(inv) !== inv.source_subject ? (
                                                    <div className="text-[11px] text-muted-foreground truncate max-w-[240px]">{inv.source_subject}</div>
                                                ) : null}
                                            </td>
                                            <td className="px-4 py-3 align-top text-right font-mono tabular-nums text-sm">
                                                <div>{formatMoney(inv.amount, inv.currency || "USD")}</div>
                                                {(inv.status === "partially_paid" || (Number(inv.paid_amount || 0) > 0 && inv.disputed_claim_amount != null))
                                                    && inv.balance_remaining != null && inv.balance_remaining < inv.amount ? (
                                                    <div className="text-[11px] text-green-700 mt-0.5" data-testid="ledger-balance-remaining">
                                                        {formatMoney(inv.balance_remaining, inv.currency || "USD")} left
                                                    </div>
                                                ) : null}
                                            </td>
                                            <td className="px-4 py-3 align-top">
                                                <StatusPill inv={inv} />
                                                {followUpLine ? (
                                                    <div className="text-[10px] text-muted-foreground mt-1" data-testid="ledger-followup-sent">
                                                        {followUpLine}
                                                    </div>
                                                ) : null}
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
                                                    <button
                                                        type="button"
                                                        onClick={(e) => { e.stopPropagation(); openDueDateEditor(inv); }}
                                                        className="text-left text-amber-800 hover:text-amber-950 underline underline-offset-2 decoration-amber-400/60"
                                                        data-testid="ledger-add-due-date">
                                                        {NO_DUE_DATE_LABEL}
                                                    </button>
                                                )}
                                            </td>
                                            <td className="px-2 py-3 align-top text-right" onClick={(e) => e.stopPropagation()}>
                                                {!isHistory ? (
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger className="inline-flex items-center justify-center w-7 h-7 rounded hover:bg-muted" data-testid="row-actions-trigger">
                                                        <MoreHorizontal className="w-4 h-4" />
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent align="end">
                                                        <DropdownMenuItem onClick={() => setChaseInvoice(inv)} data-testid="row-draft-chase"><Send className="w-3.5 h-3.5 mr-2" />Follow up</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => openDueDateEditor(inv)} data-testid="row-set-due-date">
                                                            <Calendar className="w-3.5 h-3.5 mr-2" />{inv.due_date ? "Edit due date" : "Add due date"}
                                                        </DropdownMenuItem>
                                                        {inv.status === "stale" ? (
                                                            <DropdownMenuItem onClick={() => act(inv._id, "dismiss_stale")} data-testid="row-stale-chase">Still chasing</DropdownMenuItem>
                                                        ) : null}
                                                        <DropdownMenuItem onClick={() => setConfirm({ invoice: inv, action: "mark_paid" })} data-testid="row-mark-paid">Mark paid</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => act(inv._id, "dispute")} data-testid="row-dispute">Mark disputed</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => act(inv._id, inv.chasing_paused ? "resume" : "pause")} data-testid="row-pause">
                                                            {inv.chasing_paused ? "Resume chasing" : "Pause chasing"}
                                                        </DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => setConfirm({ invoice: inv, action: "write_off" })} className="text-red-700" data-testid="row-write-off">Write off</DropdownMenuItem>
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                                ) : null}
                                            </td>
                                        </tr>
                                        {isOpen ? (
                                            <tr className="bg-muted/20">
                                                <td />
                                                <td colSpan={6} className="px-4 py-4">
                                                    <InvoiceTimeline key={`${inv._id}-${workspaceVersion}`} invoiceId={inv._id} />
                                                </td>
                                            </tr>
                                        ) : null}
                                    </Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
            <ChaseDialog
                invoice={chaseInvoice}
                open={!!chaseInvoice}
                onOpenChange={(o) => !o && setChaseInvoice(null)}
                onSent={async () => { setChaseInvoice(null); await onChanged?.(); }}
            />
            <ManualInvoiceDialog
                open={manualOpen}
                onOpenChange={setManualOpen}
                onCreated={() => onChanged?.()}
            />
            <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
                <AlertDialogContent data-testid="confirm-action-dialog">
                    {confirm ? (
                        <>
                            <AlertDialogHeader>
                                <AlertDialogTitle>{CONFIRM_COPY[confirm.action].title}</AlertDialogTitle>
                                <AlertDialogDescription>
                                    <span className="block">{CONFIRM_COPY[confirm.action].body}</span>
                                    <span className="mt-3 block rounded-md border border-border bg-muted/40 px-3 py-2 text-foreground/90 text-sm">
                                        <span className="font-medium">
                                            {confirm.invoice.counterparty_name || confirm.invoice.counterparty_email}
                                        </span>
                                        <span className="text-muted-foreground"> · </span>
                                        <span className="font-mono">
                                            {formatMoney(
                                                confirm.action === "mark_paid"
                                                    ? (confirm.invoice.balance_remaining ?? confirm.invoice.amount)
                                                    : confirm.invoice.amount,
                                                confirm.invoice.currency || "USD",
                                            )}
                                        </span>
                                        {confirm.invoice.invoice_ref && !isJunkInvoiceRef(confirm.invoice.invoice_ref) ? (
                                            <span className="text-muted-foreground"> · {confirm.invoice.invoice_ref}</span>
                                        ) : confirm.invoice.source_subject ? (
                                            <span className="text-muted-foreground"> · {confirm.invoice.source_subject}</span>
                                        ) : null}
                                    </span>
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel data-testid="confirm-cancel">Cancel</AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={() => runDestructive(confirm.invoice, confirm.action)}
                                    className={CONFIRM_COPY[confirm.action].destructive ? "bg-red-600 hover:bg-red-700 focus:ring-red-600" : ""}
                                    data-testid="confirm-action">
                                    {CONFIRM_COPY[confirm.action].confirmLabel}
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </>
                    ) : null}
                </AlertDialogContent>
            </AlertDialog>
            <AlertDialog open={!!dueDateEdit} onOpenChange={(o) => !dueDateBusy && !o && setDueDateEdit(null)}>
                <AlertDialogContent data-testid="due-date-dialog">
                    <AlertDialogHeader>
                        <AlertDialogTitle>{dueDateEdit?.due_date ? "Edit due date" : "Add due date"}</AlertDialogTitle>
                        <AlertDialogDescription>
                            Scotive only uses due dates found in your invoice or that you set here — it never guesses.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="space-y-2">
                        <Label htmlFor="ledger-due-date">Due date</Label>
                        <Input
                            id="ledger-due-date"
                            type="date"
                            value={dueDateValue}
                            onChange={(e) => setDueDateValue(e.target.value)}
                            data-testid="ledger-due-date-input"
                        />
                    </div>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={dueDateBusy}>Cancel</AlertDialogCancel>
                        <Button onClick={saveDueDate} disabled={dueDateBusy || !dueDateValue} data-testid="ledger-due-date-save">
                            Save
                        </Button>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
