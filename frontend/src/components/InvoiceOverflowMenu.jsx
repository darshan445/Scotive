import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";
import { invoiceBucket, invoiceNumber, isApprovalDraft, BUCKETS } from "@/lib/chase";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Mark paid immediately. Books are still the source of truth — this is a manual override. */
export async function markInvoicePaidWithUndo(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "mark_paid" });
        await onChanged?.();
        toast.success("Marked as paid");
    } catch (e) {
        toast.error(extractError(e));
    }
}

export async function resumeInvoiceTracking(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "resume" });
        toast.success("Snooze cleared");
        await onChanged?.();
    } catch (e) {
        toast.error(extractError(e));
    }
}

/** Resume Friendly cadence. Firm/Final drafts are skipped so they leave Needs you. */
export async function putBackOnCadence(invoice, { onChanged } = {}) {
    if (!invoice?._id) return;
    try {
        if (isApprovalDraft(invoice)) {
            await api.post(`/v1/invoices/${invoice._id}/action`, { action: "skip_followup" });
        }
        if (
            invoice.chase_status === "needs_you"
            || invoice.chase_status === "stopped"
            || invoice.expected_pay_date
        ) {
            await api.post(`/v1/invoices/${invoice._id}/action`, { action: "resume" });
        }
        toast.success("Back on cadence");
        await onChanged?.();
    } catch (e) {
        toast.error(extractError(e));
    }
}

export async function stopInvoiceChase(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "stop_chasing" });
        toast.success("Stopped chasing");
        await onChanged?.();
    } catch (e) {
        toast.error(extractError(e));
    }
}

export function InvoiceOverflowMenu({ invoice, onChanged, className = "" }) {
    if (!invoice?._id) return null;

    const bucket = invoiceBucket(invoice);
    const closed = bucket === BUCKETS.paid;
    const threadUrl = gmailThreadUrl(invoice.source_thread_id || invoice.thread_id);

    if (closed && !threadUrl) return null;

    return (
        <div
            className={className}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
        >
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        type="button"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label="Invoice actions"
                        data-testid="invoice-overflow-menu"
                    >
                        <MoreHorizontal className="h-4 w-4" />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                    {!closed && bucket === BUCKETS.watching ? (
                        <DropdownMenuItem
                            data-testid="overflow-stop-chasing"
                            onSelect={() => {
                                if (typeof window !== "undefined"
                                    && !window.confirm(`Permanently stop reminders for Invoice ${invoiceNumber(invoice)}?`)) {
                                    return;
                                }
                                stopInvoiceChase(invoice._id, { onChanged });
                            }}
                        >
                            Stop reminders
                        </DropdownMenuItem>
                    ) : null}
                    {!closed ? (
                        <DropdownMenuItem
                            data-testid="overflow-mark-paid"
                            onSelect={() => markInvoicePaidWithUndo(invoice._id, { onChanged })}
                        >
                            Mark paid
                        </DropdownMenuItem>
                    ) : null}
                    {threadUrl ? (
                        <DropdownMenuItem
                            data-testid="overflow-open-gmail"
                            onSelect={() => window.open(threadUrl, "_blank", "noopener,noreferrer")}
                        >
                            Open in Gmail
                        </DropdownMenuItem>
                    ) : null}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
