import { useState } from "react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const NO_DUE_DATE_LABEL = "No due date — please add one";

/**
 * Inline due-date setter for ledger rows — does not open the invoice modal.
 */
export function AddDueDateButton({ invoiceId, onChanged, className = "" }) {
    const [open, setOpen] = useState(false);
    const [date, setDate] = useState("");
    const [busy, setBusy] = useState(false);

    async function save() {
        if (!date || !invoiceId) return;
        setBusy(true);
        try {
            await api.post(`/v1/invoices/${invoiceId}/action`, { action: "set_due_date", due_date: date });
            toast.success("Due date saved");
            setOpen(false);
            setDate("");
            await onChanged?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    className={`text-left text-amber-800 hover:underline underline-offset-2 ${className}`}
                    data-testid="add-due-date-trigger"
                    onClick={(e) => e.stopPropagation()}
                >
                    {NO_DUE_DATE_LABEL}
                </button>
            </PopoverTrigger>
            <PopoverContent
                align="start"
                className="w-auto p-3 space-y-2"
                data-testid="add-due-date-popover"
                onClick={(e) => e.stopPropagation()}
                onPointerDown={(e) => e.stopPropagation()}
            >
                <div className="text-xs font-medium text-foreground">Set due date</div>
                <div className="flex items-center gap-2">
                    <Input
                        type="date"
                        value={date}
                        onChange={(e) => setDate(e.target.value)}
                        className="h-9 w-[160px]"
                        data-testid="add-due-date-input"
                        onKeyDown={(e) => {
                            if (e.key === "Enter") {
                                e.preventDefault();
                                save();
                            }
                        }}
                    />
                    <Button size="sm" onClick={save} disabled={busy || !date} data-testid="add-due-date-save">
                        Save
                    </Button>
                </div>
            </PopoverContent>
        </Popover>
    );
}
