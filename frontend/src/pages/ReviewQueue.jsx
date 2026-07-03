import { useEffect, useState } from "react";
import { Check, Quote, ShieldOff, X } from "lucide-react";
import { toast } from "sonner";
import { TopNav } from "@/components/TopNav";
import { api, extractError } from "@/lib/api";
import { formatDate, formatMoney } from "@/components/LedgerCard";
import { Button } from "@/components/ui/button";

export default function ReviewQueuePage() {
    const [items, setItems] = useState(null);
    const [err, setErr] = useState("");

    async function refresh() {
        try {
            const { data } = await api.get("/review-queue");
            setItems(data.items);
        } catch (e) { setErr(extractError(e)); }
    }
    useEffect(() => { refresh(); }, []);

    async function act(id, action) {
        try {
            await api.post(`/review-queue/${id}/${action}`, action === "confirm" ? {} : undefined);
            toast.success(action === "confirm" ? "Added to ledger" : action === "reject" ? "Item rejected" : "Sender suppressed");
            await refresh();
        } catch (e) { toast.error(extractError(e)); }
    }

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="review-page">
            <TopNav />
            <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-14 space-y-8">
                <div>
                    <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">Review queue</div>
                    <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight">Low-confidence items</h1>
                    <p className="mt-2 text-base text-muted-foreground">
                        Anything below the confidence bar lands here. Confirm to add to your ledger, reject if it&apos;s not payment-related, or suppress the sender to keep them out of future scans.
                    </p>
                </div>
                {err ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div> : null}
                {items === null ? (
                    <div className="text-sm text-muted-foreground">Loading…</div>
                ) : items.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="review-empty">
                        Nothing to review. Great signal-to-noise.
                    </div>
                ) : (
                    <ul className="space-y-4" data-testid="review-list">
                        {items.map((it) => (
                            <li key={it._id} className="rounded-2xl border border-border bg-card p-5" data-testid="review-card">
                                <div className="flex flex-wrap items-baseline justify-between gap-2">
                                    <div>
                                        <div className="font-heading font-semibold text-lg">
                                            {it.counterparty_name || it.counterparty_email || "Unknown"}
                                        </div>
                                        {it.counterparty_email ? <div className="text-[11px] font-mono text-muted-foreground">{it.counterparty_email}</div> : null}
                                    </div>
                                    <div className="text-right">
                                        <div className="font-mono tabular-nums text-lg">{formatMoney(it.amount, it.currency || "USD")}</div>
                                        <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-[0.15em]">
                                            {(it.kind || "unknown").replace(/_/g, " ")} · conf {(it.confidence || 0).toFixed(2)}
                                        </div>
                                    </div>
                                </div>
                                {it.source_subject ? (
                                    <div className="mt-2 text-xs font-mono text-muted-foreground truncate">{it.source_subject} · {formatDate(it.source_date || it.created_at)}</div>
                                ) : null}
                                {it.evidence_sentence ? (
                                    <div className="mt-3 flex gap-2 text-sm italic rounded-md border border-border bg-muted/40 px-3 py-2">
                                        <Quote className="w-3.5 h-3.5 mt-1 text-muted-foreground flex-shrink-0" />
                                        <span>&ldquo;{it.evidence_sentence}&rdquo;</span>
                                    </div>
                                ) : null}
                                <div className="mt-4 flex flex-wrap gap-2">
                                    <Button size="sm" onClick={() => act(it._id, "confirm")} className="bg-foreground text-background hover:bg-foreground/90" data-testid="review-confirm-button">
                                        <Check className="w-3.5 h-3.5 mr-1.5" /> Add to ledger
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => act(it._id, "reject")} data-testid="review-reject-button">
                                        <X className="w-3.5 h-3.5 mr-1.5" /> Not payment-related
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => act(it._id, "suppress")} data-testid="review-suppress-button">
                                        <ShieldOff className="w-3.5 h-3.5 mr-1.5" /> Suppress sender
                                    </Button>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </main>
        </div>
    );
}
