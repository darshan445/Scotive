"use client";
import { useCallback, useEffect, useState } from "react";
import { Check, ChevronUp, Pencil, Quote, ShieldOff, X } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { ReviewQueueSkeleton } from "@/components/PageSkeletons";
import { api, extractError } from "@/lib/api";
import { formatDate, formatMoney } from "@/components/LedgerCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { notifyWorkspaceRefresh, useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

/** PRD §13 — user-facing reason copy (not internal codes). */
const REVIEW_REASONS = {
    sweep_low_conf: {
        label: "Uncertain read",
        detail: "Scotive isn't sure enough to put this in your ledger without you checking the numbers.",
    },
    low_confidence: {
        label: "Uncertain read",
        detail: "Scotive isn't sure enough to put this in your ledger without you checking the numbers.",
    },
    missing_anchor: {
        label: "No sent-invoice link",
        detail: "We found an amount but couldn't tie it to an invoice you sent from Gmail.",
    },
    amount_mismatch_duplicate_ref: {
        label: "Conflicting amount",
        detail: "This invoice number already exists in your ledger with a different amount.",
    },
    sweep_event: {
        label: "Reply needs a decision",
        detail: "A client reply might change invoice status — confirm before it affects chasing.",
    },
    sweep_unmatched: {
        label: "Unmatched payment mention",
        detail: "We spotted money language but couldn't map it to a tracked invoice.",
    },
    vendor_domain: {
        label: "Likely a bill you received",
        detail: "This looks like money you owe, not money owed to you.",
    },
    vendor_domain_backfill: {
        label: "Likely a bill you received",
        detail: "Moved here during cleanup — probably not a client invoice.",
    },
};

const KIND_LABELS = {
    invoice_sent: "Outgoing invoice",
    receipt: "Payment receipt",
    payment_promise: "Payment promise",
    payment_claimed: "Payment claim",
    dispute: "Dispute",
    partial_payment: "Partial payment",
    none: "Mention",
};

function reasonCopy(it) {
    const base = REVIEW_REASONS[it.review_reason] || {
        label: "Needs your eyes",
        detail: "Confirm the fields below before anything hits your ledger.",
    };
    if (it.review_reason === "amount_mismatch_duplicate_ref" && it.existing_amount != null) {
        return {
            ...base,
            detail: `${base.detail} Ledger currently shows ${formatMoney(it.existing_amount, it.currency || "USD")}.`,
        };
    }
    return base;
}

