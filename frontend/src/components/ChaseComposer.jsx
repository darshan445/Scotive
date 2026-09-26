import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Loader2, Paperclip, RefreshCw, Send, X } from "lucide-react";
import { toast } from "sonner";
import { api, extractError, unwrapData } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { CHECK_BACK_HELP, CheckBackSelect } from "@/components/WaitUntilControl";
import { shortWaitDate } from "@/lib/chase";
import { cn } from "@/lib/utils";

function asThreadSubject(raw) {
    const s = String(raw || "").trim();
    if (!s) return "";
    return /^re:/i.test(s) ? s : `Re: ${s}`;
}

/**
 * Draft review / send UI shared by the invoice drawer (inline) and ChaseDialog.
 * Chase auto-drafts. Decision waits for an owner instruction. Pay link is assembled on the server.
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
    onWaitUntilChange,
    requireCheckBack = true,
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
    const [steerNote, setSteerNote] = useState("");
    const [reason, setReason] = useState("");
    const [needsInstruction, setNeedsInstruction] = useState(false);
    const [instructionHint, setInstructionHint] = useState("");
    const [includePayLink, setIncludePayLink] = useState(false);
    const [mailPreview, setMailPreview] = useState(null);
    const [files, setFiles] = useState([]);
    const [checkBackDate, setCheckBackDate] = useState(waitUntil || "");
    const baselineRef = useRef({ subject: "", body: "" });
    const loadedForRef = useRef(null);

    const dirty = subject !== baselineRef.current.subject || body !== baselineRef.current.body;
    const waitingOnBrief = needsInstruction && !body;

    useEffect(() => {
        onDirtyChange?.(dirty);
    }, [dirty, onDirtyChange]);

    async function draft(_mode = "regenerate", { intentOverride = null, noteOverride = "" } = {}) {
        if (!invoice) return;
        const note = noteOverride || "";
        if (waitingOnBrief && _mode !== "initial" && !note.trim()) {
            toast.error("Tell us what to send first");
            return;
        }
        setLoading(true);
        try {
            const { data } = await api.post(`/v1/invoices/${invoice._id}/draft-chase`, {
                note,
                intent: intentOverride || "",
            });
            const payload = unwrapData(data);
            applyPayload(payload, defaultSubject);
        } catch (e) {
            toast.error(extractError(e));
        }
        setLoading(false);
    }

    function applyPayload(payload, fallbackSubject = "") {
        const nextSubject = payload.subject || fallbackSubject || "";
        const nextBody = payload.body || "";
        setSubject(embedded ? asThreadSubject(nextSubject) : nextSubject);
        setBody(nextBody);
        setToneLabel(payload.tone_label || null);
        setIsReplyDraft(Boolean(payload.is_reply));
        setReason(payload.reason || "");
        setNeedsInstruction(Boolean(payload.needs_instruction) && !nextBody);
        setInstructionHint(payload.instruction_hint || "");
        setIncludePayLink(Boolean(payload.include_pay_link));
        setMailPreview(payload.mail_preview || null);
        baselineRef.current = { subject: nextSubject, body: nextBody };
        onDirtyChange?.(false);
    }

    useEffect(() => {
        if (!active || !invoice?._id) return;
        const key = `${invoice._id}:${initialIntent || ""}:${autoDraft ? "auto" : "manual"}`;
        if (loadedForRef.current === key) return;
        loadedForRef.current = key;
        const rawSubject = initialDraft?.subject || defaultSubject || "";
        const subject0 = embedded ? asThreadSubject(rawSubject) : rawSubject;
        setSubject(subject0);
        setBody(initialDraft?.body || "");
        setToneLabel(initialDraft?.tone_label || null);
        setIsReplyDraft(Boolean(initialDraft?.is_reply));
        setSteerNote("");
        setReason("");
        setNeedsInstruction(false);
        setInstructionHint("");
        setIncludePayLink(false);
        setMailPreview(null);
        setFiles([]);
        setCheckBackDate(waitUntil || "");
        baselineRef.current = { subject: subject0, body: initialDraft?.body || "" };
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
        setCheckBackDate(waitUntil || "");
    }, [waitUntil]);

    function updateCheckBackDate(iso) {
        setCheckBackDate(iso || "");
        onWaitUntilChange?.(iso || "");
    }

    useEffect(() => {
        if (!active) {
            loadedForRef.current = null;
            setSteerNote("");
        }
    }, [active]);

    async function confirmDraft() {
        const note = steerNote.trim();
        await draft(body ? "regenerate" : "instruct", { noteOverride: note });
        if (note) setSteerNote("");
    }

    async function send() {
        if (requireCheckBack && !checkBackDate) {
            toast.error("Pick a check-back date first");
            return;
        }
        setSending(true);
        try {
            const form = new FormData();
            form.append("subject", subject);
            form.append("body", body);
            form.append("wait_until", checkBackDate);
            form.append("include_pay_link", includePayLink ? "true" : "false");
            files.forEach((file) => form.append("attachments[]", file));
            await api.post(`/v1/invoices/${invoice._id}/send-chase`, form, { timeout: 60000 });
            toast.success(`Sent · we'll check back ${shortWaitDate(checkBackDate) || checkBackDate}`);
            baselineRef.current = { subject, body };
            onDirtyChange?.(false);
            await onSent?.();
        } catch (e) {
            toast.error(extractError(e));
        }
        setSending(false);
    }

    function addFiles(list) {
        const incoming = Array.from(list || []);
        if (!incoming.length) return;
        const next = files.concat(incoming);
        if (next.length > 10) {
            toast.error("Max 10 attachments");
            return;
        }
        const total = next.reduce((sum, file) => sum + file.size, 0);
        if (total > 25 * 1024 * 1024) {
            toast.error("Attachments must be under 25 MB total");
            return;
        }
        setFiles(next);
    }

    const canSend = Boolean(subject && body && (!requireCheckBack || checkBackDate) && !sending && !loading);
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
                </div>
            )}

            {loading ? (
                <div className="py-12 flex items-center justify-center text-muted-foreground text-sm">
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Drafting…
                </div>
            ) : (
                <div className="space-y-3">
                    {reason ? (
                        <p className="text-sm text-muted-foreground" data-testid="chase-draft-reason">
                            {reason}
                        </p>
                    ) : null}
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
                    {!embedded && toneLabel && !waitingOnBrief ? (
                        <div data-testid="chase-tone-label">
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border border-border bg-muted/50 text-muted-foreground">
                                {toneLabel}
                            </span>
                        </div>
                    ) : null}
                    {waitingOnBrief ? null : (
                        <>
                            <Textarea
                                value={body}
                                onChange={(e) => setBody(e.target.value)}
                                rows={8}
                                placeholder="Write the email…"
                                data-testid="chase-body"
                            />
                            {mailPreview ? <InvoiceMailPreview preview={mailPreview} /> : null}
                            <div className="space-y-1.5" data-testid="chase-attachments">
                                <label className="inline-flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer hover:text-foreground">
                                    <Paperclip className="w-3.5 h-3.5" />
                                    Attach
                                    <input
                                        type="file"
                                        multiple
                                        className="sr-only"
                                        onChange={(e) => {
                                            addFiles(e.target.files);
                                            e.target.value = "";
                                        }}
                                    />
                                </label>
                                {files.length ? (
                                    <ul className="space-y-1">
                                        {files.map((file, index) => (
                                            <li key={`${file.name}-${index}`} className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                                                <span className="truncate">{file.name}</span>
                                                <button
                                                    type="button"
                                                    className="text-muted-foreground hover:text-foreground"
                                                    onClick={() => setFiles(files.filter((_, i) => i !== index))}
                                                    aria-label={`Remove ${file.name}`}
                                                >
                                                    <X className="w-3 h-3" />
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p className="text-[11px] text-muted-foreground">Optional. Same as Gmail — up to 10 files, 25 MB total.</p>
                                )}
                            </div>
                        </>
                    )}
                    <div className="space-y-1.5" data-testid="chase-instruction">
                        <Input
                            value={steerNote}
                            onChange={(e) => setSteerNote(e.target.value)}
                            placeholder={instructionHint || (waitingOnBrief
                                ? "e.g. invoice stands, or offer $1,800 if they pay this week"
                                : "Optional: shorter, mention the PO, change the tone")}
                            data-testid="chase-note"
                            onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                    e.preventDefault();
                                    confirmDraft();
                                }
                            }}
                        />
                        <div className="flex justify-end">
                            <Button
                                type="button"
                                size="sm"
                                variant={waitingOnBrief ? "default" : "outline"}
                                onClick={confirmDraft}
                                disabled={loading || (waitingOnBrief && !steerNote.trim())}
                                data-testid="chase-regenerate"
                            >
                                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
                                {body ? "Adjust draft" : "Draft reply"}
                            </Button>
                        </div>
                    </div>
                    {!waitingOnBrief && requireCheckBack ? (
                        <div className="space-y-1.5">
                            <CheckBackSelect value={checkBackDate} onChange={updateCheckBackDate} />
                            <p className="text-xs leading-relaxed text-muted-foreground">{CHECK_BACK_HELP}</p>
                        </div>
                    ) : null}
                </div>
            )}

            {waitingOnBrief || loading ? null : embedded ? (
                <div className="mt-5 space-y-2.5">
                    {beforeSend}
                    <Button
                        onClick={send}
                        disabled={!canSend}
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
                        disabled={!canSend}
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

function InvoiceMailPreview({ preview }) {
    if (!preview) return null;
    return (
        <div className="rounded-md border border-border bg-muted/40 px-4 py-3 space-y-2" data-testid="chase-mail-preview">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Invoice summary</div>
            <dl className="grid grid-cols-[7.5rem_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Invoice #</dt>
                <dd>{preview.invoice_number}</dd>
                <dt className="text-muted-foreground">Invoice date</dt>
                <dd>{preview.issue_date}</dd>
                <dt className="text-muted-foreground">Due date</dt>
                <dd>{preview.due_date}</dd>
                <dt className="text-muted-foreground">Amount due</dt>
                <dd>{preview.amount_due}</dd>
            </dl>
            {preview.include_pay_link ? (
                <div className="pt-1">
                    <span className="inline-flex items-center rounded-md bg-[#2ca01c] px-3 py-1.5 text-xs font-semibold text-white">
                        {preview.pay_label || "View and pay this invoice"}
                    </span>
                </div>
            ) : null}
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
