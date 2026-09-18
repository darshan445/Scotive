import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";
import { isTrackingPaused } from "@/lib/ledgerInvoices";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const CLOSED = new Set(["paid", "written_off"]);

/** Mark paid immediately, toast with Undo (5s), then refresh lists. */
export async function markInvoicePaidWithUndo(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "mark_paid" });
        await onChanged?.();
        toast.success("Marked as paid", {
            duration: 5000,
            action: {
                label: "Undo",
                onClick: async () => {
                    try {
                        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "undo" });
                        toast.success("Restored");
                        await onChanged?.();
                    } catch (e) {
                        toast.error(extractError(e));
                    }
                },
            },
        });
    } catch (e) {
        toast.error(extractError(e));
    }
}

export async function pauseInvoiceTracking(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "pause" });
        toast.success("Paused tracking");
        await onChanged?.();
    } catch (e) {
        toast.error(extractError(e));
    }
}

export async function resumeInvoiceTracking(invoiceId, { onChanged } = {}) {
    try {
        await api.post(`/v1/invoices/${invoiceId}/action`, { action: "resume" });
        toast.success("Resumed tracking");
        await onChanged?.();
    } catch (e) {
        toast.error(extractError(e));
    }
}

/**
 * ⋯ menu: Mark as paid · Pause/Resume tracking · Open in Gmail.
 */
export function InvoiceOverflowMenu({ invoice, onChanged, className = "" }) {
    if (!invoice?._id) return null;

    const closed = invoice.status && CLOSED.has(invoice.status);
    const paused = isTrackingPaused(invoice);
    const canMarkPaid = !closed;
    const canPause = !closed && !paused;
    const canResume = !closed && paused;
    const threadUrl = gmailThreadUrl(invoice.source_thread_id || invoice.thread_id);

    if (!canMarkPaid && !canPause && !canResume && !threadUrl) return null;

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
                <DropdownMenuContent align="end" className="w-48">
                    {canMarkPaid ? (
                        <DropdownMenuItem
                            data-testid="overflow-mark-paid"
                            onSelect={() => markInvoicePaidWithUndo(invoice._id, { onChanged })}
                        >
                            Mark as paid
                        </DropdownMenuItem>
                    ) : null}
                    {canPause ? (
                        <DropdownMenuItem
                            data-testid="overflow-pause-tracking"
                            onSelect={() => pauseInvoiceTracking(invoice._id, { onChanged })}
                        >
                            Pause tracking
                        </DropdownMenuItem>
                    ) : null}
                    {canResume ? (
                        <DropdownMenuItem
                            data-testid="overflow-resume-tracking"
                            onSelect={() => resumeInvoiceTracking(invoice._id, { onChanged })}
                        >
                            Resume tracking
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
