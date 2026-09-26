"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";
import { SyncStatusBar } from "@/components/SyncStatusBar";
import { WatchingEmptyState } from "@/components/WatchingEmptyState";
import { OnboardingConnections } from "@/components/OnboardingConnections";
import { InvoiceDetectedBanner } from "@/components/InvoiceDetectedBanner";
import { DueDatePromptBanner } from "@/components/DueDatePromptBanner";
import { FollowUpPromptBanner } from "@/components/FollowUpPromptBanner";
import { CadenceIntroModal } from "@/components/CadenceIntroModal";
import { ChaseBoard } from "@/components/ChaseBoard";
import { InvoiceDetailDrawer } from "@/components/InvoiceDetailDrawer";
import { api } from "@/lib/api";
import { formatMoney, formatOpenTotals } from "@/components/LedgerCard";
import {
    DashboardContentSkeleton,
    DashboardSkeleton,
} from "@/components/PageSkeletons";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { useGmailCallbackToast } from "@/hooks/useGmailCallbackToast";
import { useQboConnection } from "@/hooks/useQboConnection";
import { useQboCallbackToast } from "@/hooks/useQboCallbackToast";
import { useLedger } from "@/hooks/useScan";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useLiveDetection } from "@/hooks/useLiveDetection";
import { useWorkspaceRefresh } from "@/hooks/useWorkspaceRefresh";
import { historyLedgerInvoices, outstandingBalance } from "@/lib/ledgerInvoices";
import { autoReminderInvoices, needsYouInvoices, openChaseInvoices, stoppedInvoices, watchingInvoices } from "@/lib/chase";
import { needsReconnect } from "@/lib/connectionStatus";
import { ConnectQboButton } from "@/components/ConnectQboButton";

function GmailIssueBanner({ status }) {
    const revoked = needsReconnect(status?.status);
    const label = status?.provider === "outlook" ? "Outlook" : "Gmail";
    const provider = status?.provider === "outlook" ? "outlook" : "google";
    return (
        <div
            className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex flex-col sm:flex-row sm:items-center gap-3"
            data-testid={revoked ? "connection-panel-revoked" : "connection-panel-send-missing"}>
            <div className="flex items-start gap-3 flex-1 min-w-0">
                <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                    <div className="font-heading font-semibold text-amber-900">
                        {revoked ? `${label} access was revoked` : "Connected — but sending is off"}
                    </div>
                    <div className="text-sm text-amber-800 mt-1">
                        {revoked ? (
                            <>
                                Reconnect to keep chase live.
                                {status.email ? (
                                    <> Access to <span className="font-mono">{status.email}</span> was removed.</>
                                ) : null}
                            </>
                        ) : (
                            <>
                                Threads still match from <span className="font-mono">{status.email}</span>, but send needs permission.
                            </>
                        )}
                    </div>
                    <Link
                        href="/settings"
                        className="inline-flex items-center gap-1 mt-2 text-xs font-semibold text-amber-900 underline underline-offset-2">
                        Mailbox settings <ArrowUpRight className="w-3 h-3" />
                    </Link>
                </div>
            </div>
            <ConnectMailboxButton
                provider={provider}
                label={`Reconnect ${label}`}
                testId="reconnect-gmail-button"
                variant={revoked ? "primary" : "secondary"}
            />
        </div>
    );
}

function QboIssueBanner({ status }) {
    if (!needsReconnect(status?.status)) return null;
    return (
        <div
            className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex flex-col sm:flex-row sm:items-center gap-3"
            data-testid="qbo-dashboard-reauth"
        >
            <div className="flex items-start gap-3 flex-1 min-w-0">
                <AlertTriangle className="w-5 h-5 text-amber-700 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                    <div className="font-heading font-semibold text-amber-900">QuickBooks needs to be reconnected</div>
                    <div className="text-sm text-amber-800 mt-1">
                        Invoice sync is paused until you reconnect
                        {status.company_name ? <> {status.company_name}</> : null}.
                    </div>
                </div>
            </div>
            <ConnectQboButton label="Reconnect QuickBooks" testId="reconnect-qbo-dashboard" />
        </div>
    );
}

