"use client";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { SiQuickbooks } from "react-icons/si";
import { toast } from "sonner";
import { ConnectQboButton } from "@/components/ConnectQboButton";
import { Button } from "@/components/ui/button";
import { api, extractError } from "@/lib/api";

/**
 * Optional QuickBooks step after Gmail, before seed (Path B).
 */
export function QboOnboardingStep({ onSkip }) {
    const [busy, setBusy] = useState(false);

    async function handleSkip() {
        setBusy(true);
        try {
            await api.post("/onboarding/qbo-step", { action: "skip" });
            await onSkip?.();
        } catch (e) {
            toast.error(extractError(e));
            setBusy(false);
        }
    }

    return (
        <div
            className="rounded-2xl border border-border bg-card p-8 md:p-10 max-w-xl mx-auto space-y-6"
            data-testid="qbo-onboarding-step"
        >
            <div className="flex justify-center">
                <span className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-muted border border-border">
                    <SiQuickbooks className="w-7 h-7 text-[#2CA01C]" />
                </span>
            </div>
            <div className="text-center space-y-2">
                <div className="eyebrow">Optional</div>
                <h2 className="type-title text-2xl md:text-3xl">Also use QuickBooks?</h2>
                <p className="text-sm text-muted-foreground max-w-md mx-auto leading-relaxed">
                    We&apos;re already scanning the last 90 days of Gmail. Connect QuickBooks too if you
                    invoice there — open invoices import in the background. You can skip and connect later in Settings.
                </p>
            </div>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                <ConnectQboButton
                    label="Connect QuickBooks"
                    testId="onboarding-connect-qbo"
                    variant="primary"
                />
                <Button
                    variant="ghost"
                    onClick={handleSkip}
                    disabled={busy}
                    data-testid="onboarding-skip-qbo"
                >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Skip for now
                </Button>
            </div>
        </div>
    );
}

/**
 * After QBO OAuth: mark step + import unpaid invoices (fast).
 * Conversation match / status re-eval runs in the background — dashboard shows progress.
 */
export async function finishQboOnboardingImport() {
    await api.post("/onboarding/qbo-step", { action: "connected" });
    const { data } = await api.post("/qbo/import");
    return data?.counts || {};
}
