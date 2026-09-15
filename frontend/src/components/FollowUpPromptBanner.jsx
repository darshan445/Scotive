import { useState } from "react";
import { MessageSquare, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { formatMoney } from "@/components/LedgerCard";
import { Button } from "@/components/ui/button";

const STEP_LABEL_UI = {
    pre_due_nudge: "Pre-due nudge",
    due_reminder: "Due-date reminder",
    firm_followup: "Firm follow-up",
    final_notice: "Final notice",
    promise_broken: "Broken promise",
};

export function FollowUpPromptBanner({ prompt, onDismiss, onChanged, onReview }) {
    const [busy, setBusy] = useState(false);
    if (!prompt) return null;

    const name = prompt.counterparty_name || prompt.counterparty_email || "Client";
    const step = STEP_LABEL_UI[prompt.step_label] || prompt.step_label || "follow-up";

    async function skip() {
        setBusy(true);
        try {
            if (prompt.draft_id) {
                await api.post(`/chase-drafts/${prompt.draft_id}/dismiss`);
            } else {
                await api.post("/sync/followup-prompts/ack", {
                    invoice_ids: [prompt.invoice_id],
                });
            }
            onDismiss?.();
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    async function stopChasing() {
        setBusy(true);
        try {
            await api.post(`/invoices/${prompt.invoice_id}/action`, { action: "pause" });
            toast.success("Chasing paused for this invoice");
            onDismiss?.();
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div
            className="rounded-xl border border-violet-300 bg-violet-50 px-4 py-3 flex flex-col gap-3 animate-fade-up"
            data-testid="followup-prompt-banner"
            role="status">
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-violet-100 text-violet-800 flex-shrink-0">
                        <MessageSquare className="w-4 h-4" />
                    </span>
                    <div className="min-w-0">
                        <div className="text-sm font-semibold text-violet-950">
                            No reply from {name} yet — send this follow-up?
                        </div>
                        <div className="text-sm text-violet-900">
                            <span className="font-mono tabular-nums">
                                {formatMoney(prompt.amount, prompt.currency || "USD")}
                            </span>
                            <span className="text-violet-800/80"> · {step} draft ready</span>
                        </div>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={skip}
                    disabled={busy}
                    className="inline-flex items-center gap-1 text-sm font-medium text-violet-800 hover:text-violet-950 flex-shrink-0"
                    data-testid="followup-prompt-dismiss">
                    <X className="w-3.5 h-3.5" />
                </button>
            </div>
            <div className="flex flex-wrap items-center gap-2 pl-12">
                <Button size="sm" onClick={() => onReview?.(prompt)} disabled={busy} data-testid="followup-prompt-review">
                    Review &amp; send
                </Button>
                <Button size="sm" variant="ghost" onClick={skip} disabled={busy} data-testid="followup-prompt-skip">
                    Skip
                </Button>
                <Button size="sm" variant="outline" onClick={stopChasing} disabled={busy} data-testid="followup-prompt-pause">
                    Stop chasing
                </Button>
            </div>
        </div>
    );
}
