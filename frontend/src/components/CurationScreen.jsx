import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { formatDate, formatMoney } from "@/components/LedgerCard";
import { statusLabel } from "@/lib/invoiceCopy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function groupByClient(candidates) {
    const groups = new Map();
    for (const c of candidates) {
        const key = c.client_identity_key || c.counterparty_email;
        if (!groups.has(key)) {
            groups.set(key, { key, label: c.counterparty_name || c.counterparty_email, email: c.counterparty_email, items: [] });
        }
        groups.get(key).items.push(c);
    }
    return Array.from(groups.values());
}

function initialSelected(candidates) {
    return new Set(candidates.map((c) => c._id));
}

export function CurationScreen({ candidates, onConfirm, busy, scanning = false }) {
    const [selected, setSelected] = useState(() => initialSelected(candidates));
    const [dueDates, setDueDates] = useState({});
    const seenRef = useRef(new Set(candidates.map((c) => c._id)));
    const groups = useMemo(() => groupByClient(candidates), [candidates]);
    const n = candidates.length;

    // Rows stream in while the scan runs — auto-select newcomers without
    // touching rows the user already unticked.
    useEffect(() => {
        const fresh = candidates.filter((c) => !seenRef.current.has(c._id));
        if (!fresh.length) return;
        for (const c of fresh) seenRef.current.add(c._id);
        setSelected((prev) => {
            const next = new Set(prev);
            for (const c of fresh) next.add(c._id);
            return next;
        });
    }, [candidates]);

    function effectiveDueDate(c) {
        if (dueDates[c._id] !== undefined) return dueDates[c._id];
        return c.due_date || null;
    }

    function toggle(id) {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }

    function toggleGroup(items) {
        const ids = items.map((i) => i._id);
        const allOn = ids.every((id) => selected.has(id));
        setSelected((prev) => {
            const next = new Set(prev);
            for (const id of ids) {
                if (allOn) next.delete(id);
                else next.add(id);
            }
            return next;
        });
    }

    function buildDueDatesPayload(ids) {
        const out = {};
        for (const id of ids) {
            const c = candidates.find((x) => x._id === id);
            if (!c) continue;
            if (dueDates[id] !== undefined) {
                out[id] = dueDates[id];
            } else if (!c.due_date) {
                out[id] = null;
            }
        }
        return out;
    }

    async function trackSelected() {
        const ids = [...selected];
        const res = await onConfirm(ids, false, buildDueDatesPayload(ids));
        if (res?.ok) {
            toast.success(ids.length ? `Tracking ${ids.length} invoice${ids.length === 1 ? "" : "s"}` : "Nothing selected");
        } else if (res?.error) {
            toast.error(res.error);
        }
    }

    async function startFresh() {
        const res = await onConfirm([], true, {});
        if (res?.ok) toast.success("Starting fresh — Scotive is watching your sent mail");
        else if (res?.error) toast.error(res.error);
    }

    if (!n) {
        return (
            <div className="rounded-2xl border border-border bg-card p-8 text-center" data-testid="curation-empty">
                <h2 className="font-heading font-bold text-xl">No sent invoices found in the last 90 days</h2>
                <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">
                    Scotive is watching — send your next invoice like you always do and it will appear here.
                </p>
                <Button className="mt-6" onClick={startFresh} disabled={busy} data-testid="curation-start-fresh">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Start watching
                </Button>
            </div>
        );
    }

    return (
        <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="curation-screen">
            <div className="p-6 md:p-8 border-b border-border">
                <div className="eyebrow mb-2">Your last 90 days</div>
                <h2 className="font-heading font-bold text-2xl md:text-3xl tracking-tight">
                    {scanning
                        ? `${n} invoice${n === 1 ? "" : "s"} found so far — still scanning…`
                        : `We found ${n} invoice${n === 1 ? "" : "s"} you sent. Which are still unpaid?`}
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                    {scanning
                        ? "Each invoice appears here the moment its conversation is read — more may still arrive."
                        : "Set due dates inline where needed — Scotive never guesses."}
                </p>
            </div>

            <div className="divide-y divide-border max-h-[min(52vh,520px)] overflow-y-auto">
                {groups.map((g) => {
                    const groupIds = g.items.map((i) => i._id);
                    const allOn = groupIds.every((id) => selected.has(id));
                    return (
                        <div key={g.key} className="p-4 md:px-6">
                            <button
                                type="button"
                                onClick={() => toggleGroup(g.items)}
                                className="flex items-center gap-2 text-left w-full mb-2 group"
                                data-testid="curation-group-toggle">
                                <span className={`w-4 h-4 rounded border flex items-center justify-center ${allOn ? "bg-foreground border-foreground" : "border-border"}`}>
                                    {allOn ? <Check className="w-3 h-3 text-background" /> : null}
                                </span>
                                <span className="font-medium text-sm">{g.label}</span>
                                <span className="text-[11px] font-mono text-muted-foreground">{g.email}</span>
                            </button>
                            <ul className="space-y-2 ml-6">
                                {g.items.map((c) => {
                                    const on = selected.has(c._id);
                                    const extracted = c.due_date;
                                    const picked = dueDates[c._id];
                                    const showPicker = !extracted;
                                    const displayDue = picked !== undefined ? picked : extracted;
                                    const knownStatus = c.enriched_status && c.enriched_status !== "invoiced"
                                        ? statusLabel(c.enriched_status)
                                        : null;
                                    return (
                                        <li key={c._id}>
                                            <div
                                                className={`w-full rounded-lg px-3 py-2.5 transition-colors border ${
                                                    on ? "bg-muted/60 border-border" : "hover:bg-muted/30 border-transparent"
                                                }`}
                                                data-testid="curation-row">
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <button
                                                        type="button"
                                                        onClick={() => toggle(c._id)}
                                                        className="flex items-start gap-2 min-w-0 text-left flex-1">
                                                        <span className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center mt-0.5 ${on ? "bg-foreground border-foreground" : "border-border"}`}>
                                                            {on ? <Check className="w-3 h-3 text-background" /> : null}
                                                        </span>
                                                        <div className="min-w-0 flex-1">
                                                            <div className="font-mono text-sm tabular-nums">{formatMoney(c.amount, c.currency || "USD")}</div>
                                                            <div className="text-[11px] text-muted-foreground break-words whitespace-normal leading-snug mt-0.5">
                                                                {c.source_subject || c.invoice_ref || "Invoice"}
                                                            </div>
                                                            {knownStatus ? (
                                                                <div className="text-[10px] font-mono uppercase tracking-wide text-amber-800 mt-1">
                                                                    {knownStatus}
                                                                    {c.status_evidence ? ` — ${c.status_evidence}` : ""}
                                                                </div>
                                                            ) : null}
                                                        </div>
                                                    </button>
                                                    <div className="text-[11px] font-mono text-muted-foreground text-right flex-shrink-0">
                                                        <div>Sent {formatDate(c.source_date)}</div>
                                                        {displayDue ? (
                                                            <div>Due {formatDate(displayDue)}</div>
                                                        ) : showPicker ? (
                                                            <div className="text-amber-800">No due date yet</div>
                                                        ) : null}
                                                    </div>
                                                </div>
                                                {on && showPicker ? (
                                                    <div className="mt-2 ml-6 flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
                                                        <Input
                                                            type="date"
                                                            value={picked || ""}
                                                            onChange={(e) => setDueDates((d) => ({ ...d, [c._id]: e.target.value || null }))}
                                                            className="h-8 max-w-[160px] text-xs"
                                                            data-testid={`curation-due-${c._id}`}
                                                        />
                                                        <Button
                                                            type="button"
                                                            size="sm"
                                                            variant="ghost"
                                                            className="h-8 text-xs"
                                                            onClick={() => setDueDates((d) => ({ ...d, [c._id]: null }))}
                                                            data-testid={`curation-no-due-${c._id}`}>
                                                            No due date
                                                        </Button>
                                                    </div>
                                                ) : null}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    );
                })}
                {scanning ? (
                    <div className="p-4 md:px-6 flex items-center gap-2 text-sm text-muted-foreground" data-testid="curation-scanning-row">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Reading more conversations…
                    </div>
                ) : null}
            </div>

            <div className="p-4 md:p-6 border-t border-border flex flex-wrap gap-3 justify-end bg-muted/20">
                {scanning ? (
                    <span className="text-xs text-muted-foreground self-center mr-auto">
                        You can curate once the scan finishes.
                    </span>
                ) : null}
                <Button variant="outline" onClick={startFresh} disabled={busy || scanning} data-testid="curation-none">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    None — start fresh
                </Button>
                <Button onClick={trackSelected} disabled={busy || scanning} data-testid="curation-track" className="bg-foreground text-background hover:bg-foreground/90">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Track selected ({selected.size})
                </Button>
            </div>
        </div>
    );
}
