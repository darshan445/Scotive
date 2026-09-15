import { CheckCircle2, Loader2, Mail, Sparkles, ListChecks, AlertTriangle } from "lucide-react";

const PHASES = [
    { key: "fetching", label: "Finding sent invoices", icon: Mail, countKey: "clients_found" },
    { key: "filtering", label: "Sweeping client threads", icon: ListChecks, countKey: "messages_swept" },
    { key: "extracting", label: "Analysing clients (AI)", icon: Sparkles, countKey: "ai_extracted" },
    { key: "building", label: "Building your ledger", icon: CheckCircle2, countKey: "invoices_created" },
];

function phaseIndex(phase) {
    const map = { queued: 0, fetching: 0, filtering: 1, extracting: 2, building: 3, complete: 4, error: -1 };
    return map[phase] ?? 0;
}

export function ScanProgressCard({ state }) {
    if (!state?.has_job) return null;
    const counts = state.counts || {};
    const active = phaseIndex(state.phase);
    const isError = state.status === "error";

    return (
        <div className="rounded-2xl border border-border bg-card p-6 md:p-8 shadow-sm" data-testid="scan-progress-card">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <div className="eyebrow">
                        {isError ? "Scan interrupted" : state.status === "complete" ? "Scan complete" : "Scanning your inbox"}
                    </div>
                    <h2 className="type-title text-2xl mt-1">
                        {isError
                            ? "Something went wrong"
                            : state.status === "complete"
                            ? "All done."
                            : `Scanning the last ${state.months ?? 12} months…`}
                    </h2>
                </div>
                {state.status !== "complete" && !isError ? (
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                ) : null}
            </div>

            {isError ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 flex items-start gap-2" data-testid="scan-error">
                    <AlertTriangle className="w-4 h-4 mt-0.5" />
                    <span>{state.error || "Please try again."}</span>
                </div>
            ) : (
                <ol className="space-y-3">
                    {PHASES.map((p, i) => {
                        const done = state.status === "complete" || i < active;
                        const current = i === active && state.status !== "complete";
                        const count = counts[p.countKey] ?? 0;
                        const Icon = p.icon;
                        return (
                            <li
                                key={p.key}
                                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                                    current ? "bg-muted" : ""
                                }`}
                                data-testid={`scan-phase-${p.key}`}
                            >
                                <span
                                    className={`inline-flex items-center justify-center w-8 h-8 rounded-md border ${
                                        done
                                            ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                                            : current
                                            ? "bg-foreground text-background border-foreground"
                                            : "bg-card border-border text-muted-foreground"
                                    }`}
                                >
                                    {done ? <CheckCircle2 className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                                </span>
                                <div className="flex-1 min-w-0">
                                    <div className={`text-sm font-medium ${done || current ? "text-foreground" : "text-muted-foreground"}`}>
                                        {p.label}
                                    </div>
                                </div>
                                <div className="font-mono text-sm tabular-nums text-muted-foreground" data-testid={`scan-count-${p.key}`}>
                                    {count.toLocaleString()}
                                </div>
                            </li>
                        );
                    })}
                </ol>
            )}
        </div>
    );
}
