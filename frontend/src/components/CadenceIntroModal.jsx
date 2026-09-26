"use client";
import Link from "next/link";
import { Mail, MousePointerClick, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

const AUTO_STEPS = [
    { when: "3 days before due date", what: "Gentle heads-up" },
    { when: "On the due date", what: "Due date check-in" },
    { when: "7 days overdue", what: "Friendly reminder" },
];

function mailboxLabel(provider) {
    return provider === "outlook" ? "Outlook" : "Gmail";
}

export function CadenceIntroModal({ open, mailboxProvider, onDismiss }) {
    const inbox = mailboxLabel(mailboxProvider);

    return (
        <Dialog
            open={open}
            onOpenChange={(next) => {
                if (!next) onDismiss?.();
            }}
        >
            <DialogContent
                className="max-w-[520px] gap-0 overflow-hidden p-0 sm:rounded-xl"
                data-testid="cadence-intro-modal"
            >
                <DialogHeader className="space-y-2 border-b border-border px-6 pb-4 pt-6 pr-12 text-left">
                    <DialogTitle className="font-heading text-xl tracking-tight">
                        How Scotive works
                    </DialogTitle>
                    <DialogDescription className="text-sm leading-relaxed">
                        We’ve set up standard, respectful follow-up rules so your clients are never spammed.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 px-6 py-5">
                    <section className="rounded-xl border border-sky-200/80 bg-sky-50/60 p-4">
                        <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-sky-800">
                            <Mail className="h-3.5 w-3.5" />
                            Sent automatically
                            <span className="font-normal normal-case tracking-normal text-sky-700/80">
                                from your {inbox}
                            </span>
                        </div>
                        <ul className="space-y-2.5">
                            {AUTO_STEPS.map((step) => (
                                <li key={step.when} className="flex items-baseline justify-between gap-4 text-sm">
                                    <span className="text-muted-foreground">{step.when}</span>
                                    <span className="shrink-0 text-right font-medium text-foreground">{step.what}</span>
                                </li>
                            ))}
                        </ul>
                    </section>

                    <section className="rounded-xl border border-violet-200/80 bg-violet-50/50 p-4">
                        <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-violet-800">
                            <MousePointerClick className="h-3.5 w-3.5" />
                            Requires your approval
                            <span className="font-normal normal-case tracking-normal text-violet-700/80">
                                never sends alone
                            </span>
                        </div>
                        <div className="flex items-baseline justify-between gap-4 text-sm">
                            <span className="text-muted-foreground">After the last Friendly</span>
                            <span className="max-w-[220px] shrink-0 text-right font-medium text-foreground">
                                Needs you — you write and send
                            </span>
                        </div>
                    </section>

                    <div className="flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50/70 px-3.5 py-3">
                        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                        <p className="text-sm leading-relaxed text-emerald-950">
                            <span className="font-semibold">Core safety rule.</span>{" "}
                            Any client reply pauses reminders instantly.
                        </p>
                    </div>
                </div>

                <DialogFooter className="items-center gap-3 border-t border-border bg-muted/30 px-6 py-4 sm:justify-between">
                    <p className="text-xs leading-relaxed text-muted-foreground sm:max-w-[280px]">
                        Adjust this schedule or the templates anytime in{" "}
                        <Link href="/settings" className="font-medium text-foreground underline underline-offset-2" onClick={() => onDismiss?.()}>
                            Settings
                        </Link>
                        .
                    </p>
                    <Button
                        className="w-full sm:w-auto"
                        onClick={() => onDismiss?.()}
                        data-testid="cadence-intro-dismiss"
                    >
                        Got it, thanks
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
