import { Check, Lock, Mail } from "lucide-react";
import { ConnectMailboxButton } from "@/components/ConnectGmailButton";

/**
 * Focused empty state for authenticated users who haven't connected a mailbox yet.
 */
export function EmptyStateHero() {
    return (
        <section
            className="pt-8 md:pt-16 pb-16 max-w-2xl mx-auto text-center"
            data-testid="empty-state-hero"
        >
            <div className="flex justify-center mb-6">
                <img src="/scotive-mark.png" alt="" width={48} height={48} className="w-12 h-12" />
            </div>

            <div className="pill mb-6 mx-auto w-fit">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                One last step
            </div>

            <h1
                className="type-display text-3xl sm:text-4xl"
                data-testid="empty-state-headline"
            >
                Connect Gmail or Outlook
            </h1>

            <p
                className="type-body mt-4 text-base md:text-lg"
                data-testid="empty-state-subhead"
            >
                You already invoiced them. Scotive matches the thread, sends Friendly reminders
                you approve, and pauses the moment they reply. Firm still a click.
            </p>

            <div className="mt-8 flex flex-col items-center gap-4">
                <div className="flex flex-col sm:flex-row flex-wrap items-center justify-center gap-3">
                    <ConnectMailboxButton provider="google" />
                    <ConnectMailboxButton provider="outlook" variant="secondary" />
                </div>
                <p className="text-xs text-muted-foreground max-w-sm">
                    Connect one or both — Scotive works across every linked mailbox.
                </p>
                <div className="text-xs text-muted-foreground max-w-sm leading-relaxed" data-testid="trust-line">
                    Read + send-with-approval only ·{" "}
                    <span className="text-foreground font-medium">Not used to train Scotive&apos;s models</span> · Disconnect anytime.
                </div>
            </div>

            <div className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" strokeWidth={2} />
                    Tokens encrypted at rest
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5" strokeWidth={2} />
                    You approve Firm/Final
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5" strokeWidth={2} />
                    Sends from your own address
                </span>
            </div>
        </section>
    );
}
