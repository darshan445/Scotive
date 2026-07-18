import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowUpRight, CalendarClock, Loader2, Wallet } from "lucide-react";
import { toast } from "sonner";
import { TopNav } from "@/components/TopNav";
import { EmptyStateHero } from "@/components/EmptyStateHero";
import { ConnectGmailButton } from "@/components/ConnectGmailButton";
import { LedgerCard } from "@/components/LedgerCard";
import { TodayCard } from "@/components/TodayCard";
import { SyncStatusBar } from "@/components/SyncStatusBar";
import { SeedScanProgress } from "@/components/SeedScanProgress";
import { CurationScreen } from "@/components/CurationScreen";
import { WatchingEmptyState } from "@/components/WatchingEmptyState";
import { InvoiceDetectedBanner } from "@/components/InvoiceDetectedBanner";
import { DueDatePromptBanner } from "@/components/DueDatePromptBanner";
import { FollowUpPromptBanner } from "@/components/FollowUpPromptBanner";
import { ChaseDialog } from "@/components/ChaseDialog";
import { formatMoney, formatOpenTotals } from "@/components/LedgerCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useGmailCallbackToast } from "@/hooks/useGmailCallbackToast";
import { useLedger } from "@/hooks/useScan";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useLiveDetection } from "@/hooks/useLiveDetection";
import { useWorkspaceRefresh } from "@/hooks/useWorkspaceRefresh";
import { openLedgerInvoices, historyLedgerInvoices, pausedLedgerInvoices, outstandingBalance } from "@/lib/ledgerInvoices";

const OPEN_STATUSES = new Set(["invoiced", "overdue", "promised", "partially_paid", "promise_broken", "disputed", "paid_unconfirmed"]);

function greeting() {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
}

function StatTile({ label, value, sub, icon: Icon, tone = "default", testId }) {
    const toneCls =
        tone === "red"
            ? "text-red-600"
            : tone === "amber"
              ? "text-amber-600"
              : tone === "green"
                ? "text-emerald-600"
                : "text-foreground";
    return (
        <div className="surface-card p-5 flex flex-col gap-1 min-w-0" data-testid={testId}>
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                {Icon ? <Icon className="w-3.5 h-3.5" /> : null}
                {label}
            </div>
            <div className={`stat-number font-bold text-2xl md:text-[1.7rem] truncate ${toneCls}`}>{value}</div>
            {sub ? <div className="text-xs text-muted-foreground truncate">{sub}</div> : null}
        </div>
    );
}

function StatsStrip({ ledger }) {
    const stats = useMemo(() => {
        const invoices = (ledger?.invoices || []).filter((i) => !i.tracking_paused);
        const open = invoices.filter((i) => OPEN_STATUSES.has(i.status));
        const pastDue = invoices.filter((i) => i.status === "overdue" || i.status === "promise_broken");
        const promised = invoices.filter((i) => i.status === "promised");
        const pastDueByCur = {};
        const openByCur = {};
        for (const i of open) {
            const cur = (i.currency || "USD").toUpperCase();
            openByCur[cur] = (openByCur[cur] || 0) + outstandingBalance(i);
        }
        for (const i of pastDue) {
            const cur = (i.currency || "USD").toUpperCase();
            // A past-due row can't owe $0 — a zeroed balance on an unpaid invoice is
            // a claim artifact ("says paid" → "not yet"); fall back via outstandingBalance.
            let owed = outstandingBalance(i);
            if (owed <= 0) owed = Number(i.amount ?? 0);
            pastDueByCur[cur] = (pastDueByCur[cur] || 0) + owed;
        }
        return { open, pastDue, promised, pastDueByCur, openByCur };
    }, [ledger]);

    if (!ledger) return null;
    const openTotals = stats.openByCur;

    return (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="dashboard-stats">
            <StatTile
                label="Outstanding"
                value={formatOpenTotals(openTotals)}
                sub={`${stats.open.length} open invoice${stats.open.length === 1 ? "" : "s"}`}
                icon={Wallet}
                testId="stat-outstanding"
            />
            <StatTile
                label="Past due / Broken promises"
                value={stats.pastDue.length ? formatOpenTotals(stats.pastDueByCur) : "—"}
                sub={stats.pastDue.length ? `${stats.pastDue.length} need${stats.pastDue.length === 1 ? "s" : ""} action` : "Nothing late. Nice."}
                icon={AlertTriangle}
                tone={stats.pastDue.length ? "red" : "green"}
                testId="stat-past-due"
            />
            <StatTile
                label="Promised"
                value={String(stats.promised.length)}
                sub={stats.promised.length ? "Payment dates being watched" : "No open promises"}
                icon={CalendarClock}
                tone={stats.promised.length ? "amber" : "default"}
                testId="stat-promised"
            />
        </div>
    );
}

