import { PlusCircle } from "lucide-react";

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
    const label = (status || "invoiced").replace(/_/g, " ");
    return (
        <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${cls} capitalize`}
            data-testid="invoice-status-pill"
        >
            {label}
        </span>
    );
}

function formatMoney(n, currency = "USD") {
    if (n == null) return "—";
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(n));
    } catch {
        return `$${Number(n).toFixed(2)}`;
    }
}

function formatDate(iso) {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    } catch {
        return iso;
    }
}

export function LedgerCard({ ledger }) {
    if (!ledger) return null;
    const { invoices = [], total_open = 0, client_count = 0 } = ledger;

    return (
        <div className="space-y-6" data-testid="ledger-card">
            <div className="rounded-2xl border border-border bg-card p-6 md:p-8">
                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                    You&apos;re owed
                </div>
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
                    <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">
                        Widen the scan window or add a payment manually once we ship that action.
                    </p>
                    <button className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card text-sm font-medium hover:border-foreground/40" data-testid="track-manual-button" disabled>
                        <PlusCircle className="w-4 h-4" />
                        Track a payment manually
                    </button>
                </div>
            ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="ledger-table-wrapper">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border bg-muted/40 text-left">
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Client</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Invoice</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Amount</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Due / Promise</th>
                            </tr>
                        </thead>
                        <tbody>
                            {invoices.map((inv) => (
                                <tr key={inv._id} className="border-b border-border/60 hover:bg-muted/30 transition-colors" data-testid="ledger-row">
                                    <td className="px-4 py-3 align-top">
                                        <div className="text-sm font-medium truncate max-w-[220px]">
                                            {inv.counterparty_name || inv.counterparty_email || "Unknown"}
                                        </div>
                                        {inv.counterparty_name && inv.counterparty_email ? (
                                            <div className="text-[11px] font-mono text-muted-foreground truncate max-w-[220px]">{inv.counterparty_email}</div>
                                        ) : null}
                                    </td>
                                    <td className="px-4 py-3 align-top">
                                        <div className="font-mono text-xs text-foreground">{inv.invoice_ref || "—"}</div>
                                        {inv.source_subject ? (
                                            <div className="text-[11px] text-muted-foreground truncate max-w-[240px]">{inv.source_subject}</div>
                                        ) : null}
                                    </td>
                                    <td className="px-4 py-3 align-top text-right font-mono tabular-nums text-sm">
                                        {formatMoney(inv.amount, inv.currency || "USD")}
                                    </td>
                                    <td className="px-4 py-3 align-top">
                                        <StatusPill status={inv.status} />
                                    </td>
                                    <td className="px-4 py-3 align-top text-sm text-muted-foreground">
                                        {inv.promise_date ? (
                                            <span>Promised {formatDate(inv.promise_date)}</span>
                                        ) : (
                                            <span>{formatDate(inv.due_date)}</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
