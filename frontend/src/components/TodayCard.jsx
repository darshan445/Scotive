import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, MessageSquareWarning, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { formatMoney } from "@/components/LedgerCard";

const SECTIONS = [
    { key: "due_overdue", label: "Due / overdue", icon: Wallet, tone: "red", testid: "digest-due" },
    { key: "broken_promises", label: "Broken promises", icon: AlertTriangle, tone: "amber", testid: "digest-broken" },
    { key: "needs_reply", label: "Needs reply", icon: MessageSquareWarning, tone: "slate", testid: "digest-reply" },
    { key: "resolved", label: "Resolved", icon: CheckCircle2, tone: "green", testid: "digest-resolved" },
];

const TONE = {
    red: "border-red-200 bg-red-50 text-red-800",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    slate: "border-border bg-muted/40 text-foreground",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
};

export function TodayCard() {
    const [data, setData] = useState(null);
    useEffect(() => {
        api.post("/lifecycle/run").catch(() => {}).finally(() => {
            api.get("/digest/today").then(({ data }) => setData(data)).catch(() => {});
        });
    }, []);
    if (!data) return null;

    return (
        <div className="rounded-2xl border border-border bg-card p-6" data-testid="today-card">
            <div className="flex items-baseline justify-between mb-4">
                <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Today</div>
                    <h2 className="font-heading font-bold text-2xl tracking-tight">Your daily surface</h2>
                </div>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
                {SECTIONS.map((s) => {
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
                            <ul className="mt-3 space-y-1.5 text-xs">
                                {rows.slice(0, 3).map((r) => (
                                    <li key={r._id} className="flex items-center justify-between gap-2 truncate">
                                        <span className="truncate">{r.counterparty_name || r.counterparty_email || "—"}</span>
                                        <span className="font-mono tabular-nums flex-shrink-0">{formatMoney(r.amount, r.currency || "USD")}</span>
                                    </li>
                                ))}
                                {rows.length > 3 ? <li className="text-[11px] opacity-70">+{rows.length - 3} more</li> : null}
                                {rows.length === 0 ? <li className="text-[11px] opacity-60">Nothing here today.</li> : null}
                            </ul>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
