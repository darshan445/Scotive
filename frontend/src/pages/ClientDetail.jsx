import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, TrendingUp, AlertTriangle, Clock } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ClientDetailSkeleton } from "@/components/PageSkeletons";
import { api, extractError } from "@/lib/api";
import { formatMoney, formatOpenTotals } from "@/components/LedgerCard";
import { invoiceStatusDateLine, invoiceSubject, isJunkInvoiceRef } from "@/lib/invoiceCopy";
import { navigateToInvoice } from "@/lib/invoiceNavigation";

const RISK_STYLES = {
    on_time: { label: "Pays on time", cls: "bg-green-50 text-green-800 border-green-200", Icon: TrendingUp },
    slow: { label: "Slow payer", cls: "bg-yellow-50 text-yellow-900 border-yellow-200", Icon: Clock },
    risky: { label: "Risky payer", cls: "bg-red-50 text-red-800 border-red-200", Icon: AlertTriangle },
};

function PaymentBehaviorCard({ stats }) {
    if (!stats) return null;
    const risk = RISK_STYLES[stats.risk_hint] || RISK_STYLES.slow;
    const RiskIcon = risk.Icon;
    return (
        <section data-testid="payment-behavior">
            <h2 className="type-title text-xl mb-3">Payment behavior</h2>
            <div className="rounded-2xl border border-border bg-card p-6">
                <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${risk.cls}`}>
                    <RiskIcon className="w-3.5 h-3.5" />
                    {risk.label}
                </div>
                <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <Stat
                        label="Payment cycles"
                        value={stats.payment_cycles}
                        detail={`${stats.payment_cycles} paid invoice${stats.payment_cycles === 1 ? "" : "s"}`}
                        testid="stat-cycles"
                    />
                    <Stat
                        label="Avg. days late"
                        value={stats.avg_days_late == null ? "—" : `${stats.avg_days_late}d`}
                        detail={stats.avg_days_late == null ? "No due-date data" : "vs. due date on paid invoices"}
                        testid="stat-days-late"
                    />
                    <Stat
                        label="Promises kept"
                        value={
                            stats.promise_keep_rate == null
                                ? "—"
                                : `${Math.round(stats.promise_keep_rate * 100)}%`
                        }
                        detail={
                            stats.promise_keep_rate == null
                                ? "No promises made yet"
                                : `${stats.promise_kept} of ${stats.promise_total} promises`
                        }
                        testid="stat-promise-rate"
                    />
                </div>
                <div className="mt-5 text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                    Based on {stats.payment_cycles} completed cycles. Updates as more invoices settle.
                </div>
            </div>
        </section>
    );
}

function Stat({ label, value, detail, testid }) {
    return (
        <div data-testid={testid}>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                {label}
            </div>
            <div className="mt-1 type-title text-2xl tabular-nums">
                {value}
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">{detail}</div>
        </div>
    );
}

export default function ClientDetailPage() {
    const { email } = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        api.get(`/clients/${encodeURIComponent(email)}`)
            .then(({ data }) => setData(data))
            .catch((e) => setErr(extractError(e)));
    }, [email]);

    return (
        <AppShell testId="client-detail-page" mainClassName="py-10 md:py-14 space-y-8">
                <Link to="/clients" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="back-to-clients">
                    <ArrowLeft className="w-4 h-4" /> All clients
                </Link>

                {err ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div> : null}
                {!data && !err ? <ClientDetailSkeleton /> : null}

                {data ? (
                    <>
                        <div>
                            <div className="eyebrow mb-2">Client</div>
                            <h1 className="type-display text-3xl md:text-4xl" data-testid="client-name">
                                {data.name || data.email}
                            </h1>
                            <div className="mt-1 text-sm text-muted-foreground font-mono">{data.email}</div>
                            <div className="mt-6 surface-card p-6">
                                <div className="eyebrow">Open balance</div>
                                <div className="mt-1 stat-number font-bold text-3xl md:text-4xl" data-testid="client-open-balance">
                                    {formatOpenTotals(data.totals_by_currency ?? data.total_open)}
                                </div>
                            </div>
                        </div>

                        <PaymentBehaviorCard stats={data.stats} />

                        <section>
                            <h2 className="type-title text-xl mb-3">Known email identities</h2>
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
                            <h2 className="type-title text-xl mb-3">Invoices</h2>
                            <div className="space-y-3" data-testid="client-invoices">
                                {data.invoices.map((inv) => {
                                    const subject = invoiceSubject(inv);
                                    const ref = (inv.invoice_ref || "").trim();
                                    return (
                                        <button
                                            key={inv._id}
                                            type="button"
                                            onClick={() => navigateToInvoice(navigate, location, inv._id)}
                                            className="w-full text-left rounded-xl border border-border bg-card p-4 hover:bg-muted/30 transition-colors"
                                            data-testid="client-invoice-row"
                                        >
                                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                                                <div className="font-medium break-words whitespace-normal">{subject}</div>
                                                <div className="font-mono tabular-nums flex-shrink-0">{formatMoney(inv.amount, inv.currency)}</div>
                                            </div>
                                            {ref && !isJunkInvoiceRef(ref) && ref !== subject ? (
                                                <div className="text-[11px] font-mono text-muted-foreground mt-0.5">{ref}</div>
                                            ) : null}
                                            <div className="mt-1 text-[11px] font-mono text-muted-foreground">
                                                {invoiceStatusDateLine(inv)}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </section>
                    </>
                ) : null}
        </AppShell>
    );
}
