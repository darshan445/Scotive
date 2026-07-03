import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Quote } from "lucide-react";
import { TopNav } from "@/components/TopNav";
import { api, extractError } from "@/lib/api";
import { formatDate, formatMoney } from "@/components/LedgerCard";

export default function ClientDetailPage() {
    const { email } = useParams();
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        api.get(`/clients/${encodeURIComponent(email)}`)
            .then(({ data }) => setData(data))
            .catch((e) => setErr(extractError(e)));
    }, [email]);

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="client-detail-page">
            <TopNav />
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-14 space-y-8">
                <Link to="/clients" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="back-to-clients">
                    <ArrowLeft className="w-4 h-4" /> All clients
                </Link>

                {err ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div> : null}
                {!data && !err ? <div className="text-sm text-muted-foreground">Loading…</div> : null}

                {data ? (
                    <>
                        <div>
                            <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">Client</div>
                            <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight" data-testid="client-name">
                                {data.name || data.email}
                            </h1>
                            <div className="mt-1 text-sm text-muted-foreground font-mono">{data.email}</div>
                            <div className="mt-6 rounded-2xl border border-border bg-card p-6">
                                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">Open balance</div>
                                <div className="mt-1 font-heading font-black text-3xl md:text-4xl tracking-tight tabular-nums" data-testid="client-open-balance">
                                    {formatMoney(data.total_open)}
                                </div>
                            </div>
                        </div>

                        <section>
                            <h2 className="font-heading font-bold text-xl mb-3">Known email identities</h2>
                            <ul className="rounded-2xl border border-border bg-card divide-y divide-border" data-testid="identities-list">
                                {data.identities.map((id) => (
                                    <li key={id.email} className="px-4 py-3 flex items-center justify-between">
                                        <span className="font-mono text-sm">{id.email}</span>
                                        <span className="text-[11px] font-mono text-muted-foreground">{id.message_count} msg</span>
                                    </li>
                                ))}
                            </ul>
                        </section>

                        <section>
                            <h2 className="font-heading font-bold text-xl mb-3">Invoices & evidence</h2>
                            <div className="space-y-3" data-testid="client-invoices">
                                {data.invoices.map((inv) => (
                                    <div key={inv._id} className="rounded-xl border border-border bg-card p-4">
                                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                                            <div className="font-medium">{inv.invoice_ref || inv.source_subject || "Invoice"}</div>
                                            <div className="font-mono tabular-nums">{formatMoney(inv.amount, inv.currency)}</div>
                                        </div>
                                        <div className="mt-1 text-[11px] font-mono text-muted-foreground">
                                            {inv.status?.replace(/_/g, " ")} · {formatDate(inv.source_date || inv.created_at)}
                                        </div>
                                        {inv.evidence_sentence ? (
                                            <div className="mt-2 flex gap-2 text-sm italic text-foreground">
                                                <Quote className="w-3.5 h-3.5 mt-1 text-muted-foreground flex-shrink-0" />
                                                <span>&ldquo;{inv.evidence_sentence}&rdquo;</span>
                                            </div>
                                        ) : null}
                                    </div>
                                ))}
                            </div>
                        </section>
                    </>
                ) : null}
            </main>
        </div>
    );
}
