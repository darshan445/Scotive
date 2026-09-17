import { Sparkles, X } from "lucide-react";
import { formatMoney } from "@/components/LedgerCard";

export function InvoiceDetectedBanner({ detection, onDismiss }) {
    if (!detection) return null;
    const name = detection.counterparty_name || detection.counterparty_email || "Client";
    const ref = detection.invoice_ref ? ` · ${detection.invoice_ref}` : "";

    return (
        <div
            className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 flex flex-wrap items-center justify-between gap-3 animate-fade-up"
            data-testid="invoice-detected-banner"
            role="status">
            <div className="flex items-start gap-3 min-w-0">
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-100 text-emerald-700 flex-shrink-0">
                    <Sparkles className="w-4 h-4" />
                </span>
                <div className="min-w-0">
                    <div className="text-sm font-semibold text-emerald-900">Invoice detected</div>
                    <div className="text-sm text-emerald-800 truncate">
                        {name}
                        <span className="font-mono tabular-nums">
                            {" "}· {formatMoney(detection.amount, detection.currency || "USD")}
                        </span>
                        {ref ? <span className="text-emerald-700/80">{ref}</span> : null}
                    </div>
                    <div className="text-[11px] text-emerald-700/80 mt-0.5">
                        Tracked automatically from QuickBooks — no action needed.
                    </div>
                </div>
            </div>
            <button
                type="button"
                onClick={onDismiss}
                className="inline-flex items-center gap-1 text-sm font-medium text-emerald-800 hover:text-emerald-950 flex-shrink-0"
                data-testid="invoice-detected-dismiss">
                <X className="w-3.5 h-3.5" />
                Got it
            </button>
        </div>
    );
}
