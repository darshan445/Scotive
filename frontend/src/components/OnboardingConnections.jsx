"use client";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Lock } from "lucide-react";
import { FcGoogle } from "react-icons/fc";
import { PiMicrosoftOutlookLogo } from "react-icons/pi";
import { SiQuickbooks } from "react-icons/si";
import { toast } from "sonner";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";
import { ConnectQboButton } from "@/components/ConnectQboButton";
import { ConnectXeroButton } from "@/components/ConnectXeroButton";
import { toastQboImportComplete } from "@/components/QboOnboardingStep";
import { toastXeroImportComplete } from "@/components/XeroOnboardingStep";
import { XeroMark } from "@/components/XeroMark";
import { Button } from "@/components/ui/button";
import { api, extractError, unwrapData, LONG_JOB_TIMEOUT_MS } from "@/lib/api";

function connFor(connections, provider) {
    return (connections || []).find((c) => c.provider === provider && c.connected);
}

function pipelineBusy(pipe) {
    return pipe?.status === "queued" || pipe?.status === "running";
}

function importFields(status, fallbackProgress = null) {
    const progress = status?.import_progress || fallbackProgress || null;
    const lastAt = status?.last_invoice_import_at || null;
    const importStatus = progress?.status || null;
    const imported = Number(progress?.imported || 0);
    const total = Number(progress?.total || 0);
    return { progress, lastAt, status: importStatus, imported, total };
}

function BrandMark({ children }) {
    return (
        <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-background border border-border flex-shrink-0">
            {children}
        </span>
    );
}

function FreshbooksMark() {
    return (
        <svg viewBox="0 2.3 33.4 33.4" className="w-5 h-5" aria-hidden="true">
            <path fill="#fff" d="M9.8 5.9h17.4v25.9H9.8z" />
            <path
                fill="#0075DD"
                d="M14.1 2.3C6.3 2.3 0 8.6 0 16.4v19.3h19.3c7.8 0 14.1-6.3 14.1-14.1V2.3zm11.4 5.9c0 2.6-2.1 4.6-4.6 4.6h-5v4h6.7v4.6h-6.6v9.6h-5.5v-24h5.4v4.3c.2-2.4 2.2-4.3 4.6-4.3h5z"
            />
        </svg>
    );
}

function ComingSoon() {
    return (
        <span className="inline-flex items-center h-8 px-3 rounded-full border border-border bg-muted/50 text-xs font-medium text-muted-foreground">
            Coming soon
        </span>
    );
}

function DisconnectButton({ onClick, busy, testId }) {
    return (
        <Button
            type="button"
            size="sm"
            variant="outline"
            className="rounded-full"
            disabled={busy}
            onClick={onClick}
            data-testid={testId}
        >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Disconnect
        </Button>
    );
}

function ConnectedActions({ onDisconnect, busy, testId }) {
    return (
        <div className="flex items-center gap-2 flex-shrink-0">
            <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700" data-testid={testId}>
                <CheckCircle2 className="w-4 h-4" /> Connected
            </span>
            <DisconnectButton onClick={onDisconnect} busy={busy} testId={`${testId}-disconnect`} />
        </div>
    );
}

function ToolProgressBar({ label, current, total, fetchingLabel, testId }) {
    const knownTotal = total > 0;
    const determinate = knownTotal && current > 0;
    const pct = determinate ? Math.min(100, Math.round((current / total) * 100)) : 0;
    const [smooth, setSmooth] = useState(false);
    const countLabel = determinate
        ? `${current} of ${total}`
        : (fetchingLabel || "Starting…");

    useEffect(() => {
        if (!determinate) {
            setSmooth(false);
            return undefined;
        }
        const id = requestAnimationFrame(() => setSmooth(true));
        return () => cancelAnimationFrame(id);
    }, [determinate]);

    return (
        <div className="pt-3 space-y-1.5" data-testid={testId}>
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>{label}</span>
                <span className="tabular-nums">{countLabel}</span>
            </div>
            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                {determinate ? (
                    <div
                        className={`h-full rounded-full bg-foreground ${smooth ? "transition-[width] duration-300 ease-out" : ""}`}
                        style={{ width: `${pct}%` }}
                    />
                ) : (
                    <div className="h-full w-1/3 rounded-full bg-foreground animate-progress-indeterminate" />
                )}
            </div>
        </div>
    );
}

