import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, Eye, HelpCircle, MessageSquareWarning, Send, Wallet } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";
import { formatDate, formatMoney, NO_DUE_DATE_LABEL } from "@/components/LedgerCard";
import { pastDueDaysLabel, pastDueQuestion, watchingSubtitle } from "@/lib/invoiceCopy";
import { ClientMergePrompts } from "@/components/ClientMergePrompts";

const SECTIONS = [
    { key: "due_overdue", label: "Past due", icon: Wallet, tone: "red", testid: "digest-due", actionable: "past_due" },
    { key: "broken_promises", label: "Broken promises", icon: AlertTriangle, tone: "amber", testid: "digest-broken", actionable: "draft" },
    { key: "confirm_prompts", label: "Confirm payment", icon: HelpCircle, tone: "violet", testid: "digest-confirm", actionable: "confirm" },
    { key: "stale_prompts", label: "Gone quiet", icon: Clock, tone: "stone", testid: "digest-stale", actionable: "stale" },
    { key: "needs_reply", label: "Needs reply", icon: MessageSquareWarning, tone: "slate", testid: "digest-reply", actionable: false },
    { key: "watching", label: "Watching", icon: Eye, tone: "slate", testid: "digest-watching", actionable: false },
    { key: "resolved", label: "Resolved", icon: CheckCircle2, tone: "green", testid: "digest-resolved", actionable: false },
];

const TONE = {
    red: "border-red-200 bg-red-50 text-red-800",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    violet: "border-violet-200 bg-violet-50 text-violet-900",
    stone: "border-stone-300 bg-stone-50 text-stone-800",
    slate: "border-border bg-muted/40 text-foreground",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
};

function rowSubtitle(r, key) {
    if (key === "due_overdue") {
        return pastDueQuestion(r) || pastDueDaysLabel(r.due_date) || null;
    }
    if (key === "watching") {
        const sub = watchingSubtitle(r);
        if (sub) return sub;
        if (r.due_date) return `Due ${formatDate(r.due_date)} — reading replies`;
        return NO_DUE_DATE_LABEL;
    }
    if (key === "confirm_prompts") {
        const q = r.payment_claim_quote;
        if (q) return `“${q.length > 60 ? `${q.slice(0, 60)}…` : q}”`;
        return "Says paid — did you receive it?";
    }
    if (key === "stale_prompts") {
        return "No email activity in 120+ days — still chasing?";
    }
    return null;
}

