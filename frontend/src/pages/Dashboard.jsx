import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { TopNav } from "@/components/TopNav";
import { EmptyStateHero } from "@/components/EmptyStateHero";
import { ConnectGmailButton } from "@/components/ConnectGmailButton";
import { LedgerCard } from "@/components/LedgerCard";
import { PaymentsCard } from "@/components/PaymentsCard";
import { TodayCard } from "@/components/TodayCard";
import { SyncStatusBar } from "@/components/SyncStatusBar";
import { ChaseQueueCard } from "@/components/ChaseQueueCard";
import { SeedScanProgress } from "@/components/SeedScanProgress";
import { CurationScreen } from "@/components/CurationScreen";
import { WatchingEmptyState } from "@/components/WatchingEmptyState";
import { InvoiceDetectedBanner } from "@/components/InvoiceDetectedBanner";
import { DueDatePromptBanner } from "@/components/DueDatePromptBanner";
import { FollowUpPromptBanner } from "@/components/FollowUpPromptBanner";
import { ChaseDialog } from "@/components/ChaseDialog";
import { formatMoney } from "@/components/LedgerCard";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useGmailCallbackToast } from "@/hooks/useGmailCallbackToast";
import { useLedger } from "@/hooks/useScan";
import { useReceipts } from "@/hooks/useReceipts";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useLiveDetection } from "@/hooks/useLiveDetection";
import { useWorkspaceRefresh } from "@/hooks/useWorkspaceRefresh";

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
    const { data: receipts, refresh: refreshReceipts } = useReceipts(pastOnboarding);
    const { refreshAll: refreshWorkspace } = useWorkspaceRefresh({
        refreshLedger,
        refreshReceipts,
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

    const hasOpenInvoices = (ledger?.invoices?.length ?? 0) > 0;

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
                    <div className="py-10 md:py-14 space-y-8" data-testid="connected-dashboard">
                        <div className="animate-fade-up">
                            <div className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground mb-3">
                                {pastOnboarding ? "Today" : "Setup"}
                            </div>
                            <h1 className="font-heading font-black text-3xl md:text-4xl tracking-tight text-foreground">
                                {pastOnboarding
                                    ? "Chase every invoice — automatically"
                                    : "Let's find what you're still owed"}
                            </h1>
                            <p className="mt-2 text-base text-muted-foreground">
                                {onboarding?.phase === "scanning"
                                    ? "Scanning sent invoices from the last 90 days…"
                                    : onboarding?.phase === "curating"
                                      ? "You know your last 90 days — pick what's still unpaid."
                                      : pastOnboarding
                                        ? "Approve follow-up drafts with one tap. Nothing sends without you."
                                        : "Forward-tracking from here — not inbox archaeology."}
                            </p>
                        </div>

                        {onboarding?.phase === "scanning" ? (
                            <SeedScanProgress
                                scanPhase={onboarding?.scan_phase}
                                counts={onboarding?.counts}
                            />
                        ) : null}

                        {onboarding?.phase === "curating" ? (
                            candidates === null ? (
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
                                className="rounded-2xl border border-border bg-card p-8 flex items-center gap-3 text-sm text-muted-foreground"
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
                                <SyncStatusBar watching onSynced={handleSyncDetected} />

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
                                />

                                {onboarding?.phase === "watching" && !hasOpenInvoices ? (
                                    <WatchingEmptyState onChanged={refreshAll} />
                                ) : (
                                    <>
                                        <TodayCard onDraftChase={setChaseInvoice} onChanged={refreshAll} />
                                        <ChaseQueueCard onSent={refreshAll} />
                                    </>
                                )}

                                <PaymentsCard
                                    receipts={receipts}
                                    ledger={ledger}
                                    onChanged={refreshAll}
                                />

                                {hasOpenInvoices ? (
                                    <section>
                                        <h2 className="font-heading font-bold text-lg mb-3 text-muted-foreground">All tracked invoices</h2>
                                        <LedgerCard ledger={ledger} onChanged={refreshAll} />
                                    </section>
                                ) : null}
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
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-wrap justify-between items-center gap-3 text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
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
            className="rounded-xl border border-amber-200 bg-amber-50 p-5 flex flex-col sm:flex-row sm:items-center gap-4"
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
                        className="inline-block mt-2 text-[11px] font-mono uppercase tracking-widest text-amber-900 underline underline-offset-2 hover:text-amber-950">
                        Gmail settings
                    </Link>
                </div>
            </div>
            <ConnectGmailButton
                label={revoked ? "Reconnect Gmail" : "Reconnect Gmail"}
                testId="reconnect-gmail-button"
                variant={revoked ? "default" : "secondary"}
            />
        </div>
    );
}
