import { useEffect, useState } from "react";
import { Loader2, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

export function ChaseDialog({ invoice, open, onOpenChange, onSent }) {
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [note, setNote] = useState("");
    const [quick, setQuick] = useState("");

    async function draft(mode = "regenerate") {
        if (!invoice) return;
        setLoading(true);
        try {
            const endpoint = mode === "quick" ? "/quick-compose" : `/invoices/${invoice._id}/draft-chase`;
            const payload = mode === "quick" ? { invoice_id: invoice._id, intent: quick } : { note };
            const { data } = await api.post(endpoint, payload);
            setSubject(data.subject); setBody(data.body);
        } catch (e) { toast.error(extractError(e)); }
        setLoading(false);
    }

    useEffect(() => { if (open && invoice) { setSubject(""); setBody(""); setNote(""); setQuick(""); draft("initial"); } }, [open, invoice?._id]);

    async function send() {
        setSending(true);
        try {
            await api.post(`/invoices/${invoice._id}/send-chase`, { subject, body });
            toast.success("Sent from your Gmail");
            await onSent?.();
            onOpenChange(false);
        } catch (e) { toast.error(extractError(e)); }
        setSending(false);
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl" data-testid="chase-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading">
                        {invoice?.status === "disputed" ? "Reply to" : "Follow up with"}{" "}
                        {invoice?.counterparty_name || invoice?.counterparty_email}
                    </DialogTitle>
                </DialogHeader>
                {loading ? (
                    <div className="py-16 flex items-center justify-center text-muted-foreground text-sm"><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Drafting…</div>
                ) : (
                    <div className="space-y-3">
                        <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" data-testid="chase-subject" />
                        <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} placeholder="Body" data-testid="chase-body" />
                        <div className="grid md:grid-cols-2 gap-2">
                            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Extra note for regenerate (optional)" data-testid="chase-note" />
                            <Button variant="outline" onClick={() => draft()} disabled={loading} data-testid="chase-regenerate"><RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Regenerate</Button>
                        </div>
                        <div className="grid md:grid-cols-2 gap-2 pt-2 border-t border-border">
                            <Input value={quick} onChange={(e) => setQuick(e.target.value)} placeholder="Quick-compose intent: e.g. 'tell him revised invoice tmrw'" data-testid="quick-intent" />
                            <Button variant="outline" onClick={() => draft("quick")} disabled={!quick || loading} data-testid="quick-expand">Expand with AI</Button>
                        </div>
                    </div>
                )}
                <div className="flex justify-between pt-4">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="chase-cancel"><X className="w-3.5 h-3.5 mr-1.5" /> Skip</Button>
                    <Button onClick={send} disabled={!subject || !body || sending} className="bg-foreground text-background" data-testid="chase-send">
                        {sending ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1.5" />}
                        Send from your Gmail
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
