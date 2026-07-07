import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TopNav } from "@/components/TopNav";
import { api, extractError } from "@/lib/api";
import { formatDate, formatMoney, formatOpenTotals } from "@/components/LedgerCard";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

export default function ClientsPage() {
    const [clients, setClients] = useState(null);
    const [err, setErr] = useState("");

    const load = useCallback(() => {
        api.get("/clients").then(({ data }) => setClients(data.clients)).catch((e) => setErr(extractError(e)));
    }, []);

    useEffect(() => { load(); }, [load]);
    useWorkspaceRefreshEffect(load);

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="clients-page">
            <TopNav />
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-14 space-y-8">
                <div>
                    <div className="eyebrow mb-2">Clients</div>
                    <h1 className="font-heading font-bold text-3xl md:text-4xl tracking-tight">Everyone who owes you</h1>
                </div>
                {err ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div> : null}
                {clients === null ? (
                    <div className="text-sm text-muted-foreground">Loading…</div>
                ) : clients.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="clients-empty">
                        No clients yet. Run a scan first.
                    </div>
                ) : (
                    <div className="rounded-2xl border border-border bg-card overflow-hidden">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-border bg-muted/40 text-left">
                                    <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Client</th>
                                    <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Open balance</th>
                                    <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Invoices</th>
                                    <th className="px-4 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Last activity</th>
                                </tr>
                            </thead>
                            <tbody>
                                {clients.map((c) => (
                                    <tr key={c.email} className="border-b border-border/60 hover:bg-muted/30" data-testid="clients-row">
                                        <td className="px-4 py-3">
                                            <Link to={`/clients/${encodeURIComponent(c.email)}`} className="font-medium hover:underline" data-testid="clients-row-link">
                                                {c.name || c.email}
                                            </Link>
                                            {c.name ? <div className="text-[11px] font-mono text-muted-foreground">{c.email}</div> : null}
                                        </td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums">
                                            {formatOpenTotals(c.open_by_currency ?? c.open_amount)}
                                        </td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-muted-foreground">{c.invoice_count}</td>
                                        <td className="px-4 py-3 text-sm text-muted-foreground">{formatDate(c.last_activity)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </main>
        </div>
    );
}
