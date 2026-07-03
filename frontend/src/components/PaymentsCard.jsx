import { useState } from "react";
import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { toast } from "sonner";
import { formatMoney, formatDate } from "@/components/LedgerCard";

/**
 * PaymentsCard — shows recent matched receipts and any ambiguous receipts
 * needing user disambiguation. Only rendered when data.receipts is non-empty.
 */
export function PaymentsCard({ receipts, ledger, onChanged }) {
    const rows = receipts?.receipts || [];
    if (!rows.length) return null;

    const ambiguous = rows.filter((r) => r.match_status === "ambiguous");
    const matched = rows.filter(
        (r) => r.match_status === "matched" || r.match_status === "user_confirmed",
    );
    if (!ambiguous.length && !matched.length) return null;

    return (
        <div className="space-y-4" data-testid="payments-card">
            {ambiguous.length > 0 ? (
                <AmbiguousBlock receipts={ambiguous} ledger={ledger} onChanged={onChanged} />
            ) : null}
            {matched.length > 0 ? <MatchedBlock receipts={matched} /> : null}
        </div>
    );
}

function AmbiguousBlock({ receipts, ledger, onChanged }) {
    const invById = new Map((ledger?.invoices || []).map((i) => [i._id, i]));
    return (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/40 p-5" data-testid="payments-ambiguous">
            <div className="flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-amber-700" />
                <div className="font-heading font-semibold text-sm text-amber-900">
                    Which invoice does this payment go against?
                </div>
            </div>
            <div className="mt-3 space-y-3">
                {receipts.map((rc) => (
                    <AmbiguousRow key={rc._id} rc={rc} invById={invById} onChanged={onChanged} />
                ))}
            </div>
        </div>
    );
}

function AmbiguousRow({ rc, invById, onChanged }) {
    const [busy, setBusy] = useState(false);

    async function pick(invoiceId) {
        setBusy(true);
        try {
            await api.post(`/receipts/${rc._id}/match`, { invoice_id: invoiceId });
            toast.success("Payment matched");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }
    async function reject() {
        setBusy(true);
        try {
            await api.post(`/receipts/${rc._id}/reject`);
            toast.success("Ignored");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    const candidates = (rc.candidate_invoice_ids || [])
        .map((id) => invById.get(id))
        .filter(Boolean);

    return (
        <div className="rounded-md border border-amber-200 bg-white p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="text-sm">
                    <span className="font-medium">{formatMoney(rc.amount, rc.currency)}</span>
                    <span className="text-muted-foreground"> · from </span>
                    <span className="font-medium">{rc.payer_name || "Unknown payer"}</span>
                    <span className="text-muted-foreground"> · {formatDate(rc.source_date)}</span>
                </div>
                <button
                    onClick={reject}
                    disabled={busy}
                    className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground disabled:opacity-50"
                    data-testid="receipt-reject-btn">
                    Not a match
                </button>
            </div>
            <div className="mt-2 space-y-1.5">
                {candidates.map((inv) => (
                    <button
                        key={inv._id}
                        onClick={() => pick(inv._id)}
                        disabled={busy}
                        data-testid="receipt-candidate-btn"
                        className="w-full flex items-baseline justify-between gap-3 rounded border border-border bg-card px-3 py-2 text-left hover:bg-muted/50 disabled:opacity-50">
                        <div className="text-sm">
                            <span className="font-medium">
                                {inv.counterparty_name || inv.counterparty_email}
                            </span>
                            <span className="text-muted-foreground">
                                {" · "}
                                {inv.invoice_ref || "no ref"}
                            </span>
                        </div>
                        <div className="font-mono text-xs tabular-nums">
                            {formatMoney(inv.balance_remaining ?? inv.amount, inv.currency)}
                        </div>
                    </button>
                ))}
                {candidates.length === 0 ? (
                    <div className="text-[11px] text-muted-foreground">
                        No candidate invoices remaining. Ignore this receipt or manually mark an
                        invoice paid.
                    </div>
                ) : null}
            </div>
        </div>
    );
}

function MatchedBlock({ receipts }) {
    return (
        <div className="rounded-2xl border border-border bg-card p-5" data-testid="payments-matched">
            <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-700" />
                <div className="font-heading font-semibold text-sm">
                    Payments received ({receipts.length})
                </div>
            </div>
            <div className="mt-3 divide-y divide-border/60">
                {receipts.slice(0, 6).map((rc) => (
                    <div key={rc._id} className="py-2 flex items-baseline justify-between gap-3">
                        <div className="text-sm min-w-0">
                            <span className="font-medium">
                                {formatMoney(rc.applied_amount ?? rc.amount, rc.currency)}
                            </span>
                            <span className="text-muted-foreground"> from </span>
                            <span className="font-medium truncate">
                                {rc.payer_name || "Unknown"}
                            </span>
                        </div>
                        <div className="text-[11px] font-mono text-muted-foreground shrink-0">
                            {formatDate(rc.source_date)}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
