import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, Clock, HelpCircle, MessageSquareWarning, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";
import { formatMoney } from "@/components/LedgerCard";
import { factualDigestLine, invoiceSubject, isJunkInvoiceRef } from "@/lib/invoiceCopy";
import { ClientMergePrompts } from "@/components/ClientMergePrompts";
import { InvoiceOverflowMenu } from "@/components/InvoiceOverflowMenu";
import { navigateToInvoice } from "@/lib/invoiceNavigation";

/** Urgency order: money at risk → quick confirms → needs reply. */
const ACTION_SECTIONS = [
    { key: "due_overdue", label: "Past due", icon: Wallet, tone: "red", testid: "digest-due" },
    { key: "broken_promises", label: "Broken promise", icon: AlertTriangle, tone: "amber", testid: "digest-broken" },
    { key: "confirm_prompts", label: "Confirm payment", icon: HelpCircle, tone: "violet", testid: "digest-confirm" },
    { key: "stale_prompts", label: "Gone quiet", icon: Clock, tone: "stone", testid: "digest-stale" },
    { key: "needs_reply", label: "Needs your reply", icon: MessageSquareWarning, tone: "slate", testid: "digest-reply" },
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

function sortByAmountDesc(rows) {
    return [...(rows || [])].sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0));
}

function cardLabel(r, sectionKey) {
    if (sectionKey === "needs_reply" && (r.status === "disputed" || r.disputed_claim_amount != null)) {
        return "Disputed";
    }
    return ACTION_SECTIONS.find((s) => s.key === sectionKey)?.label || sectionKey;
}

export function TodayCard({ onChanged }) {
    const navigate = useNavigate();
    const location = useLocation();
    const [data, setData] = useState(null);

    const refresh = useCallback(() => {
        api.post("/lifecycle/run").catch(() => {}).finally(() => {
            api.get("/digest/today").then(({ data: d }) => setData(d)).catch(() => {});
        });
    }, []);

    const handleChanged = useCallback(async () => {
        refresh();
        await onChanged?.();
    }, [refresh, onChanged]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    useWorkspaceRefreshEffect(refresh);

    const actionSections = useMemo(() => {
        if (!data) return [];
        return ACTION_SECTIONS
            .map((s) => ({ ...s, rows: sortByAmountDesc(data[s.key] || []) }))
            .filter((s) => s.rows.length > 0);
    }, [data]);

    if (!data) return null;

    const actionCount = actionSections.reduce((n, s) => n + s.rows.length, 0);
    const mergePrompts = data.merge_prompts || [];
    const hasMergePrompts = mergePrompts.length > 0;

    if (actionCount === 0 && !hasMergePrompts) {
        return null;
    }

    if (actionCount === 0) {
        return (
            <div className="space-y-4" data-testid="today-card-wrapper">
                <ClientMergePrompts
                    prompts={mergePrompts}
                    onChanged={() => {
                        refresh();
                        onChanged?.();
                    }}
                />
            </div>
        );
    }

    return (
        <div className="space-y-4" data-testid="today-card-wrapper">
            {hasMergePrompts ? (
                <ClientMergePrompts
                    prompts={mergePrompts}
                    onChanged={() => {
                        refresh();
                        onChanged?.();
                    }}
                />
            ) : null}
            <div className="surface-card overflow-hidden" data-testid="today-card">
                <div className="px-6 py-5 border-b border-border flex items-center justify-between">
                    <div>
                        <h2 className="font-heading font-bold text-xl tracking-tight">Needs you today</h2>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            {actionCount} thing{actionCount === 1 ? "" : "s"} — open any to act
                        </p>
                    </div>
                    <span className="stat-number inline-flex items-center justify-center min-w-[36px] h-9 rounded-full bg-primary text-primary-foreground text-base font-bold px-3">
                        {actionCount}
                    </span>
                </div>

                <ul className="divide-y divide-border">
                    {actionSections.map((s) =>
                        s.rows.map((r, i) => {
                            const Icon = s.icon;
                            const subject = invoiceSubject(r);
                            const fact = factualDigestLine(r, s.key);
                            const label = cardLabel(r, s.key);
                            const ref = (r.invoice_ref || "").trim();
                            return (
                                <li key={`${s.key}-${r._id}`}>
                                    <div
                                        role="button"
                                        tabIndex={0}
                                        onClick={() => navigateToInvoice(navigate, location, r._id)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" || e.key === " ") {
                                                e.preventDefault();
                                                navigateToInvoice(navigate, location, r._id);
                                            }
                                        }}
                                        className="w-full text-left px-6 py-4 flex items-start gap-3 hover:bg-muted/40 transition-colors cursor-pointer"
                                        data-testid={i === 0 ? s.testid : undefined}
                                    >
                                        <span className={`mt-0.5 flex-shrink-0 ${TONE_ICON[s.tone]}`}>
                                            <Icon className="w-4 h-4" />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                                <span className="text-sm font-semibold">
                                                    {r.counterparty_name || r.counterparty_email || "—"}
                                                </span>
                                                <span className="font-mono tabular-nums text-sm text-foreground/80">
                                                    {formatMoney(r.amount, r.currency || "USD")}
                                                </span>
                                                <span
                                                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${TONE_BADGE[s.tone]}`}
                                                    data-testid={i === 0 ? `${s.testid}-count` : undefined}
                                                >
                                                    {label}
                                                </span>
                                            </div>
                                            <div className="text-sm text-foreground mt-1 break-words whitespace-normal" data-testid="digest-subject">
                                                {subject}
                                            </div>
                                            {ref && !isJunkInvoiceRef(ref) && ref !== subject ? (
                                                <div className="text-[11px] font-mono text-muted-foreground mt-0.5">{ref}</div>
                                            ) : null}
                                            {fact ? (
                                                <div className="text-xs text-muted-foreground mt-1" data-testid="digest-fact-line">
                                                    {fact}
                                                </div>
                                            ) : null}
                                        </div>
                                        <InvoiceOverflowMenu
                                            invoice={r}
                                            onChanged={handleChanged}
                                            className="flex-shrink-0 -mr-1 -mt-0.5"
                                        />
                                    </div>
                                </li>
                            );
                        }),
                    )}
                </ul>
            </div>
        </div>
    );
}