export function TodayCard({ onDraftChase, onChanged }) {
    const [data, setData] = useState(null);

    const refresh = useCallback(() => {
        api.post("/lifecycle/run").catch(() => {}).finally(() => {
            api.get("/digest/today").then(({ data }) => setData(data)).catch(() => {});
        });
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    useWorkspaceRefreshEffect(refresh);

    async function invoiceAction(id, action) {
        try {
            await api.post(`/invoices/${id}/action`, { action });
            toast.success(
                action === "mark_paid"
                    ? "Marked paid"
                    : action === "write_off"
                      ? "Written off"
                      : action === "dismiss_stale"
                        ? "Back on the chase list"
                        : "Chasing resumed",
            );
            refresh();
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        }
    }

    if (!data) return null;

    const visibleSections = SECTIONS.filter((s) => {
        const rows = data[s.key] || [];
        if (rows.length > 0) return true;
        return s.key === "due_overdue" || s.key === "watching";
    });

    return (
        <div className="space-y-4" data-testid="today-card-wrapper">
            <ClientMergePrompts
                prompts={data.merge_prompts}
                onChanged={() => {
                    refresh();
                    onChanged?.();
                }}
            />
        <div className="rounded-2xl border border-border bg-card p-6" data-testid="today-card">
            <div className="flex items-baseline justify-between mb-4">
                <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Today</div>
                    <h2 className="font-heading font-bold text-2xl tracking-tight">Your daily surface</h2>
                </div>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
                {visibleSections.map((s) => {
                    const rows = data[s.key] || [];
                    const Icon = s.icon;
                    return (
                        <div key={s.key} className={`rounded-xl border p-4 ${TONE[s.tone]}`} data-testid={s.testid}>
                            <div className="flex items-center justify-between">
                                <span className="inline-flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-[0.18em]">
                                    <Icon className="w-3.5 h-3.5" /> {s.label}
                                </span>
                                <span className="font-mono tabular-nums text-sm font-semibold" data-testid={`${s.testid}-count`}>
                                    {rows.length}
                                </span>
                            </div>
                            <ul className="mt-3 space-y-2 text-xs">
                                {rows.slice(0, 4).map((r) => {
                                    const sub = rowSubtitle(r, s.key);
                                    return (
                                        <li key={r._id} className="flex items-start justify-between gap-2">
                                            <div className="min-w-0 flex-1">
                                                <div className="truncate font-medium">
                                                    {r.counterparty_name || r.counterparty_email || "—"}
                                                </div>
                                                <div className="font-mono tabular-nums">{formatMoney(r.amount, r.currency || "USD")}</div>
                                                {sub ? <div className="text-[10px] opacity-80 mt-0.5 line-clamp-2">{sub}</div> : null}
                                            </div>
                                            {s.actionable === "past_due" ? (
                                                <div className="flex flex-col gap-1 flex-shrink-0">
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "mark_paid")}
                                                        className="rounded-md border border-current/25 bg-white/60 px-2 py-1 text-[10px] font-medium hover:bg-white"
                                                        data-testid="digest-past-due-paid">
                                                        Mark paid
                                                    </button>
                                                    {onDraftChase ? (
                                                        <button
                                                            type="button"
                                                            onClick={() => onDraftChase(r)}
                                                            className="inline-flex items-center justify-center gap-1 rounded-md border border-current/20 px-2 py-1 text-[10px] font-medium hover:bg-white/40"
                                                            data-testid="digest-past-due-draft">
                                                            <Send className="w-3 h-3" />
                                                            Follow-up
                                                        </button>
                                                    ) : null}
                                                </div>
                                            ) : null}
                                            {s.actionable === "draft" && onDraftChase ? (
                                                <button
                                                    type="button"
                                                    onClick={() => onDraftChase(r)}
                                                    className="flex-shrink-0 inline-flex items-center gap-1 rounded-md border border-current/20 px-2 py-1 text-[10px] font-medium hover:bg-white/40 transition-colors"
                                                    data-testid="digest-draft-btn">
                                                    <Send className="w-3 h-3" />
                                                    Draft
                                                </button>
                                            ) : null}
                                            {s.actionable === "confirm" ? (
                                                <div className="flex flex-col gap-1 flex-shrink-0">
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "mark_paid")}
                                                        className="rounded-md border border-current/25 bg-white/60 px-2 py-1 text-[10px] font-medium hover:bg-white"
                                                        data-testid="digest-confirm-paid">
                                                        Received
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "deny_payment_claim")}
                                                        className="rounded-md border border-current/15 px-2 py-1 text-[10px] font-medium opacity-80 hover:opacity-100"
                                                        data-testid="digest-deny-claim">
                                                        Not yet
                                                    </button>
                                                </div>
                                            ) : null}
                                            {s.actionable === "stale" ? (
                                                <div className="flex flex-col gap-1 flex-shrink-0">
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "mark_paid")}
                                                        className="rounded-md border border-current/25 bg-white/60 px-2 py-1 text-[10px] font-medium hover:bg-white"
                                                        data-testid="digest-stale-paid">
                                                        Received
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "write_off")}
                                                        className="rounded-md border border-current/20 px-2 py-1 text-[10px] font-medium opacity-90 hover:opacity-100"
                                                        data-testid="digest-stale-writeoff">
                                                        Write off
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => invoiceAction(r._id, "dismiss_stale")}
                                                        className="rounded-md border border-current/15 px-2 py-1 text-[10px] font-medium opacity-80 hover:opacity-100"
                                                        data-testid="digest-stale-chase">
                                                        Still chasing
                                                    </button>
                                                </div>
                                            ) : null}
                                        </li>
                                    );
                                })}
                                {rows.length > 4 ? <li className="text-[11px] opacity-70">+{rows.length - 4} more</li> : null}
                                {rows.length === 0 ? (
                                    <li className="text-[11px] opacity-60">
                                        {s.key === "watching" ? "Nothing being watched yet." : "Nothing here today."}
                                    </li>
                                ) : null}
                            </ul>
                        </div>
                    );
                })}
            </div>
            </div>
        </div>
    );
}
