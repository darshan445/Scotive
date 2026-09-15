"use client";
import { useState } from "react";
import { CheckCircle2, Loader2, Lock } from "lucide-react";
import { FcGoogle } from "react-icons/fc";
import { PiMicrosoftOutlookLogo } from "react-icons/pi";
import { SiQuickbooks } from "react-icons/si";
import { toast } from "sonner";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";
import { ConnectQboButton } from "@/components/ConnectQboButton";
import { Button } from "@/components/ui/button";
import { api, extractError } from "@/lib/api";
import { finishQboOnboardingImport } from "@/components/QboOnboardingStep";

function connFor(connections, provider) {
    return (connections || []).find((c) => c.provider === provider && c.connected);
}

/**
 * Onboarding: email (Gmail and/or Outlook) + optional QuickBooks.
 * At least one mailbox required; both allowed.
 */
export function OnboardingConnections({
    gmailConnected = false,
    qboConnected = false,
    mailProvider = null,
    connections = [],
    onContinue,
    onQboImported,
}) {
    const [busy, setBusy] = useState(false);
    const googleConn = connFor(connections, "google");
    const outlookConn = connFor(connections, "outlook");
    const googleOn = Boolean(googleConn) || (gmailConnected && (mailProvider === "google" || !mailProvider) && !outlookConn);
    const outlookOn = Boolean(outlookConn) || (gmailConnected && mailProvider === "outlook");
    const anyMail = googleOn || outlookOn || gmailConnected;

    async function handleNext() {
        if (!anyMail || busy) return;
        setBusy(true);
        try {
            if (qboConnected) {
                try {
                    await finishQboOnboardingImport();
                    onQboImported?.();
                } catch {
                    await api.post("/onboarding/qbo-step", { action: "connected" }).catch(() => {});
                }
            }
            const { data } = await api.post("/onboarding/continue");
            await onContinue?.(data);
        } catch (e) {
            toast.error(extractError(e));
            setBusy(false);
        }
    }

    return (
        <section
            className="pt-8 md:pt-12 pb-16 max-w-2xl mx-auto"
            data-testid="onboarding-connections"
        >
            <div className="text-center mb-10">
                <div className="flex justify-center mb-6">
                    <img src="/scotive-mark.png" alt="" width={48} height={48} className="w-12 h-12" />
                </div>
                <div className="pill mb-6 mx-auto w-fit">Setup</div>
                <h1 className="type-display text-3xl sm:text-4xl">Connect your tools</h1>
                <p className="type-body mt-4 text-base md:text-lg max-w-lg mx-auto">
                    Connect Gmail, Outlook, or both — Scotive tracks invoices from every linked mailbox.
                    QuickBooks is optional.
                </p>
            </div>

            <div className="space-y-4">
                <div
                    className="rounded-2xl border border-border bg-card p-5 space-y-4"
                    data-testid="onboarding-email-row"
                >
                    <div>
                        <div className="font-heading font-semibold text-foreground">Email</div>
                        <div className="text-sm text-muted-foreground mt-0.5">
                            Required · connect at least one · both is fine if you use both
                        </div>
                    </div>

                    <div className="flex flex-col gap-3">
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                                <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-muted border border-border flex-shrink-0">
                                    <FcGoogle className="w-5 h-5" />
                                </span>
                                <div className="min-w-0">
                                    <div className="text-sm font-medium">Gmail</div>
                                    {googleOn ? (
                                        <div className="text-xs text-emerald-700 truncate">
                                            {googleConn?.email || "Connected"}
                                        </div>
                                    ) : null}
                                </div>
                            </div>
                            {googleOn ? (
                                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700" data-testid="onboarding-gmail-connected">
                                    <CheckCircle2 className="w-4 h-4" /> Connected
                                </span>
                            ) : (
                                <ConnectMailboxButton provider="google" label="Connect Gmail" testId="onboarding-connect-gmail" />
                            )}
                        </div>

                        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                                <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-muted border border-border flex-shrink-0">
                                    <PiMicrosoftOutlookLogo className="w-5 h-5 text-[#0078D4]" />
                                </span>
                                <div className="min-w-0">
                                    <div className="text-sm font-medium">Outlook</div>
                                    {outlookOn ? (
                                        <div className="text-xs text-emerald-700 truncate">
                                            {outlookConn?.email || "Connected"}
                                        </div>
                                    ) : null}
                                </div>
                            </div>
                            {outlookOn ? (
                                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700" data-testid="onboarding-outlook-connected">
                                    <CheckCircle2 className="w-4 h-4" /> Connected
                                </span>
                            ) : (
                                <ConnectMailboxButton
                                    provider="outlook"
                                    label="Connect Outlook"
                                    testId="onboarding-connect-outlook"
                                    variant="secondary"
                                />
                            )}
                        </div>
                    </div>
                </div>

                <div
                    className="rounded-2xl border border-border bg-card p-5 flex flex-col sm:flex-row sm:items-center gap-4"
                    data-testid="onboarding-qbo-row"
                >
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                        <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-muted border border-border flex-shrink-0">
                            <SiQuickbooks className="w-5 h-5 text-[#2CA01C]" />
                        </span>
                        <div className="min-w-0">
                            <div className="font-heading font-semibold text-foreground">QuickBooks Online</div>
                            <div className="text-sm text-muted-foreground mt-0.5">
                                Optional · import open unpaid invoices
                            </div>
                        </div>
                    </div>
                    {qboConnected ? (
                        <span
                            className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700"
                            data-testid="onboarding-qbo-connected"
                        >
                            <CheckCircle2 className="w-4 h-4" /> Connected
                        </span>
                    ) : (
                        <ConnectQboButton
                            label="Connect QuickBooks"
                            testId="onboarding-connect-qbo"
                            variant="secondary"
                        />
                    )}
                </div>
            </div>

            <div className="mt-10 flex flex-col items-center gap-3">
                <Button
                    size="lg"
                    className="min-w-[200px]"
                    disabled={!anyMail || busy}
                    onClick={handleNext}
                    data-testid="onboarding-next"
                >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Next
                </Button>
                {!anyMail ? (
                    <p className="text-xs text-muted-foreground">Connect Gmail or Outlook to continue</p>
                ) : qboConnected ? (
                    <p className="text-xs text-muted-foreground">
                        Next opens your dashboard with QuickBooks invoices tracked
                    </p>
                ) : (
                    <p className="text-xs text-muted-foreground">
                        Next reviews invoices found in your mailbox
                    </p>
                )}
                <div className="text-xs text-muted-foreground inline-flex items-center gap-1.5 mt-2">
                    <Lock className="w-3.5 h-3.5" />
                    Tokens encrypted · nothing sends without your approval
                </div>
            </div>
        </section>
    );
}
