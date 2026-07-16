import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";
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
        await api.post(`/invoices/${invoiceId}/action`, { action: "mark_paid" });
        await onChanged?.();
        toast.success("Marked as paid", {
            duration: 5000,
            action: {
                label: "Undo",
                onClick: async () => {
                    try {
                        await api.post(`/invoices/${invoiceId}/action`, { action: "undo" });
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

/**
 * ⋯ menu for list/digest rows: Mark as paid + Open in Gmail.
 * Callers must stopPropagation on the trigger wrapper so row clicks still open detail.
 */
export function InvoiceOverflowMenu({ invoice, onChanged, className = "" }) {
    if (!invoice?._id) return null;

    const canMarkPaid = invoice.status && !CLOSED.has(invoice.status);
    const threadUrl = gmailThreadUrl(invoice.source_thread_id || invoice.thread_id);

    if (!canMarkPaid && !threadUrl) return null;

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
                <DropdownMenuContent align="end" className="w-44">
                    {canMarkPaid ? (
                        <DropdownMenuItem
                            data-testid="overflow-mark-paid"
                            onSelect={() => markInvoicePaidWithUndo(invoice._id, { onChanged })}
                        >
                            Mark as paid
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
