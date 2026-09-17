import { useState } from "react";
import { Eye, Forward, PlusCircle } from "lucide-react";
import { ManualInvoiceDialog } from "@/components/ManualInvoiceDialog";

export function WatchingEmptyState({ onChanged }) {
    const [manualOpen, setManualOpen] = useState(false);

    return (
        <div className="rounded-2xl border border-border bg-card p-8 md:p-12 text-center" data-testid="watching-empty">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-700 mb-4">
                <Eye className="w-6 h-6" />
            </div>
            <h2 className="type-title text-2xl md:text-3xl">
                Scotive is watching
            </h2>
            <p className="mt-3 text-muted-foreground max-w-md mx-auto leading-relaxed">
                No open invoices in QuickBooks right now. When you send the next one there, Scotive imports it and matches the conversation in Gmail or Outlook.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
                <button
                    onClick={() => setManualOpen(true)}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card text-sm font-medium hover:bg-muted transition-colors"
                    data-testid="watching-track-manual">
                    <PlusCircle className="w-4 h-4" />
                    Track manually
                </button>
            </div>
            <p className="mt-6 text-xs text-muted-foreground flex items-center justify-center gap-1.5">
                <Forward className="w-3.5 h-3.5" />
                Tip: invoices enter Scotive from QuickBooks, not from a forwarded PDF.
            </p>
            <ManualInvoiceDialog open={manualOpen} onOpenChange={setManualOpen} onCreated={() => onChanged?.()} />
        </div>
    );
}
