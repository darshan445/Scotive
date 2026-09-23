import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError, unwrapData } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

function asThreadSubject(raw) {
    const s = String(raw || "").trim();
    if (!s) return "";
    return /^re:/i.test(s) ? s : `Re: ${s}`;
}

/**
 * Draft review / send UI shared by the invoice drawer (inline) and ChaseDialog.
 * Send uses draft-chase + send-chase unchanged.
 */
export function ChaseComposer({
    invoice,
    active = true,
    initialIntent = null,
    initialDraft = null,
    defaultSubject = "",
    autoDraft = true,
    onCancel,
    onSent,
    onDirtyChange,
    showBack = false,
    embedded = false,
    waitUntil = null,
    sendLabel = "Send reply from Gmail",
    composeTitle = "Your reply",
    beforeSend = null,
    className = "",
}) {
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [subject, setSubject] = useState("");
    const [body, setBody] = useState("");
    const [toneLabel, setToneLabel] = useState(null);
    const [isReplyDraft, setIsReplyDraft] = useState(false);
    const [steerOpen, setSteerOpen] = useState(false);
    const [steerNote, setSteerNote] = useState("");
    const baselineRef = useRef({ subject: "", body: "" });
    const loadedForRef = useRef(null);

    const dirty = subject !== baselineRef.current.subject || body !== baselineRef.current.body;

    useEffect(() => {
        onDirtyChange?.(dirty);
    }, [dirty, onDirtyChange]);

    async function draft(_mode = "regenerate", { intentOverride = null, noteOverride = "" } = {}) {
        if (!invoice) return;
        setLoading(true);
        try {
            const { data } = await api.post(`/v1/invoices/${invoice._id}/draft-chase`, {
                note: noteOverride || "",
                intent: intentOverride || "",
            });
            const payload = unwrapData(data);
            setSubject(payload.subject);
            setBody(payload.body);
            setToneLabel(payload.tone_label || null);
            setIsReplyDraft(Boolean(payload.is_reply));
            baselineRef.current = { subject: payload.subject || "", body: payload.body || "" };
            onDirtyChange?.(false);
        } catch (e) {
            toast.error(extractError(e));
        }
        setLoading(false);
    }

    useEffect(() => {
        if (!active || !invoice?._id) return;
        const key = `${invoice._id}:${initialIntent || ""}:${initialDraft?.subject || ""}:${autoDraft ? "auto" : "manual"}`;
        if (loadedForRef.current === key) return;
        loadedForRef.current = key;
        const rawSubject = initialDraft?.subject || defaultSubject || "";
        const subject0 = embedded ? asThreadSubject(rawSubject) : rawSubject;
        const body0 = initialDraft?.body || "";
        setSubject(subject0);
        setBody(body0);
        setToneLabel(initialDraft?.tone_label || null);
        setIsReplyDraft(Boolean(initialDraft?.is_reply));
        setSteerNote("");
        setSteerOpen(false);
        baselineRef.current = { subject: subject0, body: body0 };
        onDirtyChange?.(false);
        if (!autoDraft) return;
        if (initialIntent) {
            draft("quick", { intentOverride: initialIntent });
        } else {
            draft("initial");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per open/invoice/intent
    }, [active, invoice?._id, initialIntent, autoDraft]);

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
            await api.post(`/v1/invoices/${invoice._id}/send-chase`, {
                subject,
                body,
                wait_until: waitUntil || undefined,
            });
            toast.success(waitUntil ? `Sent · we'll check back ${waitUntil}` : "Sent from your Gmail");
            baselineRef.current = { subject, body };
            onDirtyChange?.(false);
            await onSent?.();
        } catch (e) {
            toast.error(extractError(e));
        }
        setSending(false);
    }

    const title = (isReplyDraft || invoice?.status === "needs_you" || invoice?.last_human_inbound_at)
        ? "Reply to"
        : "Follow up with";
    const name = invoice?.counterparty_name || invoice?.counterparty_email || "client";

    return (
        <div className={cn("flex flex-col", className)} data-testid="chase-composer">
            {embedded ? null : (
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
                        {composeTitle || `${title} ${name}`}
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
                                {body ? "Regenerate" : "Draft a reply"}
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
                                <Button type="button" variant="ghost" size="sm" onClick={() => setSteerOpen(false)} data-testid="chase-regenerate-dismiss">
                                    Cancel
                                </Button>
                                <Button type="button" size="sm" onClick={confirmRegenerate} disabled={loading} data-testid="chase-regenerate-confirm">
                                    Regenerate
                                </Button>
                            </div>
                        </PopoverContent>
                    </Popover>
                </div>
            )}

            {!embedded && toneLabel && !loading ? (
                <div className="mb-3" data-testid="chase-tone-label">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border border-border bg-muted/50 text-muted-foreground">
                        {toneLabel}
                    </span>
                </div>
            ) : null}

            {loading ? (
                <div className="py-12 flex items-center justify-center text-muted-foreground text-sm">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Drafting…
                </div>
            ) : (
                <div className="space-y-3">
                    {embedded ? (
                        <p className="text-xs text-muted-foreground" data-testid="chase-subject">
                            Thread: {subject || "—"}
                        </p>
                    ) : (
                        <Input
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                            placeholder="Subject"
                            data-testid="chase-subject"
                        />
                    )}
                    <Textarea
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        rows={8}
                        placeholder="Write the email…"
                        data-testid="chase-body"
                    />
                </div>
            )}

            {embedded ? (
                <div className="mt-5 space-y-2.5">
                    {beforeSend}
                    <Button
                        onClick={send}
                        disabled={!subject || !body || sending || loading}
                        className="w-full bg-foreground text-background"
                        data-testid="chase-send"
                    >
                        {sending ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1.5" />}
                        {sendLabel}
                    </Button>
                </div>
            ) : (
                <div className="flex items-center justify-between gap-3 pt-4 mt-auto">
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
                        {sendLabel}
                    </Button>
                </div>
            )}
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
