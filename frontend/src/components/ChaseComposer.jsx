import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/**
 * Draft review / send UI shared by the invoice modal (inline) and ChaseDialog.
 * Send uses draft-chase + send-chase unchanged.
 */
export function ChaseComposer({
    invoice,
    active = true,
    initialIntent = null,
    onCancel,
    onSent,
    onDirtyChange,
    showBack = false,
    className = "",
}) {
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [steerOpen, setSteerOpen] = useState(false);
    const [steerNote, setSteerNote] = useState("");
    const baselineRef = useRef({ subject: "", body: "" });
    const loadedForRef = useRef(null);

    const dirty = subject !== baselineRef.current.subject || body !== baselineRef.current.body;

    useEffect(() => {
        onDirtyChange?.(dirty);
    }, [dirty, onDirtyChange]);

    async function draft(mode = "regenerate", { intentOverride = null, noteOverride = "" } = {}) {
        if (!invoice) return;
        setLoading(true);
        try {
            const endpoint = mode === "quick" ? "/quick-compose" : `/invoices/${invoice._id}/draft-chase`;
            const payload = mode === "quick"
                ? { invoice_id: invoice._id, intent: intentOverride || "" }
                : { note: noteOverride || "" };
            const { data } = await api.post(endpoint, payload);
            setSubject(data.subject);
            setBody(data.body);
            baselineRef.current = { subject: data.subject || "", body: data.body || "" };
            onDirtyChange?.(false);
        } catch (e) {
            toast.error(extractError(e));
        }
        setLoading(false);
    }

    useEffect(() => {
        if (!active || !invoice?._id) return;
        const key = `${invoice._id}:${initialIntent || ""}`;
        if (loadedForRef.current === key) return;
        loadedForRef.current = key;
        setSubject("");
        setBody("");
        setSteerNote("");
        setSteerOpen(false);
        baselineRef.current = { subject: "", body: "" };
        onDirtyChange?.(false);
        if (initialIntent) {
            draft("quick", { intentOverride: initialIntent });
        } else {
            draft("initial");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per open/invoice/intent
    }, [active, invoice?._id, initialIntent]);

    useEffect(() => {
        if (!active) {
            loadedForRef.current = null;
            setSteerOpen(false);
        }
    }, [active]);

    async function confirmRegenerate() {
        const note = steerNote.trim();
        setSteerOpen(false);
        await draft("regenerate", { noteOverride: note });
        setSteerNote("");
    }

    async function send() {
        setSending(true);
        try {
            await api.post(`/invoices/${invoice._id}/send-chase`, { subject, body });
            toast.success("Sent from your Gmail");
            baselineRef.current = { subject, body };
            onDirtyChange?.(false);
            await onSent?.();
        } catch (e) {
            toast.error(extractError(e));
        }
        setSending(false);
    }

    const title = invoice?.status === "disputed" ? "Reply to" : "Follow up with";
    const name = invoice?.counterparty_name || invoice?.counterparty_email || "client";

    return (
        <div className={cn("flex flex-col", className)} data-testid="chase-composer">
            <div className="flex items-center gap-2 mb-3">
                {showBack ? (
                    <button
                        type="button"
                        onClick={onCancel}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground sm:hidden"
                        aria-label="Back to conversation"
                        data-testid="chase-back"
                    >
                        <ArrowLeft className="w-4 h-4" />
                    </button>
                ) : null}
                <h3 className="font-heading font-semibold text-base min-w-0 flex-1 truncate">
                    {title} {name}
                </h3>
                <Popover open={steerOpen} onOpenChange={setSteerOpen}>
                    <PopoverTrigger asChild>
                        <button
                            type="button"
                            disabled={loading}
                            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50 flex-shrink-0"
                            data-testid="chase-regenerate"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
                            Regenerate
                        </button>
                    </PopoverTrigger>
                    <PopoverContent align="end" className="w-80 p-3 space-y-2" data-testid="chase-regenerate-popover">
                        <Input
                            value={steerNote}
                            onChange={(e) => setSteerNote(e.target.value)}
                            placeholder="Optional: steer it — e.g. 'friendlier' or 'mention the revised invoice'"
                            data-testid="chase-note"
                            onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                    e.preventDefault();
                                    confirmRegenerate();
                                }
                            }}
                            autoFocus
                        />
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => setSteerOpen(false)}
                                data-testid="chase-regenerate-dismiss"
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                onClick={confirmRegenerate}
                                disabled={loading}
                                data-testid="chase-regenerate-confirm"
                            >
                                Regenerate
                            </Button>
                        </div>
                    </PopoverContent>
                </Popover>
            </div>

            {loading ? (
                <div className="py-12 flex items-center justify-center text-muted-foreground text-sm">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Drafting…
                </div>
            ) : (
                <div className="space-y-3">
                    <Input
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        placeholder="Subject"
                        data-testid="chase-subject"
                    />
                    <Textarea
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        rows={8}
                        placeholder="Body"
                        data-testid="chase-body"
                    />
                </div>
            )}

            <div className="flex justify-between pt-4 mt-auto">
                <Button variant="ghost" onClick={onCancel} data-testid="chase-cancel">
                    <X className="w-3.5 h-3.5 mr-1.5" /> Cancel
                </Button>
                <Button
                    onClick={send}
                    disabled={!subject || !body || sending || loading}
                    className="bg-foreground text-background"
                    data-testid="chase-send"
                >
                    {sending ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1.5" />}
                    Send from your Gmail
                </Button>
            </div>
        </div>
    );
}

/** Returns true if composer should collapse (caller collapses). False if user cancelled discard. */
export function confirmDiscardComposer(dirty) {
    if (!dirty) return true;
    return typeof window !== "undefined"
        ? window.confirm("Discard this draft?")
        : true;
}