export default function DashboardPage() {
    const { status, refresh } = useGmailConnection();
    const connected = status?.connected || status?.status === "revoked";
    const {
        state: onboarding,
        candidates,
        startSeed,
        confirmCuration,
        refresh: refreshOnboarding,
    } = useOnboarding({ enabled: connected });

    const pastOnboarding = onboarding?.phase === "complete" || onboarding?.phase === "watching";
    const onboardingActive =
        onboarding?.phase === "scanning" ||
        onboarding?.phase === "curating" ||
        onboarding?.phase === "needs_seed";

    const { data: ledger, refresh: refreshLedger } = useLedger(pastOnboarding);
    const { refreshAll: refreshWorkspace } = useWorkspaceRefresh({
        refreshLedger,
        refreshOnboarding,
    });

    const refreshAll = useCallback(async () => {
        await refreshWorkspace();
        setFollowUpPrompt(null);
        setDueDatePrompt(null);
    }, [refreshWorkspace]);
    const autoSeedRef = useRef(false);
    const [confirmBusy, setConfirmBusy] = useState(false);
    const [chaseInvoice, setChaseInvoice] = useState(null);
    const [latestDetection, setLatestDetection] = useState(null);
    const [dueDatePrompt, setDueDatePrompt] = useState(null);
    const [followUpPrompt, setFollowUpPrompt] = useState(null);

    const hasOpenInvoices = useMemo(
        () => openLedgerInvoices(ledger?.invoices).length > 0,
        [ledger?.invoices],
    );
    const openInvoiceCount = useMemo(
        () => openLedgerInvoices(ledger?.invoices).length,
        [ledger?.invoices],
    );
    const paidInvoiceCount = useMemo(
        () => historyLedgerInvoices(ledger?.invoices).length,
        [ledger?.invoices],
    );
    const pausedInvoiceCount = useMemo(
        () => pausedLedgerInvoices(ledger?.invoices).length,
        [ledger?.invoices],
    );

    const handleInvoiceDetected = useCallback(async (inv) => {
        setLatestDetection(inv);
        const name = inv.counterparty_name || inv.counterparty_email || "Client";
        toast.success("Invoice detected", {
            description: `${name} · ${formatMoney(inv.amount, inv.currency || "USD")}`,
            duration: 8000,
        });
        await refreshAll();
    }, [refreshAll]);

    const { ackAll } = useLiveDetection({
        enabled: pastOnboarding && status?.connected,
        onDetected: handleInvoiceDetected,
        onDueDatePrompt: (prompt) => setDueDatePrompt(prompt),
        onFollowUpPrompt: (prompt) => setFollowUpPrompt(prompt),
    });

    async function dismissDetection() {
        setLatestDetection(null);
        await ackAll();
    }

    function handleSyncDetected(newInvoices) {
        if (newInvoices?.length) {
            handleInvoiceDetected(newInvoices[newInvoices.length - 1]);
        } else {
            void refreshAll();
        }
    }

    useGmailCallbackToast(
        useCallback(async (result) => {
            await refresh();
            if (result === "connected" || result === "send_missing") {
                autoSeedRef.current = true;
                await startSeed();
                await refreshOnboarding();
            }
        }, [refresh, startSeed, refreshOnboarding]),
    );

    useEffect(() => {
        if (!status?.connected) return;
        refreshOnboarding();
    }, [status?.connected, refreshOnboarding]);

    useEffect(() => {
        if (autoSeedRef.current) return;
        if (!status?.connected) return;
        if (onboarding?.phase === "needs_seed") {
            autoSeedRef.current = true;
            startSeed();
        }
    }, [status?.connected, onboarding?.phase, startSeed]);

    async function handleConfirm(ids, trackNone, dueDates = {}) {
        setConfirmBusy(true);
        const res = await confirmCuration(ids, trackNone, dueDates);
        setConfirmBusy(false);
        if (res?.ok) {
            await refreshAll();
        }
        return res;
    }

    return (
        <div className="min-h-screen bg-background text-foreground" data-testid="dashboard-root">
            <TopNav />
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {status === null ? (
                    <div className="py-32 flex items-center justify-center text-muted-foreground text-sm" data-testid="dashboard-loading">
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Loading your workspace…
                    </div>
                ) : connected ? (
                    <div className="py-8 md:py-12 space-y-6" data-testid="connected-dashboard">
                        <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
                            <div>
                                <div className="eyebrow mb-2">
                                    {pastOnboarding
                                        ? new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })
                                        : "Setup"}
                                </div>
                                <h1 className="font-heading font-bold text-3xl md:text-4xl tracking-tight text-foreground">
                                    {pastOnboarding ? greeting() : "Let's find what you're still owed"}
                                </h1>
                                <p className="mt-1.5 text-base text-muted-foreground">
                                    {onboarding?.phase === "scanning"
                                        ? "Scanning sent invoices from the last 90 days…"
                                        : onboarding?.phase === "curating"
                                          ? "You know your last 90 days — pick what's still unpaid."
                                          : pastOnboarding
                                            ? "Open invoices sorted by what's due next."
                                            : "Forward-tracking from here — not inbox archaeology."}
                                </p>
                            </div>
                            {pastOnboarding ? (
                                <SyncStatusBar
                                    watching
                                    openInvoiceCount={
                                        (ledger?.invoices || []).filter(
                                            (i) => OPEN_STATUSES.has(i.status) && !i.tracking_paused,
                                        ).length
                                    }
                                    onSynced={handleSyncDetected}
                                />
                            ) : null}
                        </div>

                        {onboarding?.phase === "scanning" || onboarding?.phase === "curating" ? (
                            candidates?.length ? (
                                // One mount across scanning → curating so streamed rows and
                                // the user's un-ticks survive the phase flip.
                                <CurationScreen
                                    candidates={candidates}
                                    busy={confirmBusy}
                                    onConfirm={handleConfirm}
                                    scanning={onboarding?.phase === "scanning"}
                                />
                            ) : onboarding?.phase === "scanning" ? (
                                <SeedScanProgress
                                    scanPhase={onboarding?.scan_phase}
                                    counts={onboarding?.counts}
                                />
                            ) : candidates === null ? (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
                                    <Loader2 className="w-4 h-4 animate-spin" /> Loading invoices…
                                </div>
                            ) : (
                                <CurationScreen
                                    candidates={candidates}
                                    busy={confirmBusy}
                                    onConfirm={handleConfirm}
                                />
                            )
                        ) : null}

                        {onboarding?.phase === "needs_seed" ? (
                            <div
                                className="surface-card p-8 flex items-center gap-3 text-sm text-muted-foreground"
                                data-testid="seed-preparing">
                                <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
                                Preparing your invoice scan…
                            </div>
                        ) : null}

                        {!onboardingActive && (status?.status === "revoked" || status?.status === "send_missing") ? (
                            <GmailIssueBanner status={status} />
                        ) : null}

                        {pastOnboarding ? (
                            <>
                                <InvoiceDetectedBanner detection={latestDetection} onDismiss={dismissDetection} />

                                <DueDatePromptBanner
                                    prompt={dueDatePrompt}
                                    onDismiss={() => setDueDatePrompt(null)}
                                    onChanged={refreshAll}
                                />

                                <FollowUpPromptBanner
                                    prompt={followUpPrompt}
                                    onDismiss={() => setFollowUpPrompt(null)}
                                    onChanged={refreshAll}
                                    onReview={(prompt) => {
                                        const inv = (ledger?.invoices || []).find((i) => i._id === prompt.invoice_id);
                                        if (inv) {
                                            setChaseInvoice(inv);
                                            setFollowUpPrompt(null);
                                        }
                                    }}
                                />

                                {hasOpenInvoices ? <StatsStrip ledger={ledger} /> : null}

                                {onboarding?.phase === "watching" && !hasOpenInvoices ? (
                                    <WatchingEmptyState onChanged={refreshAll} />
                                ) : (
                                    <TodayCard onChanged={refreshAll} />
                                )}

                                <Tabs defaultValue="ledger" className="w-full" data-testid="dashboard-tabs">
                                    <TabsList className="bg-muted/60 rounded-full h-auto p-1">
                                        <TabsTrigger value="ledger" className="rounded-full px-4 py-2 text-sm data-[state=active]:shadow-sm" data-testid="tab-ledger">
                                            Open{openInvoiceCount ? ` (${openInvoiceCount})` : ""}
                                        </TabsTrigger>
                                        {pausedInvoiceCount > 0 ? (
                                            <TabsTrigger value="paused" className="rounded-full px-4 py-2 text-sm data-[state=active]:shadow-sm" data-testid="tab-paused">
                                                Paused ({pausedInvoiceCount})
                                            </TabsTrigger>
                                        ) : null}
                                        <TabsTrigger value="paid" className="rounded-full px-4 py-2 text-sm data-[state=active]:shadow-sm" data-testid="tab-paid">
                                            Paid{paidInvoiceCount ? ` (${paidInvoiceCount})` : ""}
                                        </TabsTrigger>
                                    </TabsList>
                                    <TabsContent value="paid" className="mt-4">
                                        <LedgerCard ledger={ledger} onChanged={refreshAll} variant="paid" />
                                    </TabsContent>
                                    {pausedInvoiceCount > 0 ? (
                                        <TabsContent value="paused" className="mt-4">
                                            <LedgerCard ledger={ledger} onChanged={refreshAll} variant="paused" />
                                        </TabsContent>
                                    ) : null}
                                    <TabsContent value="ledger" className="mt-4">
                                        <LedgerCard ledger={ledger} onChanged={refreshAll} variant="open" />
                                    </TabsContent>
                                </Tabs>
                            </>
                        ) : null}
                    </div>
                ) : (
                    <EmptyStateHero />
                )}
            </main>

            <ChaseDialog
                invoice={chaseInvoice}
                open={!!chaseInvoice}
                onOpenChange={(o) => !o && setChaseInvoice(null)}
                onSent={refreshAll}
            />

            <footer className="border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground">
                    <span>© {new Date().getFullYear()} Scotive</span>
                    <span>Payment ops · Inside Gmail</span>
                </div>
            </footer>
        </div>
    );
}

