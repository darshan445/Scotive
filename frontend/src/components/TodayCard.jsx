import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Clock, Eye, HelpCircle, MessageSquareWarning, PartyPopper, Send, Wallet } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";
import { formatDate, formatMoney, NO_DUE_DATE_LABEL } from "@/components/LedgerCard";
import { pastDueDaysLabel, pastDueQuestion, watchingSubtitle } from "@/lib/invoiceCopy";
import { ClientMergePrompts } from "@/components/ClientMergePrompts";

/** Priority order — most urgent first. Actionable sections render as full rows. */
const ACTION_SECTIONS = [
    { key: "due_overdue", label: "Past due", icon: Wallet, tone: "red", testid: "digest-due", actionable: "past_due" },
    { key: "broken_promises", label: "Broken promise", icon: AlertTriangle, tone: "amber", testid: "digest-broken", actionable: "draft" },
    { key: "confirm_prompts", label: "Confirm payment", icon: HelpCircle, tone: "violet", testid: "digest-confirm", actionable: "confirm" },
    { key: "stale_prompts", label: "Gone quiet", icon: Clock, tone: "stone", testid: "digest-stale", actionable: "stale" },
    { key: "needs_reply", label: "Needs your reply", icon: MessageSquareWarning, tone: "slate", testid: "digest-reply", actionable: "reply" },
];

/** Quiet sections — collapsed strip at the bottom. */
const QUIET_SECTIONS = [
    { key: "watching", label: "Watching", icon: Eye, testid: "digest-watching" },
    { key: "resolved", label: "Resolved", icon: CheckCircle2, testid: "digest-resolved" },
];

const TONE_BADGE = {
    red: "bg-red-50 text-red-700 border-red-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
    stone: "bg-stone-100 text-stone-700 border-stone-300",
    slate: "bg-muted text-muted-foreground border-border",
};

const TONE_ICON = {
    red: "text-red-600",
    amber: "text-amber-600",
    violet: "text-violet-600",
    stone: "text-stone-600",
    slate: "text-muted-foreground",
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
    if (key === "broken_promises") {
        return r.promise_date ? `Promised ${formatDate(r.promise_date)} — didn't arrive` : "Promise date passed";
    }
    return null;
}

function ActionButton({ children, primary = false, onClick, testId }) {
    return (
        <button
            type="button"
            onClick={onClick}
            data-testid={testId}
            className={
                primary
                    ? "rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-xs font-semibold hover:bg-primary/90 transition-colors whitespace-nowrap"
                    : "rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors whitespace-nowrap"
            }
        >
            {children}
        </button>
    );
}

