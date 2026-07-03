import { useState } from "react";
import { toast } from "sonner";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, extractError } from "@/lib/api";

/**
 * Manual invoice-add dialog. Uses POST /api/invoices/manual and calls
 * `onCreated()` on success so the caller can refresh the ledger.
 */
export function ManualInvoiceDialog({ open, onOpenChange, onCreated }) {
    const [clientEmail, setClientEmail] = useState("");
    const [clientName, setClientName] = useState("");
    const [amount, setAmount] = useState("");
    const [currency, setCurrency] = useState("USD");
    const [invoiceRef, setInvoiceRef] = useState("");
    const [dueDate, setDueDate] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);

    function reset() {
        setClientEmail("");
        setClientName("");
        setAmount("");
        setCurrency("USD");
        setInvoiceRef("");
        setDueDate("");
        setNote("");
    }

    async function submit() {
        if (!clientEmail.trim() || !clientEmail.includes("@")) {
            toast.error("Client email is required.");
            return;
        }
        const amt = parseFloat(amount);
        if (!(amt > 0)) {
            toast.error("Amount must be greater than zero.");
            return;
        }
        setBusy(true);
        try {
            await api.post("/invoices/manual", {
                counterparty_email: clientEmail.trim(),
                counterparty_name: clientName.trim() || null,
                amount: amt,
                currency: currency || "USD",
                invoice_ref: invoiceRef.trim() || null,
                due_date: dueDate || null,
                note: note.trim() || null,
            });
            toast.success("Invoice added to your ledger");
            reset();
            onOpenChange?.(false);
            onCreated?.();
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange?.(o); }}>
            <DialogContent data-testid="manual-invoice-dialog" className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Track a payment manually</DialogTitle>
                    <DialogDescription>
                        Add an invoice the Gmail scan missed — off-email agreements,
                        paper contracts, or invoices sent from another tool.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="mi-email">Client email <span className="text-red-600">*</span></Label>
                            <Input
                                id="mi-email"
                                value={clientEmail}
                                onChange={(e) => setClientEmail(e.target.value)}
                                placeholder="ap@northbeam.com"
                                data-testid="manual-client-email"
                                autoFocus
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="mi-name">Client name</Label>
                            <Input
                                id="mi-name"
                                value={clientName}
                                onChange={(e) => setClientName(e.target.value)}
                                placeholder="Northbeam Studio"
                                data-testid="manual-client-name"
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="space-y-1.5 sm:col-span-2">
                            <Label htmlFor="mi-amount">Amount <span className="text-red-600">*</span></Label>
                            <Input
                                id="mi-amount"
                                type="number"
                                step="0.01"
                                min="0"
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                                placeholder="1250.00"
                                data-testid="manual-amount"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="mi-currency">Currency</Label>
                            <Input
                                id="mi-currency"
                                value={currency}
                                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                                maxLength={4}
                                data-testid="manual-currency"
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label htmlFor="mi-ref">Invoice reference</Label>
                            <Input
                                id="mi-ref"
                                value={invoiceRef}
                                onChange={(e) => setInvoiceRef(e.target.value)}
                                placeholder="INV-2026-42"
                                data-testid="manual-ref"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="mi-due">Due date</Label>
                            <Input
                                id="mi-due"
                                type="date"
                                value={dueDate}
                                onChange={(e) => setDueDate(e.target.value)}
                                data-testid="manual-due"
                            />
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="mi-note">Note (optional)</Label>
                        <Textarea
                            id="mi-note"
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            rows={2}
                            placeholder="Design engagement · signed 22 May 2026"
                            data-testid="manual-note"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => onOpenChange?.(false)} disabled={busy} data-testid="manual-cancel">
                        Cancel
                    </Button>
                    <Button onClick={submit} disabled={busy} data-testid="manual-submit">
                        {busy ? "Adding…" : "Add invoice"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
