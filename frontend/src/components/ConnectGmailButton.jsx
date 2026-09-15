"use client";
import { useState } from "react";
import { FcGoogle } from "react-icons/fc";
import { PiMicrosoftOutlookLogo } from "react-icons/pi";
import { ArrowRight, Loader2 } from "lucide-react";
import { useGmailConnection } from "@/hooks/useGmailConnection";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

const COPY = {
    google: {
        labelDefault: "Connect Gmail",
        title: "Connect Gmail securely",
        body:
            "We use Unipile, our email partner, to securely connect your Gmail to Scotive — without exposing sensitive details like your Google password.",
        hint: "Google may show Unipile on the next screen. That's normal. After you connect, we only use your mailbox to track invoices and send follow-ups you approve.",
        continue: "Continue to Google",
        opening: "Opening Google…",
        testPrefix: "gmail",
    },
    outlook: {
        labelDefault: "Connect Outlook",
        title: "Connect Outlook securely",
        body:
            "We use Unipile, our email partner, to securely connect your Outlook / Microsoft 365 mailbox to Scotive — without exposing sensitive details like your Microsoft password.",
        hint: "Microsoft may show Unipile on the next screen. That's normal. After you connect, we only use your mailbox to track invoices and send follow-ups you approve.",
        continue: "Continue to Microsoft",
        opening: "Opening Microsoft…",
        testPrefix: "outlook",
    },
};

/**
 * Connect Gmail or Outlook via Unipile. One mailbox per account.
 * @param {"google"|"outlook"} provider
 */
export function ConnectMailboxButton({
    provider = "google",
    testId,
    label,
    variant = "primary",
}) {
    const key = provider === "outlook" ? "outlook" : "google";
    const copy = COPY[key];
    const { startConnect } = useGmailConnection();
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);

    const base =
        "group relative inline-flex items-center gap-3 rounded-full pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-sm active:scale-[0.98]";
    const styles =
        variant === "primary"
            ? "bg-foreground text-background hover:bg-foreground/90 hover:pr-7"
            : "bg-card text-foreground border border-border hover:border-foreground/40 hover:pr-7";

    async function handleContinue() {
        if (busy) return;
        setBusy(true);
        try {
            await startConnect(key);
        } finally {
            setBusy(false);
        }
    }

    const Icon = key === "outlook" ? PiMicrosoftOutlookLogo : FcGoogle;
    const iconClass = key === "outlook" ? "w-5 h-5 text-[#0078D4]" : "w-5 h-5";

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                className={`${base} ${styles}`}
                data-testid={testId || `connect-${copy.testPrefix}-button`}
            >
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-background border border-border">
                    <Icon className={iconClass} />
                </span>
                {label || copy.labelDefault}
                <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
            </button>

            <Dialog open={open} onOpenChange={(o) => { if (!busy) setOpen(o); }}>
                <DialogContent
                    className="sm:max-w-md"
                    data-testid={`${copy.testPrefix}-connect-confirm-dialog`}
                >
                    <DialogHeader>
                        <DialogTitle>{copy.title}</DialogTitle>
                        <DialogDescription className="text-left pt-1">
                            <span className="block text-sm text-muted-foreground leading-relaxed">
                                {copy.body.split("Unipile").map((part, i, arr) =>
                                    i < arr.length - 1 ? (
                                        <span key={i}>
                                            {part}
                                            <span className="text-foreground font-medium">Unipile</span>
                                        </span>
                                    ) : (
                                        <span key={i}>{part}</span>
                                    )
                                )}
                            </span>
                        </DialogDescription>
                    </DialogHeader>

                    <p className="text-sm text-muted-foreground leading-relaxed">
                        {copy.hint}
                    </p>

                    <DialogFooter className="gap-2 sm:gap-2">
                        <Button
                            type="button"
                            variant="ghost"
                            disabled={busy}
                            onClick={() => setOpen(false)}
                            data-testid={`${copy.testPrefix}-connect-cancel`}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            disabled={busy}
                            onClick={handleContinue}
                            data-testid={`${copy.testPrefix}-connect-continue`}
                        >
                            {busy ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                    {copy.opening}
                                </>
                            ) : (
                                copy.continue
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

/** @deprecated Prefer ConnectMailboxButton provider="google" */
export function ConnectGmailButton(props) {
    return <ConnectMailboxButton provider="google" {...props} />;
}

export function ConnectOutlookButton(props) {
    return <ConnectMailboxButton provider="outlook" {...props} />;
}