/**
 * Onboarding: invoicing first (one or more), then mailbox (Gmail and/or Outlook).
 * Email stays locked until invoices are imported from QuickBooks or Xero.
 */
export function OnboardingConnections({
    gmailConnected = false,
    qboConnected = false,
    xeroConnected = false,
    mailProvider = null,
    connections = [],
    qboStatus = null,
    xeroStatus = null,
    onboarding = null,
    onContinue,
    onQboImported,
    onConnectionsChange,
}) {
    const [busy, setBusy] = useState(false);
    const [retrying, setRetrying] = useState(false);
    const [disconnecting, setDisconnecting] = useState(null);
    const [liveQbo, setLiveQbo] = useState(qboStatus);
    const [liveXero, setLiveXero] = useState(xeroStatus);
    const [livePipe, setLivePipe] = useState(onboarding?.qbo_pipeline || null);
    const [kickoffImporting, setKickoffImporting] = useState(false);
    const [kickoffXeroImporting, setKickoffXeroImporting] = useState(false);
    const [kickoffError, setKickoffError] = useState(false);
    const [kickoffXeroError, setKickoffXeroError] = useState(false);
    const [kickoffMatching, setKickoffMatching] = useState(false);
    const importKickoffRef = useRef(false);
    const xeroImportKickoffRef = useRef(false);
    const matchKickoffRef = useRef(false);

    useEffect(() => {
        setLiveQbo(qboStatus);
    }, [qboStatus]);

    useEffect(() => {
        setLiveXero(xeroStatus);
    }, [xeroStatus]);

    const mergedQbo = liveQbo || qboStatus;
    const mergedXero = liveXero || xeroStatus;
    const qboImport = importFields(mergedQbo, onboarding?.qbo_import_progress);
    const xeroImport = importFields(mergedXero, onboarding?.xero_import_progress);
    const qboImportError = qboImport.status === "error" || kickoffError;
    const xeroImportError = xeroImport.status === "error" || kickoffXeroError;
    const qboImportComplete = Boolean(!qboImportError && (qboImport.lastAt || qboImport.status === "complete"));
    const xeroImportComplete = Boolean(!xeroImportError && (xeroImport.lastAt || xeroImport.status === "complete"));
    const booksConnected = qboConnected || xeroConnected;
    const importComplete = (qboConnected && qboImportComplete) || (xeroConnected && xeroImportComplete);
    const qboImporting = Boolean(
        qboConnected && !qboImportComplete && (qboImport.status === "running" || qboImport.status === "queued" || kickoffImporting),
    );
    const xeroImporting = Boolean(
        xeroConnected && !xeroImportComplete && (xeroImport.status === "running" || xeroImport.status === "queued" || kickoffXeroImporting),
    );
    const importing = qboImporting || xeroImporting;
    const importError = (qboConnected && qboImportError && !qboImportComplete) || (xeroConnected && xeroImportError && !xeroImportComplete);
    const emailUnlocked = booksConnected && importComplete && !importing;
    const googleConn = connFor(connections, "google");
    const outlookConn = connFor(connections, "outlook");
    const googleOn = Boolean(googleConn) || (gmailConnected && (mailProvider === "google" || !mailProvider) && !outlookConn);
    const outlookOn = Boolean(outlookConn) || (gmailConnected && mailProvider === "outlook");
    const anyMail = googleOn || outlookOn || gmailConnected;
    const pipe = livePipe || onboarding?.qbo_pipeline || null;
    const pipeBusy = pipelineBusy(pipe);
    const phase = pipe?.phase || "";
    const matchComplete = pipe?.status === "complete";
    const matchFailed = pipe?.status === "error";
    const deciding = Boolean(pipeBusy && phase === "deciding_status");
    const matchingPhase = Boolean(
        kickoffMatching ||
        (anyMail && importComplete && !matchComplete && !matchFailed) ||
        (pipeBusy && !deciding)
    );
    const blocking = matchingPhase || deciding;
    const pipeTotal = Number(pipe?.total || 0);
    const examined = Number(pipe?.examined || 0);
    const statusTotal = Number(pipe?.status_total || 0);
    const statusDone = Number(pipe?.status_done || 0);
    const barCurrent = deciding ? statusDone : examined;
    const barTotal = deciding ? statusTotal : pipeTotal;
    const barLabel = deciding ? "Updating status from conversations" : "Matching conversations";
    const matchBarOnGmail = blocking && googleOn;
    const matchBarOnOutlook = blocking && outlookOn && !googleOn;
    const canContinue = anyMail && booksConnected && importComplete && matchComplete && !blocking;
    const companyName = (mergedQbo?.company_name || "").trim();
    const xeroCompanyName = (mergedXero?.company_name || "").trim();

    const onImportedRef = useRef(onQboImported);
    onImportedRef.current = onQboImported;

    useEffect(() => {
        if (onboarding?.qbo_pipeline) setLivePipe(onboarding.qbo_pipeline);
    }, [onboarding?.qbo_pipeline]);

    useEffect(() => {
        if (!qboConnected || qboImportComplete || qboImportError || importKickoffRef.current) return undefined;
        importKickoffRef.current = true;
        setKickoffImporting(true);
        setKickoffError(false);
        (async () => {
            try {
                const { data } = await api.post("/v1/qbo/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
                toastQboImportComplete(unwrapData(data)?.counts || {});
                const { data: status } = await api.get("/v1/qbo/status");
                setLiveQbo(unwrapData(status));
                onImportedRef.current?.();
            } catch (e) {
                importKickoffRef.current = false;
                setKickoffError(true);
                toast.error(extractError(e));
            } finally {
                setKickoffImporting(false);
            }
        })();
        return undefined;
    }, [qboConnected, qboImportComplete, qboImportError]);

    useEffect(() => {
        if (!xeroConnected || xeroImportComplete || xeroImportError || xeroImportKickoffRef.current) return undefined;
        xeroImportKickoffRef.current = true;
        setKickoffXeroImporting(true);
        setKickoffXeroError(false);
        (async () => {
            try {
                const { data } = await api.post("/v1/xero/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
                toastXeroImportComplete(unwrapData(data)?.counts || {});
                const { data: status } = await api.get("/v1/xero/status");
                setLiveXero(unwrapData(status));
                onImportedRef.current?.();
            } catch (e) {
                xeroImportKickoffRef.current = false;
                setKickoffXeroError(true);
                toast.error(extractError(e));
            } finally {
                setKickoffXeroImporting(false);
            }
        })();
        return undefined;
    }, [xeroConnected, xeroImportComplete, xeroImportError]);

    useEffect(() => {
        if (!anyMail || !importComplete || matchComplete || matchFailed || matchKickoffRef.current) return undefined;
        matchKickoffRef.current = true;
        setKickoffMatching(true);
        (async () => {
            try {
                const { data } = await api.post("/v1/qbo/match-conversations", null, { timeout: LONG_JOB_TIMEOUT_MS });
                const payload = unwrapData(data);
                setLivePipe(payload?.pipeline || { status: "complete", phase: "matching" });
                onImportedRef.current?.();
            } catch (e) {
                setLivePipe({ status: "error", phase: "matching" });
                toast.error(extractError(e));
            } finally {
                setKickoffMatching(false);
            }
        })();
        return undefined;
    }, [anyMail, importComplete, matchComplete, matchFailed]);

    const skipImportNotify = useRef(true);
    useEffect(() => {
        if (skipImportNotify.current) {
            skipImportNotify.current = false;
            return;
        }
        if (importComplete) onImportedRef.current?.();
    }, [importComplete]);

    async function disconnectQbo() {
        if (disconnecting) return;
        setDisconnecting("qbo");
        try {
            await api.post("/v1/qbo/disconnect");
            importKickoffRef.current = false;
            setKickoffImporting(false);
            setKickoffError(false);
            setLiveQbo({ connected: false, status: "disconnected" });
            toast("QuickBooks disconnected");
            onConnectionsChange?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setDisconnecting(null);
        }
    }

    async function disconnectXero() {
        if (disconnecting) return;
        setDisconnecting("xero");
        try {
            await api.post("/v1/xero/disconnect");
            xeroImportKickoffRef.current = false;
            setKickoffXeroImporting(false);
            setKickoffXeroError(false);
            setLiveXero({ connected: false, status: "disconnected" });
            toast("Xero disconnected");
            onConnectionsChange?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setDisconnecting(null);
        }
    }

    async function disconnectMail(provider) {
        if (disconnecting) return;
        setDisconnecting(provider);
        try {
            await api.post("/v1/gmail/disconnect", null, { params: { provider } });
            matchKickoffRef.current = false;
            setKickoffMatching(false);
            setLivePipe(null);
            toast(provider === "outlook" ? "Outlook disconnected" : "Gmail disconnected");
            onConnectionsChange?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setDisconnecting(null);
        }
    }

    async function retryImport() {
        if (retrying) return;
        setRetrying(true);
        setKickoffError(false);
        try {
            const { data } = await api.post("/v1/qbo/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
            toastQboImportComplete(unwrapData(data)?.counts || {});
            const { data: status } = await api.get("/v1/qbo/status");
            setLiveQbo(unwrapData(status));
            onQboImported?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setRetrying(false);
        }
    }

    async function retryXeroImport() {
        if (retrying) return;
        setRetrying(true);
        setKickoffXeroError(false);
        try {
            const { data } = await api.post("/v1/xero/import", null, { timeout: LONG_JOB_TIMEOUT_MS });
            toastXeroImportComplete(unwrapData(data)?.counts || {});
            const { data: status } = await api.get("/v1/xero/status");
            setLiveXero(unwrapData(status));
            onQboImported?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setRetrying(false);
        }
    }

    async function handleNext() {
        if (!canContinue || busy) return;
        setBusy(true);
        try {
            await api.post("/v1/onboarding/qbo-step", { action: "connected" }).catch(() => {});
            const { data } = await api.post("/v1/onboarding/continue");
            await onContinue?.(unwrapData(data));
        } catch (e) {
            toast.error(extractError(e));
            setBusy(false);
        }
    }

    const emailLockHint = !booksConnected
        ? "Connect invoicing first"
        : !importComplete || importing || importError
            ? "Available after invoices are imported"
            : null;

    let nextHint = "Connect invoicing, then Gmail or Outlook";
    if (importing) nextHint = "Importing invoices…";
    else if (importError) nextHint = "Invoice import didn’t finish — try again";
    else if (booksConnected && !importComplete) nextHint = "Invoice import is next — mailbox stays locked until then";
    else if (booksConnected && !anyMail) nextHint = "Connect Gmail or Outlook — one or both";
    else if (matchingPhase) nextHint = "Matching conversations…";
    else if (matchFailed) nextHint = "Couldn’t match conversations — reconnect email to try again";
    else if (deciding) nextHint = "Updating status from conversations…";
    else if (canContinue) nextHint = "Next opens your ledger";

    return (
        <section
            className="pt-4 md:pt-8 pb-16 max-w-xl mx-auto"
            data-testid="onboarding-connections"
        >
            <div className="mb-8">
                <h1 className="type-display text-3xl sm:text-4xl">Connect your tools</h1>
                <p className="type-body mt-3 text-base max-w-md">
                    Invoices from your books. Conversations from your inbox. Connect both — Scotive matches them.
                </p>
            </div>

            <div className="space-y-6">
                <section>
                    <div className="mb-3">
                        <h2 className="type-title text-base">Invoicing</h2>
                        <p className="text-sm text-muted-foreground mt-1">
                            Connect one or more.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-border bg-card divide-y divide-border">
                        <div className="p-4" data-testid="onboarding-qbo-row">
                            <div className="flex items-center gap-3">
                                <BrandMark>
                                    <SiQuickbooks className="w-5 h-5 text-[#2CA01C]" />
                                </BrandMark>
                                <div className="min-w-0 flex-1">
                                    <div className="font-heading font-semibold text-foreground">QuickBooks Online</div>
                                    {qboConnected && companyName ? (
                                        <div className="text-xs text-muted-foreground truncate mt-0.5">{companyName}</div>
                                    ) : null}
                                </div>
                                {qboConnected && qboImporting ? (
                                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                                        <Loader2 className="w-4 h-4 animate-spin" /> Importing
                                    </span>
                                ) : qboConnected && qboImportError ? (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        className="rounded-full"
                                        disabled={retrying}
                                        onClick={retryImport}
                                        data-testid="onboarding-qbo-retry"
                                    >
                                        {retrying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                                        Try again
                                    </Button>
                                ) : qboConnected ? (
                                    <ConnectedActions
                                        onDisconnect={disconnectQbo}
                                        busy={disconnecting === "qbo"}
                                        testId="onboarding-qbo-connected"
                                    />
                                ) : (
                                    <ConnectQboButton
                                        label="Connect"
                                        testId="onboarding-connect-qbo"
                                        compact
                                    />
                                )}
                            </div>
                            {qboImporting ? (
                                <ToolProgressBar
                                    label="Importing invoices"
                                    current={qboImport.imported}
                                    total={qboImport.total}
                                    fetchingLabel="Fetching invoices…"
                                    testId="onboarding-qbo-import-bar"
                                />
                            ) : null}
                            {qboImportError ? (
                                <p className="text-xs text-red-600 mt-3">Couldn’t import invoices. Try again.</p>
                            ) : null}
                        </div>

                        <div className="p-4" data-testid="onboarding-xero-row">
                            <div className="flex items-center gap-3">
                                <BrandMark>
                                    <XeroMark />
                                </BrandMark>
                                <div className="min-w-0 flex-1">
                                    <div className="font-heading font-semibold text-foreground">Xero</div>
                                    {xeroConnected && xeroCompanyName ? (
                                        <div className="text-xs text-muted-foreground truncate mt-0.5">{xeroCompanyName}</div>
                                    ) : null}
                                </div>
                                {xeroConnected && xeroImporting ? (
                                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                                        <Loader2 className="w-4 h-4 animate-spin" /> Importing
                                    </span>
                                ) : xeroConnected && xeroImportError ? (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        className="rounded-full"
                                        disabled={retrying}
                                        onClick={retryXeroImport}
                                        data-testid="onboarding-xero-retry"
                                    >
                                        {retrying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                                        Try again
                                    </Button>
                                ) : xeroConnected ? (
                                    <ConnectedActions
                                        onDisconnect={disconnectXero}
                                        busy={disconnecting === "xero"}
                                        testId="onboarding-xero-connected"
                                    />
                                ) : (
                                    <ConnectXeroButton
                                        label="Connect"
                                        testId="onboarding-connect-xero"
                                        compact
                                    />
                                )}
                            </div>
                            {xeroImporting ? (
                                <ToolProgressBar
                                    label="Importing invoices"
                                    current={xeroImport.imported}
                                    total={xeroImport.total}
                                    fetchingLabel="Fetching invoices…"
                                    testId="onboarding-xero-import-bar"
                                />
                            ) : null}
                            {xeroImportError ? (
                                <p className="text-xs text-red-600 mt-3">Couldn’t import invoices. Try again.</p>
                            ) : null}
                        </div>

                        <div className="p-4 flex items-center gap-3" data-testid="onboarding-freshbooks-row">
                            <BrandMark>
                                <FreshbooksMark />
                            </BrandMark>
                            <div className="min-w-0 flex-1">
                                <div className="font-heading font-semibold text-foreground">FreshBooks</div>
                            </div>
                            <ComingSoon />
                        </div>
                    </div>
                </section>

                <section
                    className={emailUnlocked ? "" : "opacity-60"}
                    data-testid="onboarding-email-section"
                    aria-disabled={!emailUnlocked}
                >
                    <div className="mb-3">
                        <h2 className="type-title text-base">Email</h2>
                        <p className="text-sm text-muted-foreground mt-1">
                            {emailUnlocked
                                ? "Connect Gmail, Outlook, or both."
                                : !booksConnected
                                    ? "Connect invoicing first."
                                    : "Unlocks after invoices are imported."}
                        </p>
                    </div>
                    <div
                        className="rounded-2xl border border-border bg-card divide-y divide-border"
                        data-testid="onboarding-email-row"
                    >
                        <div className="p-4" data-testid="onboarding-gmail-row">
                            <div className="flex items-center gap-3">
                                <BrandMark>
                                    <FcGoogle className="w-5 h-5" />
                                </BrandMark>
                                <div className="min-w-0 flex-1">
                                    <div className="font-heading font-semibold text-foreground">Gmail</div>
                                    {googleOn ? (
                                        <div className="text-xs text-emerald-700 truncate mt-0.5">
                                            {googleConn?.email || "Connected"}
                                        </div>
                                    ) : null}
                                </div>
                                {googleOn ? (
                                    <ConnectedActions
                                        onDisconnect={() => disconnectMail("google")}
                                        busy={disconnecting === "google"}
                                        testId="onboarding-gmail-connected"
                                    />
                                ) : (
                                    <ConnectMailboxButton
                                        provider="google"
                                        label="Connect"
                                        testId="onboarding-connect-gmail"
                                        compact
                                        disabled={!emailUnlocked}
                                        disabledTitle={emailLockHint}
                                    />
                                )}
                            </div>
                            {matchBarOnGmail ? (
                                <ToolProgressBar
                                    label={barLabel}
                                    current={barCurrent}
                                    total={barTotal}
                                    fetchingLabel="Starting…"
                                    testId="onboarding-match-bar"
                                />
                            ) : null}
                        </div>

                        <div className="p-4" data-testid="onboarding-outlook-row">
                            <div className="flex items-center gap-3">
                                <BrandMark>
                                    <PiMicrosoftOutlookLogo className="w-5 h-5 text-[#0078D4]" />
                                </BrandMark>
                                <div className="min-w-0 flex-1">
                                    <div className="font-heading font-semibold text-foreground">Outlook</div>
                                    {outlookOn ? (
                                        <div className="text-xs text-emerald-700 truncate mt-0.5">
                                            {outlookConn?.email || "Connected"}
                                        </div>
                                    ) : null}
                                </div>
                                {outlookOn ? (
                                    <ConnectedActions
                                        onDisconnect={() => disconnectMail("outlook")}
                                        busy={disconnecting === "outlook"}
                                        testId="onboarding-outlook-connected"
                                    />
                                ) : (
                                    <ConnectMailboxButton
                                        provider="outlook"
                                        label="Connect"
                                        testId="onboarding-connect-outlook"
                                        compact
                                        disabled={!emailUnlocked}
                                        disabledTitle={emailLockHint}
                                    />
                                )}
                            </div>
                            {matchBarOnOutlook ? (
                                <ToolProgressBar
                                    label={barLabel}
                                    current={barCurrent}
                                    total={barTotal}
                                    fetchingLabel="Starting…"
                                    testId="onboarding-match-bar"
                                />
                            ) : null}
                        </div>
                    </div>
                </section>
            </div>

            <div className="mt-10 flex flex-col items-center gap-3">
                <Button
                    size="lg"
                    className="min-w-[200px]"
                    disabled={!canContinue || busy}
                    onClick={handleNext}
                    data-testid="onboarding-next"
                >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Next
                </Button>
                <p className="text-xs text-muted-foreground text-center">{nextHint}</p>
                <div className="text-xs text-muted-foreground inline-flex items-center gap-1.5 mt-1">
                    <Lock className="w-3.5 h-3.5" />
                    Nothing sends without your approval
                </div>
            </div>
        </section>
    );
}