function GmailIssueBanner({ status }) {
    const revoked = status?.status === "revoked";
    return (
        <div
            className="rounded-2xl border border-amber-200 bg-amber-50 p-5 flex flex-col sm:flex-row sm:items-center gap-4"
            data-testid={revoked ? "connection-panel-revoked" : "connection-panel-send-missing"}>
            <div className="flex items-start gap-3 flex-1 min-w-0">
                <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                    <div className="font-heading font-semibold text-amber-900">
                        {revoked ? "Gmail access was revoked" : "Connected — but sending is off"}
                    </div>
                    <div className="text-sm text-amber-800 mt-1">
                        {revoked ? (
                            <>
                                Reconnect to keep your ledger fresh.
                                {status.email ? (
                                    <> Access to <span className="font-mono">{status.email}</span> was removed in Google.</>
                                ) : null}
                            </>
                        ) : (
                            <>
                                Ledger still builds from <span className="font-mono">{status.email}</span>, but one-tap chasers need send permission.
                            </>
                        )}
                    </div>
                    <Link
                        to="/settings"
                        className="inline-flex items-center gap-1 mt-2 text-xs font-semibold text-amber-900 underline underline-offset-2 hover:text-amber-950">
                        Gmail settings <ArrowUpRight className="w-3 h-3" />
                    </Link>
                </div>
            </div>
            <ConnectGmailButton
                label="Reconnect Gmail"
                testId="reconnect-gmail-button"
                variant={revoked ? "default" : "secondary"}
            />
        </div>
    );
}
