import { useEffect, Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, MoreHorizontal, PlusCircle, Quote, Send } from "lucide-react";
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
};

function StatusPill({ status }) {
    const cls = STATUS_STYLES[status] || STATUS_STYLES.invoiced;
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${cls} capitalize`} data-testid="invoice-status-pill">
            {(status || "invoiced").replace(/_/g, " ")}
        </span>
    );
}

export function formatMoney(n, currency = "USD") {
    if (n == null) return "—";
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(n));
    } catch { return `$${Number(n).toFixed(2)}`; }
}

export function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); } catch { return iso; }
}

function TimelineRow({ invoiceId }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");
    useEffect(() => {
        let alive = true;
        api.get(`/invoices/${invoiceId}/timeline`)
            .then(({ data }) => { if (alive) setData(data); })
            .catch((e) => { if (alive) setErr(extractError(e)); });
        return () => { alive = false; };
    }, [invoiceId]);
    if (err) return <div className="text-sm text-red-700">{err}</div>;
    if (!data) return <div className="text-sm text-muted-foreground">Loading timeline…</div>;
    return (
        <div className="space-y-3" data-testid="invoice-timeline">
            {data.events.map((ev, i) => (
                <div key={i} className="flex gap-3">
                    <div className="w-2 h-2 rounded-full bg-foreground mt-1.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-baseline gap-2">
                            <span className="text-sm font-medium capitalize">{(ev.kind || "event").replace(/_/g, " ")}</span>
                            <span className="text-[11px] font-mono text-muted-foreground">{formatDate(ev.date)}</span>
                        </div>
                        {ev.quote ? (
                            <div className="mt-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-foreground italic flex gap-2">
                                <Quote className="w-3.5 h-3.5 mt-1 text-muted-foreground flex-shrink-0" />
                                <span>&ldquo;{ev.quote}&rdquo;</span>
                            </div>
                        ) : null}
                        {ev.subject ? (
                            <div className="mt-1 text-[11px] font-mono text-muted-foreground truncate">
                                {ev.subject} · from {ev.from}
                            </div>
                        ) : null}
                    </div>
                </div>
            ))}
        </div>
    );
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

export function LedgerCard({ ledger, onChanged }) {
    const [expanded, setExpanded] = useState(null);
    const [chaseInvoice, setChaseInvoice] = useState(null);
    const [confirm, setConfirm] = useState(null); // { invoice, action }
    if (!ledger) return null;
    const { invoices = [], total_open = 0, client_count = 0 } = ledger;

    async function act(id, action) {
        try {
            await api.post(`/invoices/${id}/action`, { action });
            toast.success("Updated");
            onChanged?.();
        } catch (e) { toast.error(extractError(e)); }
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
                            onChanged?.();
                        } catch (e) {
                            toast.error(extractError(e));
                        }
                    },
                },
            });
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setConfirm(null);
        }
    }
    return (
        <div className="space-y-6" data-testid="ledger-card">
            <div className="rounded-2xl border border-border bg-card p-6 md:p-8">
                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">You&apos;re owed</div>
                <div className="mt-1 flex items-baseline gap-4 flex-wrap">
                    <span className="font-heading font-black text-4xl md:text-5xl tracking-tight tabular-nums" data-testid="ledger-total">
                        {formatMoney(total_open)}
                    </span>
                    <span className="text-muted-foreground text-sm" data-testid="ledger-client-count">
                        across {client_count} client{client_count === 1 ? "" : "s"}
                    </span>
                </div>
            </div>

            {invoices.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center" data-testid="ledger-empty">
                    <h3 className="font-heading font-semibold text-lg">No unpaid invoices found in the last 12 months.</h3>
                    <button className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card text-sm font-medium" data-testid="track-manual-button" disabled>
                        <PlusCircle className="w-4 h-4" /> Track a payment manually
                    </button>
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
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Due / Promise</th>
                                <th className="px-2 py-3 w-8" />
                            </tr>
                        </thead>
                        <tbody>
                            {invoices.map((inv) => {
                                const isOpen = expanded === inv._id;
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
                                                <div className="font-mono text-xs text-foreground">{inv.invoice_ref || "—"}</div>
                                                {inv.source_subject ? <div className="text-[11px] text-muted-foreground truncate max-w-[240px]">{inv.source_subject}</div> : null}
                                            </td>
                                            <td className="px-4 py-3 align-top text-right font-mono tabular-nums text-sm">
                                                <div>{formatMoney(inv.amount, inv.currency || "USD")}</div>
                                                {inv.status === "partially_paid" && inv.balance_remaining != null && inv.balance_remaining < inv.amount ? (
                                                    <div className="text-[11px] text-green-700 mt-0.5" data-testid="ledger-balance-remaining">
                                                        {formatMoney(inv.balance_remaining, inv.currency || "USD")} left
                                                    </div>
                                                ) : null}
                                            </td>
                                            <td className="px-4 py-3 align-top"><StatusPill status={inv.status} /></td>
                                            <td className="px-4 py-3 align-top text-sm text-muted-foreground">
                                                {inv.promise_date ? <span>Promised {formatDate(inv.promise_date)}</span> : <span>{formatDate(inv.due_date)}</span>}
                                            </td>
                                            <td className="px-2 py-3 align-top text-right" onClick={(e) => e.stopPropagation()}>
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger className="inline-flex items-center justify-center w-7 h-7 rounded hover:bg-muted" data-testid="row-actions-trigger">
                                                        <MoreHorizontal className="w-4 h-4" />
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent align="end">
                                                        <DropdownMenuItem onClick={() => setChaseInvoice(inv)} data-testid="row-draft-chase"><Send className="w-3.5 h-3.5 mr-2" />Draft chase</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => setConfirm({ invoice: inv, action: "mark_paid" })} data-testid="row-mark-paid">Mark paid</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => act(inv._id, "dispute")} data-testid="row-dispute">Mark disputed</DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => act(inv._id, inv.chasing_paused ? "resume" : "pause")} data-testid="row-pause">
                                                            {inv.chasing_paused ? "Resume chasing" : "Pause chasing"}
                                                        </DropdownMenuItem>
                                                        <DropdownMenuItem onClick={() => setConfirm({ invoice: inv, action: "write_off" })} className="text-red-700" data-testid="row-write-off">Write off</DropdownMenuItem>
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            </td>
                                        </tr>
                                        {isOpen ? (
                                            <tr className="bg-muted/20">
                                                <td />
                                                <td colSpan={6} className="px-4 py-4">
                                                    <TimelineRow invoiceId={inv._id} />
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
            <ChaseDialog invoice={chaseInvoice} open={!!chaseInvoice} onOpenChange={(o) => !o && setChaseInvoice(null)} onSent={() => { setChaseInvoice(null); onChanged?.(); }} />
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
                                        {confirm.invoice.invoice_ref ? (
                                            <span className="text-muted-foreground"> · {confirm.invoice.invoice_ref}</span>
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
        </div>
    );
}
