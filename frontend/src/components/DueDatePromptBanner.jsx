import { useState } from "react";
import { Calendar, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { formatMoney } from "@/components/LedgerCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function DueDatePromptBanner({ prompt, onDismiss, onChanged }) {
    const [date, setDate] = useState("");
    const [busy, setBusy] = useState(false);
    if (!prompt) return null;

    const name = prompt.counterparty_name || prompt.counterparty_email || "Client";
    const id = prompt.invoice_id;

    async function pickDate() {
        if (!date) return;
        setBusy(true);
        try {
            await api.post(`/invoices/${id}/action`, { action: "set_due_date", due_date: date });
            toast.success("Due date saved");
            onDismiss?.();
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    async function skipDueDate() {
        setBusy(true);
        try {
            await api.post(`/invoices/${id}/action`, { action: "skip_due_date" });
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
            className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 flex flex-col gap-3 animate-fade-up"
            data-testid="due-date-prompt-banner"
            role="status">
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-amber-100 text-amber-800 flex-shrink-0">
                        <Calendar className="w-4 h-4" />
                    </span>
                    <div className="min-w-0">
                        <div className="text-sm font-semibold text-amber-950">When&apos;s this due?</div>
                        <div className="text-sm text-amber-900">
                            {name}
                            <span className="font-mono tabular-nums">
                                {" "}· {formatMoney(prompt.amount, prompt.currency || "USD")}
                            </span>
                        </div>
                        <div className="text-[11px] text-amber-800/90 mt-0.5">
                            Tracked from your sent mail — pick a due date or skip for now.
                        </div>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={skipDueDate}
                    disabled={busy}
                    className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-widest text-amber-800 hover:text-amber-950 flex-shrink-0"
                    data-testid="due-date-prompt-dismiss">
                    <X className="w-3.5 h-3.5" />
                </button>
            </div>
            <div className="flex flex-wrap items-center gap-2 pl-12">
                <Input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="max-w-[170px] h-9 bg-white"
                    data-testid="due-date-prompt-input"
                />
                <Button size="sm" onClick={pickDate} disabled={busy || !date} data-testid="due-date-prompt-save">
                    Pick date
                </Button>
                <Button size="sm" variant="ghost" onClick={skipDueDate} disabled={busy} data-testid="due-date-prompt-skip">
                    No due date
                </Button>
            </div>
        </div>
    );
}
