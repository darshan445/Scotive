import { Check, Lock, Mail } from "lucide-react";
import { ConnectGmailButton } from "@/components/ConnectGmailButton";

/**
 * Simple, focused empty state shown to authenticated users who haven't
 * connected Gmail yet. The full product pitch lives on the public landing
 * page (`/`) — this is deliberately minimal so users just do the one thing
 * that matters: connect Gmail.
 */
export function EmptyStateHero() {
    return (
        <section
            className="pt-8 md:pt-16 pb-16 max-w-2xl mx-auto text-center"
            data-testid="empty-state-hero"
        >
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground mb-6">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                One last step
            </div>

            <h1
                className="font-heading font-black text-3xl sm:text-4xl leading-tight tracking-tight text-foreground"
                data-testid="empty-state-headline"
            >
                Chase every invoice — automatically.
            </h1>

            <p
                className="mt-4 text-base md:text-lg text-muted-foreground leading-relaxed"
                data-testid="empty-state-subhead"
            >
                Scotive watches your Gmail, tracks invoices you send, reads client replies, and drafts the follow-ups. Nothing sends without your approval.
            </p>

            <div className="mt-8 flex flex-col items-center gap-4">
                <ConnectGmailButton />
                <div className="text-xs text-muted-foreground max-w-sm leading-relaxed" data-testid="trust-line">
                    Read + send-with-approval access only ·{" "}
                    <span className="text-foreground font-medium">Your emails never train AI models</span> · Disconnect anytime.
                </div>
            </div>

            <div className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" strokeWidth={2} />
                    Only 2 Gmail permissions
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5" strokeWidth={2} />
                    SOC 2-grade encryption at rest
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5" strokeWidth={2} />
                    Sends from your own address
                </span>
            </div>
        </section>
    );
}
