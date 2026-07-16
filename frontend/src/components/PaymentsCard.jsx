import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Wallet } from "lucide-react";
import { api, extractError } from "@/lib/api";
import { toast } from "sonner";
import { formatMoney, formatDate } from "@/components/LedgerCard";
import { hasPendingPaymentClaim } from "@/lib/invoiceCopy";

const OPEN_INVOICE_STATUSES = [
    "invoiced",
    "overdue",
    "promised",
    "partially_paid",
    "promise_broken",
    "disputed",
    "paid_unconfirmed",
];

/** Only suggest an invoice when amount + currency actually match — never default to first open row. */
function guessInvoiceForReceipt(openInvoices, rc) {
    const amount = Number(rc.amount);
    const cur = (rc.currency || "USD").toUpperCase();
    if (!Number.isFinite(amount)) return null;
    return (
        openInvoices.find((i) => {
            const bal = Number(i.balance_remaining ?? i.amount);
            const ic = (i.currency || "USD").toUpperCase();
            return ic === cur && Math.abs(bal - amount) < 0.02;
        }) || null
    );
}

/**
 * PaymentsCard — confirm-paid prompts from remittance matches and spotted payments.
 * De-emphasizes invoice picking; user is authority on money received.
 */
export function PaymentsCard({ receipts, ledger, onChanged }) {
    const rows = receipts?.receipts || [];
    const invById = new Map((ledger?.invoices || []).map((i) => [i._id, i]));

    const confirmInvoices = (ledger?.invoices || []).filter((i) => hasPendingPaymentClaim(i));
    const unmatched = rows.filter((r) => r.match_status === "unmatched");
    const ambiguous = rows.filter((r) => r.match_status === "ambiguous");
    const recent = rows.filter((r) =>
        ["matched", "user_confirmed"].includes(r.match_status),
    );

    if (!confirmInvoices.length && !unmatched.length && !ambiguous.length) {
        return (
            <div className="surface-card px-6 py-10 text-center" data-testid="payments-card">
                <Wallet className="w-5 h-5 mx-auto text-muted-foreground mb-3" />
                <div className="font-heading font-semibold text-base">No payments to review</div>
                <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
                    Stripe and PayPal receipts are matched to open invoices automatically. Anything that needs a decision shows up here.
                </p>
                {recent.length > 0 ? (
                    <div className="mt-4 inline-block text-left">
                        <RecentActivity receipts={recent.slice(0, 4)} />
                    </div>
                ) : null}
            </div>
        );
    }

    return (
        <div className="space-y-4" data-testid="payments-card">
            {confirmInvoices.length > 0 ? (
                <ConfirmPaidBlock invoices={confirmInvoices} onChanged={onChanged} />
            ) : null}

            {unmatched.length > 0 ? (
                <SpottedBlock receipts={unmatched} invById={invById} onChanged={onChanged} />
            ) : null}

            {ambiguous.length > 0 ? (
                <AmbiguousCollapsible receipts={ambiguous} invById={invById} onChanged={onChanged} />
            ) : null}

            {recent.length > 0 ? <RecentActivity receipts={recent.slice(0, 4)} /> : null}
        </div>
    );
}

function ConfirmPaidBlock({ invoices, onChanged }) {
    return (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/30 p-5" data-testid="payments-confirm">
            <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-emerald-800" />
                <div className="font-heading font-semibold text-sm text-emerald-950">
                    Confirm you received it
                </div>
            </div>
            <p className="mt-1 text-xs text-emerald-900/70">
                We spotted a payment on these invoices — one tap when it lands in your account.
            </p>
            <div className="mt-3 space-y-2">
                {invoices.map((inv) => (
                    <ConfirmRow key={inv._id} inv={inv} onChanged={onChanged} />
                ))}
            </div>
        </div>
    );
}

