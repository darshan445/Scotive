"use client";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Lock } from "lucide-react";
import { FcGoogle } from "react-icons/fc";
import { PiMicrosoftOutlookLogo } from "react-icons/pi";
import { SiQuickbooks } from "react-icons/si";
import { toast } from "sonner";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";
import { ConnectQboButton } from "@/components/ConnectQboButton";
import { toastQboImportComplete } from "@/components/QboOnboardingStep";
import { Button } from "@/components/ui/button";
import { api, extractError } from "@/lib/api";

const POLL_MS = 400;

function connFor(connections, provider) {
    return (connections || []).find((c) => c.provider === provider && c.connected);
}

function pipelineBusy(pipe) {
    return pipe?.status === "queued" || pipe?.status === "running";
}

function importFields(qboStatus, onboarding) {
    const progress = qboStatus?.import_progress || onboarding?.qbo_import_progress || null;
    const lastAt = qboStatus?.last_invoice_import_at || onboarding?.last_invoice_import_at || null;
    const status = progress?.status || null;
    const imported = Number(progress?.imported || 0);
    const total = Number(progress?.total || 0);
    return { progress, lastAt, status, imported, total };
}

function BrandMark({ children }) {
    return (
        <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-background border border-border flex-shrink-0">
            {children}
        </span>
    );
}