function ReviewCard({ item, onChanged }) {
    const [editing, setEditing] = useState(false);
    const [busy, setBusy] = useState(false);
    const [form, setForm] = useState({
        amount: item.amount ?? "",
        invoice_ref: item.invoice_ref ?? "",
        counterparty_name: item.counterparty_name ?? "",
        counterparty_email: item.counterparty_email ?? "",
        due_date: item.due_date ? String(item.due_date).slice(0, 10) : "",
    });

    const reason = reasonCopy(item);
    const kindLabel = KIND_LABELS[item.kind] || (item.kind || "item").replace(/_/g, " ");

    async function act(action, body) {
        setBusy(true);
        try {
            await api.post(`/review-queue/${item._id}/${action}`, body);
            const msg =
                action === "confirm"
                    ? "Added to ledger"
                    : action === "reject"
                      ? "Dismissed"
                      : "Sender suppressed";
            toast.success(msg);
            onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    function confirm() {
        if (editing) {
            const amount = parseFloat(form.amount);
            if (!Number.isFinite(amount) || amount <= 0) {
                toast.error("Enter a valid amount");
                return;
            }
            act("confirm", {
                amount,
                invoice_ref: form.invoice_ref || undefined,
                counterparty_name: form.counterparty_name || undefined,
                counterparty_email: form.counterparty_email || undefined,
                due_date: form.due_date || undefined,
            });
            return;
        }
        act("confirm", {});
    }

    return (
        <li className="rounded-2xl border border-border bg-card p-5" data-testid="review-card">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                        {kindLabel}
                    </div>
                    <div className="font-heading font-semibold text-lg mt-0.5">
                        {item.counterparty_name || item.counterparty_email || "Unknown"}
                    </div>
                    {item.counterparty_email ? (
                        <div className="text-[11px] font-mono text-muted-foreground truncate">
                            {item.counterparty_email}
                        </div>
                    ) : null}
                </div>
                <div className="text-right shrink-0">
                    <div className="font-mono tabular-nums text-lg">
                        {formatMoney(item.amount, item.currency || "USD")}
                    </div>
                    {item.invoice_ref ? (
                        <div className="text-[11px] font-mono text-muted-foreground">{item.invoice_ref}</div>
                    ) : null}
                </div>
            </div>

            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-950">
                <span className="font-medium">{reason.label}</span>
                <span className="text-amber-900/80"> — {reason.detail}</span>
            </div>

            <dl className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="rounded-md border border-border/80 bg-muted/20 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Amount</dt>
                    <dd className="font-mono tabular-nums mt-0.5">{formatMoney(item.amount, item.currency || "USD")}</dd>
                </div>
                <div className="rounded-md border border-border/80 bg-muted/20 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Invoice #</dt>
                    <dd className="font-mono mt-0.5 truncate">{item.invoice_ref || "—"}</dd>
                </div>
                <div className="rounded-md border border-border/80 bg-muted/20 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Due</dt>
                    <dd className="mt-0.5">{item.due_date ? formatDate(item.due_date) : "—"}</dd>
                </div>
                <div className="rounded-md border border-border/80 bg-muted/20 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Status</dt>
                    <dd className="mt-0.5 capitalize">{(item.status || "invoiced").replace(/_/g, " ")}</dd>
                </div>
            </dl>

            {(item.source_subject || item.source_from) ? (
                <div className="mt-3 text-xs text-muted-foreground" data-testid="review-source">
                    <span className="font-mono uppercase tracking-wider text-[10px]">Source · </span>
                    {item.source_from ? <span className="font-mono">{item.source_from}</span> : null}
                    {item.source_subject ? (
                        <span className="block sm:inline sm:ml-2 truncate">{item.source_subject}</span>
                    ) : null}
                    {item.source_date || item.created_at ? (
                        <span className="block sm:inline sm:ml-2">· {formatDate(item.source_date || item.created_at)}</span>
                    ) : null}
                </div>
            ) : null}

            {item.evidence_sentence ? (
                <div className="mt-3 flex gap-2 text-sm italic rounded-md border border-border bg-muted/40 px-3 py-2">
                    <Quote className="w-3.5 h-3.5 mt-1 text-muted-foreground flex-shrink-0" />
                    <span>&ldquo;{item.evidence_sentence}&rdquo;</span>
                </div>
            ) : null}

            {editing ? (
                <div className="mt-4 grid sm:grid-cols-2 gap-3 rounded-lg border border-border bg-muted/10 p-3" data-testid="review-edit-form">
                    <div className="space-y-1">
                        <Label htmlFor={`amount-${item._id}`} className="text-xs">Amount</Label>
                        <Input
                            id={`amount-${item._id}`}
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.amount}
                            onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor={`ref-${item._id}`} className="text-xs">Invoice #</Label>
                        <Input
                            id={`ref-${item._id}`}
                            value={form.invoice_ref}
                            onChange={(e) => setForm((f) => ({ ...f, invoice_ref: e.target.value }))}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor={`name-${item._id}`} className="text-xs">Client name</Label>
                        <Input
                            id={`name-${item._id}`}
                            value={form.counterparty_name}
                            onChange={(e) => setForm((f) => ({ ...f, counterparty_name: e.target.value }))}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor={`email-${item._id}`} className="text-xs">Client email</Label>
                        <Input
                            id={`email-${item._id}`}
                            type="email"
                            value={form.counterparty_email}
                            onChange={(e) => setForm((f) => ({ ...f, counterparty_email: e.target.value }))}
                        />
                    </div>
                    <div className="space-y-1 sm:col-span-2">
                        <Label htmlFor={`due-${item._id}`} className="text-xs">Due date</Label>
                        <Input
                            id={`due-${item._id}`}
                            type="date"
                            value={form.due_date}
                            onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
                        />
                    </div>
                </div>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button
                    size="sm"
                    onClick={confirm}
                    disabled={busy}
                    className="bg-foreground text-background hover:bg-foreground/90"
                    data-testid="review-confirm-button">
                    <Check className="w-3.5 h-3.5 mr-1.5" />
                    {editing ? "Save & track" : "Confirm"}
                </Button>
                <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing((v) => !v)}
                    disabled={busy}
                    data-testid="review-edit-toggle">
                    {editing ? <ChevronUp className="w-3.5 h-3.5 mr-1.5" /> : <Pencil className="w-3.5 h-3.5 mr-1.5" />}
                    {editing ? "Hide fields" : "Edit first"}
                </Button>
                <Button
                    size="sm"
                    variant="outline"
                    onClick={() => act("reject")}
                    disabled={busy}
                    data-testid="review-reject-button">
                    <X className="w-3.5 h-3.5 mr-1.5" /> Not payment-related
                </Button>
                <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => act("suppress")}
                    disabled={busy}
                    data-testid="review-suppress-button">
                    <ShieldOff className="w-3.5 h-3.5 mr-1.5" /> Suppress sender
                </Button>
            </div>
        </li>
    );
}

export default function ReviewQueuePage() {
    const [items, setItems] = useState(null);
    const [err, setErr] = useState("");

    const load = useCallback(async () => {
        try {
            const { data } = await api.get("/review-queue");
            setItems(data.items);
        } catch (e) {
            setErr(extractError(e));
        }
    }, []);

    const refresh = useCallback(async () => {
        await load();
        notifyWorkspaceRefresh();
    }, [load]);

    useEffect(() => {
        load();
    }, [load]);

    useWorkspaceRefreshEffect(load);

    return (
        <AppShell testId="review-page" width="5xl" mainClassName="py-10 md:py-14 space-y-8">
            <div>
                <div className="eyebrow mb-2">Review queue</div>
                <h1 className="type-display text-3xl md:text-4xl">Check before it hits the ledger</h1>
                <p className="type-body mt-2 text-base max-w-2xl">
                    Low-confidence reads and ambiguous mappings land here with the exact quote and source email.
                    Nothing is tracked until you confirm — edit the fields if something looks off, or dismiss if it&apos;s not payment-related.
                </p>
            </div>
            {err ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>
            ) : null}
            {items === null ? (
                <ReviewQueueSkeleton />
            ) : items.length === 0 ? (
                <div
                    className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground"
                    data-testid="review-empty">
                    Nothing to review — no uncertain extractions waiting on you.
                </div>
            ) : (
                <ul className="space-y-4" data-testid="review-list">
                    {items.map((it) => (
                        <ReviewCard key={it._id} item={it} onChanged={refresh} />
                    ))}
                </ul>
            )}
        </AppShell>
    );
}