export default function DashboardPage() {
    const { status, refresh } = useGmailConnection();
    const { status: qboStatus, refresh: refreshQbo } = useQboConnection();
    const gmailConnected = Boolean(status?.connected);
    const {
        state: onboarding,
        refresh: refreshOnboarding,
    } = useOnboarding({ enabled: true });

    const onboardingReady = onboarding != null;
    const pastOnboarding = onboarding?.phase === "complete" || onboarding?.phase === "watching";
    const showConnections =
        !pastOnboarding &&
        (onboarding?.phase === "connections" || onboarding?.phase == null);
    const bootstrapping = status === null || !onboardingReady;

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
    const [reviewInvoice, setReviewInvoice] = useState(null);
    const [latestDetection, setLatestDetection] = useState(null);
    const [dueDatePrompt, setDueDatePrompt] = useState(null);
    const [followUpPrompt, setFollowUpPrompt] = useState(null);
    const [tab, setTab] = useState("needs_you");
    const [cadenceIntroHidden, setCadenceIntroHidden] = useState(false);

    const invoices = ledger?.invoices || [];
    const needsYouCount = useMemo(() => needsYouInvoices(invoices).length, [invoices]);
    const watchingCount = useMemo(() => watchingInvoices(invoices).length, [invoices]);
    const autoCount = useMemo(() => autoReminderInvoices(invoices).length, [invoices]);
    const stoppedCount = useMemo(() => stoppedInvoices(invoices).length, [invoices]);
    const paidCount = useMemo(() => historyLedgerInvoices(invoices).length, [invoices]);
    const hasOpenInvoices = useMemo(() => openChaseInvoices(invoices).length > 0, [invoices]);
    const outstanding = useMemo(() => {
        const byCur = {};
        for (const i of openChaseInvoices(invoices)) {
            const cur = (i.currency || "USD").toUpperCase();
            byCur[cur] = (byCur[cur] || 0) + outstandingBalance(i);
        }
        return formatOpenTotals(byCur);
    }, [invoices]);

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
        enabled: pastOnboarding && gmailConnected,
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
                await refreshOnboarding();
            }
        }, [refresh, refreshOnboarding]),
    );

    useQboCallbackToast(
        useCallback(async (result) => {
            await refreshQbo();
            if (result === "connected") {
                await refreshOnboarding();
            }
        }, [refreshQbo, refreshOnboarding]),
    );

    useEffect(() => {
        refreshOnboarding();
    }, [status?.connected, qboStatus?.connected, refreshOnboarding]);

    const handleConnectionsChange = useCallback(() => {
        void refresh();
        void refreshQbo();
        void refreshOnboarding();
    }, [refresh, refreshQbo, refreshOnboarding]);

    const handleQboImported = useCallback(() => {
        void refreshQbo();
        void refreshOnboarding();
    }, [refreshQbo, refreshOnboarding]);

    async function handleConnectionsContinue(data) {
        await refreshOnboarding();
        if (data?.next === "dashboard") {
            await refreshAll();
            toast.success("You're set", {
                description: "QuickBooks invoices are on your ledger.",
            });
        }
    }

    const qboIsConnected = Boolean(qboStatus?.connected || onboarding?.qbo_connected);
    const showCadenceIntro =
        pastOnboarding &&
        onboarding?.onboarding_modal_dismissed === false &&
        !cadenceIntroHidden;

    async function dismissCadenceIntro() {
        setCadenceIntroHidden(true);
        try {
            await api.post("/v1/onboarding/dismiss-modal");
            await refreshOnboarding();
        } catch {
            setCadenceIntroHidden(false);
        }
    }

    return (
        <AppShell
            testId="dashboard-root"
            showFooter={false}
            afterMain={(
                <InvoiceDetailDrawer
                    invoiceId={reviewInvoice?._id}
                    preview={reviewInvoice}
                    open={!!reviewInvoice}
                    onClose={() => setReviewInvoice(null)}
                    onChanged={refreshAll}
                />
            )}
        >
            {bootstrapping ? (
                <DashboardSkeleton />
            ) : showConnections ? (
                <div className="py-8 md:py-12" data-testid="onboarding-connections-wrap">
                    <OnboardingConnections
                        gmailConnected={gmailConnected || Boolean(onboarding?.gmail_connected)}
                        qboConnected={qboIsConnected}
                        mailProvider={status?.provider || null}
                        connections={status?.connections || []}
                        qboStatus={qboStatus}
                        onboarding={onboarding}
                        onContinue={handleConnectionsContinue}
                        onConnectionsChange={handleConnectionsChange}
                        onQboImported={handleQboImported}
                    />
                </div>
            ) : (
                <div className="py-6 md:py-8 space-y-5" data-testid="connected-dashboard">
                    {pastOnboarding && (needsReconnect(status?.status) || status?.status === "send_missing") ? (
                        <GmailIssueBanner status={status} />
                    ) : null}
                    {pastOnboarding ? <QboIssueBanner status={qboStatus} /> : null}

                    {pastOnboarding ? (
                        ledger == null ? (
                            <DashboardContentSkeleton />
                        ) : (
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
                                        const inv = invoices.find((i) => i._id === prompt.invoice_id);
                                        if (inv) {
                                            setReviewInvoice(inv);
                                            setFollowUpPrompt(null);
                                        }
                                    }}
                                />

                                {onboarding?.phase === "watching" && !hasOpenInvoices ? (
                                    <WatchingEmptyState onChanged={refreshAll} />
                                ) : null}

                                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                                    <div>
                                        <h1 className="type-display text-2xl md:text-[1.75rem]">Open invoices</h1>
                                        <p className="mt-1 text-sm text-muted-foreground">
                                            <span className="font-medium text-foreground tabular-nums">{outstanding}</span>
                                            {" "}still unpaid · reminders send from your Gmail
                                        </p>
                                    </div>
                                    <SyncStatusBar
                                        watching
                                        openInvoiceCount={openChaseInvoices(invoices).length}
                                        openTotal={outstanding}
                                        onSynced={handleSyncDetected}
                                    />
                                </div>

                                <Tabs value={tab} onValueChange={setTab} className="w-full" data-testid="dashboard-tabs">
                                    <TabsList className="h-auto flex-wrap rounded-lg bg-muted/70 p-1">
                                        <TabsTrigger
                                            value="needs_you"
                                            className="rounded-md px-3.5 py-2 text-sm data-[state=active]:shadow-sm"
                                            data-testid="tab-needs-you"
                                        >
                                            Needs you
                                            {needsYouCount ? (
                                                <span className="ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-600 px-1.5 text-[11px] font-semibold text-white">
                                                    {needsYouCount}
                                                </span>
                                            ) : null}
                                        </TabsTrigger>
                                        <TabsTrigger
                                            value="watching"
                                            className="rounded-md px-3.5 py-2 text-sm data-[state=active]:shadow-sm"
                                            data-testid="tab-watching"
                                        >
                                            Watching
                                            {watchingCount ? (
                                                <span className="ml-1.5 text-[11px] tabular-nums text-muted-foreground">{watchingCount}</span>
                                            ) : null}
                                        </TabsTrigger>
                                        <TabsTrigger
                                            value="auto_reminders"
                                            className="rounded-md px-3.5 py-2 text-sm data-[state=active]:shadow-sm"
                                            data-testid="tab-auto-reminders"
                                        >
                                            Auto reminders
                                            {autoCount ? (
                                                <span className="ml-1.5 text-[11px] tabular-nums text-muted-foreground">{autoCount}</span>
                                            ) : null}
                                        </TabsTrigger>
                                        <TabsTrigger
                                            value="stopped"
                                            className="rounded-md px-3.5 py-2 text-sm data-[state=active]:shadow-sm"
                                            data-testid="tab-stopped"
                                        >
                                            Stopped
                                            <span className="ml-1.5 text-[11px] tabular-nums text-muted-foreground">{stoppedCount}</span>
                                        </TabsTrigger>
                                        <TabsTrigger
                                            value="paid"
                                            className="rounded-md px-3.5 py-2 text-sm data-[state=active]:shadow-sm"
                                            data-testid="tab-paid"
                                        >
                                            Paid
                                            {paidCount ? (
                                                <span className="ml-1.5 text-[11px] tabular-nums text-muted-foreground">{paidCount}</span>
                                            ) : null}
                                        </TabsTrigger>
                                    </TabsList>
                                    <p className="mt-3 text-sm text-muted-foreground max-w-2xl" data-testid="tab-explainer">
                                        {tab === "needs_you"
                                            ? "Replies and Firm drafts. After you act, pick when to check back if they stay quiet."
                                            : tab === "watching"
                                              ? "Dates you set. We'll bring it back to Needs you on that day if they haven't written — or sooner if they reply."
                                              : tab === "auto_reminders"
                                                ? "Silent invoices. Friendly reminders send on their own. A reply stops them. Stop from the menu if you need to turn them off."
                                                : tab === "stopped"
                                                  ? "You turned reminders off. Pick a date when you want Scotive to check back."
                                                  : "Closed in QuickBooks. Chase is over."}
                                    </p>
                                    <TabsContent value="needs_you" className="mt-4">
                                        <ChaseBoard
                                            ledger={ledger}
                                            variant="needs_you"
                                            onChanged={refreshAll}
                                            onReview={setReviewInvoice}
                                        />
                                    </TabsContent>
                                    <TabsContent value="watching" className="mt-4">
                                        <ChaseBoard
                                            ledger={ledger}
                                            variant="watching"
                                            onChanged={refreshAll}
                                            onReview={setReviewInvoice}
                                        />
                                    </TabsContent>
                                    <TabsContent value="auto_reminders" className="mt-4">
                                        <ChaseBoard
                                            ledger={ledger}
                                            variant="auto_reminders"
                                            onChanged={refreshAll}
                                        />
                                    </TabsContent>
                                    <TabsContent value="stopped" className="mt-4">
                                        <ChaseBoard ledger={ledger} variant="stopped" onChanged={refreshAll} />
                                    </TabsContent>
                                    <TabsContent value="paid" className="mt-4">
                                        <ChaseBoard ledger={ledger} variant="paid" onChanged={refreshAll} />
                                    </TabsContent>
                                </Tabs>
                            </>
                        )
                    ) : null}
                    <CadenceIntroModal
                        open={showCadenceIntro}
                        mailboxProvider={status?.provider || onboarding?.mail_provider}
                        onDismiss={dismissCadenceIntro}
                    />
                </div>
            )}
        </AppShell>
    );
}