function ConfirmRow({ inv, onChanged }) {
    const [busy, setBusy] = useState(false);
    const label = inv.counterparty_name || inv.counterparty_email || "Client";
    const quote = inv.payment_claim_quote;

    async function confirm() {
        setBusy(true);
        try {
            await api.post(`/invoices/${inv._id}/action`, { action: "mark_paid" });
            toast.success("Marked as received");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    async function deny() {
        setBusy(true);
        try {
            await api.post(`/invoices/${inv._id}/action`, { action: "deny_payment_claim" });
            toast.success("Kept open — we'll keep watching");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div
            className="rounded-md border border-emerald-200/80 bg-white p-3"
            data-testid="payment-confirm-row">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="text-sm min-w-0">
                    <span className="font-medium">{label}</span>
                    <span className="text-muted-foreground">
                        {" · "}
                        {inv.invoice_ref || "invoice"}
                    </span>
                    <span className="text-muted-foreground"> · </span>
                    <span className="font-mono tabular-nums">
                        {formatMoney(inv.amount, inv.currency)}
                    </span>
                </div>
            </div>
            {quote ? (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-2">&ldquo;{quote}&rdquo;</p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2">
                <button
                    onClick={confirm}
                    disabled={busy}
                    data-testid="payment-confirm-yes"
                    className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50">
                    Yes, received
                </button>
                <button
                    onClick={deny}
                    disabled={busy}
                    data-testid="payment-confirm-no"
                    className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50">
                    Not yet
                </button>
            </div>
        </div>
    );
}

function SpottedBlock({ receipts, invById, onChanged }) {
    const [expanded, setExpanded] = useState(false);
    const [busyAll, setBusyAll] = useState(false);
    const openInvoices = [...invById.values()].filter((i) => OPEN_INVOICE_STATUSES.includes(i.status));
    const withGuess = receipts.filter((rc) => guessInvoiceForReceipt(openInvoices, rc));
    const noise = receipts.filter((rc) => !guessInvoiceForReceipt(openInvoices, rc));
    const preview = expanded ? receipts : receipts.slice(0, 4);

    async function dismissAll() {
        setBusyAll(true);
        try {
            const { data } = await api.post("/receipts/dismiss-unmatched");
            toast.success(`Dismissed ${data.dismissed ?? receipts.length} spotted emails`);
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusyAll(false);
        }
    }

    return (
        <div className="rounded-2xl border border-border bg-card p-5" data-testid="payments-spotted">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                    <div className="font-heading font-semibold text-sm">Payments we spotted</div>
                    <p className="mt-1 text-xs text-muted-foreground max-w-xl">
                        Processor or bank emails Scotive parsed from your inbox. Many are subscriptions or
                        charges you paid — not client payments. Only link one if the amount matches an open
                        invoice.
                    </p>
                </div>
                {receipts.length > 1 ? (
                    <button
                        type="button"
                        onClick={dismissAll}
                        disabled={busyAll}
                        className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground hover:text-foreground disabled:opacity-50 shrink-0"
                        data-testid="payments-dismiss-all">
                        Dismiss all ({receipts.length})
                    </button>
                ) : null}
            </div>
            {withGuess.length === 0 && noise.length > 0 ? (
                <p className="mt-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                    None of these match an open invoice amount — they&apos;re probably not client payments.
                    Use &ldquo;Dismiss all&rdquo; to clear the list.
                </p>
            ) : null}
            <div className="mt-3 space-y-2">
                {preview.map((rc) => (
                    <SpottedRow key={rc._id} rc={rc} openInvoices={openInvoices} onChanged={onChanged} />
                ))}
            </div>
            {receipts.length > 4 ? (
                <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                    {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    {expanded ? "Show less" : `Show ${receipts.length - 4} more`}
                </button>
            ) : null}
        </div>
    );
}

function SpottedRow({ rc, openInvoices, onChanged }) {
    const [busy, setBusy] = useState(false);
    const guess = guessInvoiceForReceipt(openInvoices, rc);

    async function confirmGuess() {
        if (!guess) return;
        setBusy(true);
        try {
            await api.post(`/receipts/${rc._id}/match`, { invoice_id: guess._id });
            toast.success("Linked — confirm when it lands");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    async function dismiss() {
        setBusy(true);
        try {
            await api.post(`/receipts/${rc._id}/reject`);
            toast.success("Dismissed");
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="rounded-md border border-border bg-muted/20 p-3">
            <div className="text-sm">
                <span className="font-medium">{formatMoney(rc.amount, rc.currency)}</span>
                <span className="text-muted-foreground"> from </span>
                <span className="font-medium">{rc.payer_name || "processor"}</span>
                <span className="text-muted-foreground"> · {formatDate(rc.source_date)}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
                {guess ? (
                    <button
                        onClick={confirmGuess}
                        disabled={busy}
                        data-testid="payment-spotted-confirm"
                        className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                        Link to {guess.counterparty_name || guess.counterparty_email}
                        {guess.invoice_ref ? ` · ${guess.invoice_ref}` : ""}
                    </button>
                ) : (
                    <span className="text-[11px] text-muted-foreground self-center">
                        No matching open invoice
                    </span>
                )}
                <button
                    onClick={dismiss}
                    disabled={busy}
                    data-testid="payment-spotted-dismiss"
                    className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50">
                    Not for me
                </button>
            </div>
        </div>
    );
}

function AmbiguousCollapsible({ receipts, invById, onChanged }) {
    const [open, setOpen] = useState(false);

    return (
        <div className="rounded-2xl border border-border/80 bg-muted/10 p-4" data-testid="payments-ambiguous">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="flex w-full items-center justify-between gap-2 text-left">
                <span className="text-xs text-muted-foreground">
                    {receipts.length} payment{receipts.length === 1 ? "" : "s"} could match more than one
                    invoice
                </span>
                {open ? (
                    <ChevronUp className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                ) : (
                    <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                )}
            </button>
            {open ? (
                <div className="mt-3 space-y-2">
                    {receipts.map((rc) => (
                        <AmbiguousRow key={rc._id} rc={rc} invById={invById} onChanged={onChanged} />
                    ))}
                </div>
            ) : null}
        </div>
    );
}

function AmbiguousRow({ rc, invById, onChanged }) {
    const [busy, setBusy] = useState(false);

    async function pick(invoiceId) {
        setBusy(true);
        try {
            await api.post(`/receipts/${rc._id}/match`, { invoice_id: invoiceId });
            toast.success("Linked — confirm when it lands");
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
            toast.success("Dismissed");
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
        <div className="rounded-md border border-border bg-white p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="text-sm">
                    <span className="font-medium">{formatMoney(rc.amount, rc.currency)}</span>
                    <span className="text-muted-foreground"> · {rc.payer_name || "Unknown"}</span>
                </div>
                <button
                    onClick={reject}
                    disabled={busy}
                    className="text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50">
                    Dismiss
                </button>
            </div>
            <div className="mt-2 space-y-1">
                {candidates.map((inv) => (
                    <button
                        key={inv._id}
                        onClick={() => pick(inv._id)}
                        disabled={busy}
                        data-testid="receipt-candidate-btn"
                        className="w-full flex items-baseline justify-between gap-3 rounded border border-border px-3 py-2 text-left text-sm hover:bg-muted/40 disabled:opacity-50">
                        <span>
                            {inv.counterparty_name || inv.counterparty_email}
                            {inv.invoice_ref ? ` · ${inv.invoice_ref}` : ""}
                        </span>
                        <span className="font-mono text-xs tabular-nums">
                            {formatMoney(inv.balance_remaining ?? inv.amount, inv.currency)}
                        </span>
                    </button>
                ))}
            </div>
        </div>
    );
}

function RecentActivity({ receipts }) {
    const [open, setOpen] = useState(false);
    if (!receipts.length) return null;

    return (
        <div className="text-xs text-muted-foreground" data-testid="payments-recent">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1.5 hover:text-foreground">
                <CheckCircle2 className="w-3 h-3" />
                {receipts.length} recent payment{receipts.length === 1 ? "" : "s"} linked
                {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {open ? (
                <div className="mt-2 space-y-1 pl-5">
                    {receipts.map((rc) => (
                        <div key={rc._id} className="flex justify-between gap-2">
                            <span>
                                {formatMoney(rc.applied_amount ?? rc.amount, rc.currency)} from{" "}
                                {rc.payer_name || "processor"}
                            </span>
                            <span className="font-mono shrink-0">{formatDate(rc.source_date)}</span>
                        </div>
                    ))}
                </div>
            ) : null}
        </div>
    );
}
