"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ClientsTableSkeleton } from "@/components/PageSkeletons";
import { api, extractError, unwrapData } from "@/lib/api";
import { formatDate, formatOpenTotals } from "@/components/LedgerCard";
import { useWorkspaceRefreshEffect } from "@/lib/workspaceRefresh";

export default function ClientsPage() {
    const router = useRouter();
    const [clients, setClients] = useState(null);
    const [err, setErr] = useState("");

    const load = useCallback(() => {
        api.get("/v1/clients").then(({ data }) => setClients(unwrapData(data).clients)).catch((e) => setErr(extractError(e)));
    }, []);

    useEffect(() => { load(); }, [load]);
    useWorkspaceRefreshEffect(load);

    function openClient(email) {
        router.push(`/clients/${encodeURIComponent(email)}`);
    }

    return (
        <AppShell testId="clients-page" mainClassName="py-10 md:py-14 space-y-8">
            <div>
                <div className="eyebrow mb-2">Clients</div>
                <h1 className="type-display text-3xl md:text-4xl">Everyone who owes you</h1>
            </div>
            {err ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div> : null}
            {clients === null ? (
                <ClientsTableSkeleton />
            ) : clients.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="clients-empty">
                    No clients yet. Run a scan first.
                </div>
            ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-border bg-muted/40 text-left">
                                <th className="px-4 py-3 type-label text-muted-foreground">Client</th>
                                <th className="px-4 py-3 type-label text-muted-foreground text-right">Open balance</th>
                                <th className="px-4 py-3 type-label text-muted-foreground text-right">Invoices</th>
                                <th className="px-4 py-3 type-label text-muted-foreground">Last activity</th>
                            </tr>
                        </thead>
                        <tbody>
                            {clients.map((c) => (
                                <tr
                                    key={c.email}
                                    role="link"
                                    tabIndex={0}
                                    onClick={() => openClient(c.email)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault();
                                            openClient(c.email);
                                        }
                                    }}
                                    className="border-b border-border/60 hover:bg-muted/30 cursor-pointer"
                                    data-testid="clients-row"
                                >
                                    <td className="px-4 py-3">
                                        <div className="font-medium" data-testid="clients-row-link">
                                            {c.name || c.email}
                                        </div>
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
        </AppShell>
    );
}