export function TodayCard({ onDraftChase, onChanged }) {
    const [data, setData] = useState(null);
    const [quietOpen, setQuietOpen] = useState(false);

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

    const actionSections = ACTION_SECTIONS
        .map((s) => ({ ...s, rows: data[s.key] || [] }))
        .filter((s) => s.rows.length > 0);
    const actionCount = actionSections.reduce((n, s) => n + s.rows.length, 0);
    const quietSections = QUIET_SECTIONS.map((s) => ({ ...s, rows: data[s.key] || [] }));
    const quietCount = quietSections.reduce((n, s) => n + s.rows.length, 0);

    return (
        <div className="space-y-4" data-testid="today-card-wrapper">
            <ClientMergePrompts
                prompts={data.merge_prompts}
                onChanged={() => {
                    refresh();
                    onChanged?.();
                }}
            />
            <div className="surface-card overflow-hidden" data-testid="today-card">
                <div className="px-6 py-5 border-b border-border flex items-center justify-between">
                    <div>
                        <h2 className="font-heading font-bold text-xl tracking-tight">Needs you today</h2>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            {actionCount > 0
                                ? `${actionCount} thing${actionCount === 1 ? "" : "s"} — usually under a minute`
                                : "You're all caught up"}
                        </p>
                    </div>
                    {actionCount > 0 ? (
                        <span className="stat-number inline-flex items-center justify-center min-w-[36px] h-9 rounded-full bg-primary text-primary-foreground text-base font-bold px-3">
                            {actionCount}
                        </span>
                    ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1.5">
                            <PartyPopper className="w-3.5 h-3.5" /> Clear
                        </span>
                    )}
                </div>

                {actionCount === 0 ? (
                    <div className="px-6 py-10 text-center text-sm text-muted-foreground">
                        Nothing needs your attention. Scotive keeps watching your sent mail and client replies.
                    </div>
                ) : (
                    <ul className="divide-y divide-border">
                        {actionSections.map((s) =>
                            s.rows.map((r, i) => {
                                const sub = rowSubtitle(r, s.key);
                                const Icon = s.icon;
                                return (
                                    <li
                                        key={`${s.key}-${r._id}`}
                                        className="px-6 py-4 flex flex-col sm:flex-row sm:items-center gap-3"
                                        data-testid={i === 0 ? s.testid : undefined}
                                    >
                                        <div className="flex items-start gap-3 flex-1 min-w-0">
                                            <span className={`mt-0.5 flex-shrink-0 ${TONE_ICON[s.tone]}`}>
                                                <Icon className="w-4 h-4" />
                                            </span>
                                            <div className="min-w-0">
                                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                                    <span className="text-sm font-semibold truncate">
                                                        {r.counterparty_name || r.counterparty_email || "—"}
                                                    </span>
                                                    <span className="font-mono tabular-nums text-sm text-foreground/80">
                                                        {formatMoney(r.amount, r.currency || "USD")}
                                                    </span>
                                                    <span
                                                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${TONE_BADGE[s.tone]}`}
                                                        data-testid={i === 0 ? `${s.testid}-count` : undefined}
                                                    >
                                                        {s.label}
                                                    </span>
                                                </div>
                                                {sub ? (
                                                    <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{sub}</div>
                                                ) : null}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0 sm:pl-3 pl-7">
                                            {s.actionable === "past_due" ? (
                                                <>
                                                    {onDraftChase ? (
                                                        <ActionButton primary onClick={() => onDraftChase(r)} testId="digest-past-due-draft">
                                                            <span className="inline-flex items-center gap-1.5"><Send className="w-3 h-3" /> Follow up</span>
                                                        </ActionButton>
                                                    ) : null}
                                                    <ActionButton onClick={() => invoiceAction(r._id, "mark_paid")} testId="digest-past-due-paid">
                                                        Mark paid
                                                    </ActionButton>
                                                </>
                                            ) : null}
                                            {s.actionable === "draft" && onDraftChase ? (
                                                <ActionButton primary onClick={() => onDraftChase(r)} testId="digest-draft-btn">
                                                    <span className="inline-flex items-center gap-1.5"><Send className="w-3 h-3" /> Follow up</span>
                                                </ActionButton>
                                            ) : null}
                                            {s.actionable === "reply" && onDraftChase ? (
                                                <ActionButton primary onClick={() => onDraftChase(r)} testId="digest-reply-btn">
                                                    <span className="inline-flex items-center gap-1.5"><Send className="w-3 h-3" /> Reply</span>
                                                </ActionButton>
                                            ) : null}
                                            {s.actionable === "confirm" ? (
                                                <>
                                                    <ActionButton primary onClick={() => invoiceAction(r._id, "mark_paid")} testId="digest-confirm-paid">
                                                        Received
                                                    </ActionButton>
                                                    <ActionButton onClick={() => invoiceAction(r._id, "deny_payment_claim")} testId="digest-deny-claim">
                                                        Not yet
                                                    </ActionButton>
                                                </>
                                            ) : null}
                                            {s.actionable === "stale" ? (
                                                <>
                                                    <ActionButton primary onClick={() => invoiceAction(r._id, "mark_paid")} testId="digest-stale-paid">
                                                        Received
                                                    </ActionButton>
                                                    <ActionButton onClick={() => invoiceAction(r._id, "dismiss_stale")} testId="digest-stale-chase">
                                                        Still chasing
                                                    </ActionButton>
                                                    <ActionButton onClick={() => invoiceAction(r._id, "write_off")} testId="digest-stale-writeoff">
                                                        Write off
                                                    </ActionButton>
                                                </>
                                            ) : null}
                                        </div>
                                    </li>
                                );
                            }),
                        )}
                    </ul>
                )}

                {quietCount > 0 ? (
                    <div className="border-t border-border bg-muted/30">
                        <button
                            type="button"
                            onClick={() => setQuietOpen((v) => !v)}
                            className="w-full px-6 py-3 flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
                            data-testid="digest-quiet-toggle"
                        >
                            <span className="inline-flex items-center gap-4">
                                {quietSections.map((s) => (
                                    <span key={s.key} className="inline-flex items-center gap-1.5" data-testid={s.testid}>
                                        <s.icon className="w-3.5 h-3.5" />
                                        {s.label}
                                        <span className="font-mono tabular-nums font-semibold" data-testid={`${s.testid}-count`}>{s.rows.length}</span>
                                    </span>
                                ))}
                            </span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${quietOpen ? "rotate-180" : ""}`} />
                        </button>
                        {quietOpen ? (
                            <div className="px-6 pb-4 grid sm:grid-cols-2 gap-3">
                                {quietSections.map((s) => (
                                    <div key={s.key} className="rounded-xl border border-border bg-card p-3.5">
                                        <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-2 inline-flex items-center gap-1.5">
                                            <s.icon className="w-3.5 h-3.5" /> {s.label}
                                        </div>
                                        <ul className="space-y-1.5 text-xs">
                                            {s.rows.slice(0, 5).map((r) => (
                                                <li key={r._id} className="flex items-baseline justify-between gap-2">
                                                    <div className="min-w-0">
                                                        <span className="font-medium truncate block">
                                                            {r.counterparty_name || r.counterparty_email || "—"}
                                                        </span>
                                                        {rowSubtitle(r, s.key) ? (
                                                            <span className="text-[10px] text-muted-foreground line-clamp-1">{rowSubtitle(r, s.key)}</span>
                                                        ) : null}
                                                    </div>
                                                    <span className="font-mono tabular-nums flex-shrink-0">{formatMoney(r.amount, r.currency || "USD")}</span>
                                                </li>
                                            ))}
                                            {s.rows.length > 5 ? <li className="text-[10px] text-muted-foreground">+{s.rows.length - 5} more</li> : null}
                                            {s.rows.length === 0 ? (
                                                <li className="text-[10px] text-muted-foreground">
                                                    {s.key === "watching" ? "Nothing being watched yet." : "Nothing here today."}
                                                </li>
                                            ) : null}
                                        </ul>
                                    </div>
                                ))}
                            </div>
                        ) : null}
                    </div>
                ) : null}
            </div>
        </div>
    );
}