function XeroMark() {
    return (
        <svg viewBox="10 16 28.1 27.9" className="w-5 h-5" aria-hidden="true">
            <path
                fill="#13B5EA"
                d="M27.15 29.944L38.062 19.03c.334-.334.557-.9.557-1.336a2 2 0 0 0-2.004-2.004c-.557 0-1.002.223-1.448.557L24.254 27.16 13.34 16.247c-.334-.334-.9-.557-1.336-.557A2 2 0 0 0 10 17.694c0 .557.223 1.002.557 1.448L21.47 30.056 10.557 40.97c-.445.334-.557.9-.557 1.448a2 2 0 0 0 2.004 2.004c.557 0 1.002-.223 1.336-.557L24.254 32.95l10.913 10.913c.445.445.9.557 1.448.557a2 2 0 0 0 2.004-2.004c0-.557-.223-1.002-.557-1.336z"
            />
        </svg>
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
 * Email stays locked until QuickBooks invoices are imported.
 */
export function OnboardingConnections({
    gmailConnected = false,
    qboConnected = false,
    mailProvider = null,
    connections = [],
    qboStatus = null,
    onboarding = null,
    onContinue,
    onQboImported,
    onConnectionsChange,
}) {
    const [busy, setBusy] = useState(false);
    const [retrying, setRetrying] = useState(false);
    const [disconnecting, setDisconnecting] = useState(null);
    const [liveQbo, setLiveQbo] = useState(qboStatus);
    const [livePipe, setLivePipe] = useState(onboarding?.qbo_pipeline || null);

    useEffect(() => {
        setLiveQbo(qboStatus);
    }, [qboStatus]);

    const merged = liveQbo || qboStatus;
    const { lastAt, status: importStatus, imported, total } = importFields(merged, onboarding);
    const importError = importStatus === "error";
    const importing = Boolean(
        qboConnected && (
            importStatus === "running"
            || (!lastAt && importStatus !== "complete" && importStatus !== "error")
        ),
    );
    const importComplete = Boolean(!importing && !importError && (lastAt || importStatus === "complete"));
    const emailUnlocked = qboConnected && importComplete && !importing;
    const googleConn = connFor(connections, "google");
    const outlookConn = connFor(connections, "outlook");
    const googleOn = Boolean(googleConn) || (gmailConnected && (mailProvider === "google" || !mailProvider) && !outlookConn);
    const outlookOn = Boolean(outlookConn) || (gmailConnected && mailProvider === "outlook");
    const anyMail = googleOn || outlookOn || gmailConnected;
    const pipe = livePipe || onboarding?.qbo_pipeline || null;
    const pipeBusy = pipelineBusy(pipe);
    const phase = pipe?.phase || "";
    const jobDone = pipe?.status === "complete" || pipe?.status === "error";
    const deciding = Boolean(pipeBusy && phase === "deciding_status");
    const jobPending = Boolean(anyMail && importComplete && !pipeBusy && !jobDone);
    const matchingPhase = Boolean(jobPending || (pipeBusy && !deciding));
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
    const canContinue = anyMail && qboConnected && importComplete && jobDone && !blocking;
    const companyName = (merged?.company_name || "").trim();

    useEffect(() => {
        if (onboarding?.qbo_pipeline) setLivePipe(onboarding.qbo_pipeline);
    }, [onboarding?.qbo_pipeline]);

    useEffect(() => {
        if (!qboConnected || importComplete || importError) return undefined;
        let cancelled = false;
        async function tick() {
            try {
                const { data } = await api.get("/qbo/status");
                if (!cancelled) setLiveQbo(data);
            } catch {
                /* keep last snapshot */
            }
        }
        tick();
        const id = setInterval(tick, POLL_MS);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [qboConnected, importComplete, importError]);

    useEffect(() => {
        if (!anyMail || !importComplete || jobDone) return undefined;
        let cancelled = false;
        async function tick() {
            try {
                const { data } = await api.get("/qbo/pipeline-status");
                if (!cancelled && data?.pipeline) setLivePipe(data.pipeline);
            } catch {
                /* keep last snapshot */
            }
        }
        tick();
        const id = setInterval(tick, POLL_MS);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [anyMail, importComplete, jobDone]);

    useEffect(() => {
        if (!anyMail || !importComplete) return undefined;
        if (pipeBusy || jobDone) return undefined;
        let cancelled = false;
        (async () => {
            try {
                await api.post("/qbo/match-conversations");
                const { data } = await api.get("/qbo/pipeline-status");
                if (!cancelled && data?.pipeline) setLivePipe(data.pipeline);
            } catch {
                /* enqueue is best-effort; poll will pick it up */
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [anyMail, importComplete, pipeBusy, jobDone]);

    const onImportedRef = useRef(onQboImported);
    onImportedRef.current = onQboImported;
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
            await api.post("/qbo/disconnect");
            setLiveQbo({ connected: false, status: "disconnected" });
            toast("QuickBooks disconnected");
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
            await api.post("/gmail/disconnect", null, { params: { provider } });
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
        try {
            const { data } = await api.post("/qbo/import");
            toastQboImportComplete(data?.counts || {});
            const { data: status } = await api.get("/qbo/status");
            setLiveQbo(status);
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
            await api.post("/onboarding/qbo-step", { action: "connected" }).catch(() => {});
            const { data } = await api.post("/onboarding/continue");
            await onContinue?.(data);
        } catch (e) {
            toast.error(extractError(e));
            setBusy(false);
        }
    }

    const emailLockHint = !qboConnected
        ? "Connect invoicing first"
        : importing
            ? "Available after invoices are imported"
            : importError
                ? "Available after invoices are imported"
                : null;

    let nextHint = "Connect invoicing, then Gmail or Outlook";
    if (importing) nextHint = "Importing invoices…";
    else if (importError) nextHint = "Invoice import didn’t finish — try again";
    else if (qboConnected && !anyMail) nextHint = "Connect Gmail or Outlook — one or both";
    else if (matchingPhase) nextHint = "Matching conversations…";
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
                                {qboConnected && importComplete ? (
                                    <ConnectedActions
                                        onDisconnect={disconnectQbo}
                                        busy={disconnecting === "qbo"}
                                        testId="onboarding-qbo-connected"
                                    />
                                ) : qboConnected && importing ? (
                                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                                        <Loader2 className="w-4 h-4 animate-spin" /> Importing
                                    </span>
                                ) : qboConnected && importError ? (
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
                                ) : (
                                    <ConnectQboButton
                                        label="Connect"
                                        testId="onboarding-connect-qbo"
                                        compact
                                    />
                                )}
                            </div>
                            {importing ? (
                                <ToolProgressBar
                                    label="Importing invoices"
                                    current={imported}
                                    total={total}
                                    fetchingLabel="Fetching invoices…"
                                    testId="onboarding-qbo-import-bar"
                                />
                            ) : null}
                            {importError ? (
                                <p className="text-xs text-red-600 mt-3">Couldn’t import invoices. Try again.</p>
                            ) : null}
                        </div>

                        <div className="p-4 flex items-center gap-3" data-testid="onboarding-xero-row">
                            <BrandMark>
                                <XeroMark />
                            </BrandMark>
                            <div className="min-w-0 flex-1">
                                <div className="font-heading font-semibold text-foreground">Xero</div>
                            </div>
                            <ComingSoon />
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
                                : !qboConnected
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
