import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Send, X } from "lucide-react";
import { toast } from "sonner";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { ChaseComposer, confirmDiscardComposer } from "@/components/ChaseComposer";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, extractError } from "@/lib/api";
import { formatDate, formatMoney } from "@/components/LedgerCard";
import {
    invoiceStatusDisplay,
    invoiceSubject,
    isJunkInvoiceRef,
    factualDigestLine,
    hasPendingPaymentClaim,
} from "@/lib/invoiceCopy";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";
import { cn } from "@/lib/utils";

const STATUS_STYLES = {
    invoiced: "bg-gray-100 text-gray-700 border-gray-200",
    overdue: "bg-red-50 text-red-700 border-red-200",
    promised: "bg-yellow-50 text-yellow-800 border-yellow-200",
    promise_broken: "bg-orange-50 text-orange-700 border-orange-200",
    disputed: "bg-purple-50 text-purple-700 border-purple-200",
    partially_paid: "bg-green-50 text-green-700 border-green-200",
    paid_unconfirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    paid: "bg-green-50 text-green-700 border-green-200",
    written_off: "bg-gray-100 text-gray-500 border-gray-200",
    stale: "bg-stone-100 text-stone-600 border-stone-200",
};

function StatusChip({ inv }) {
    const status = inv?.status || "invoiced";
    const hasClaim = inv?.disputed_claim_amount != null && Number(inv.disputed_claim_amount) > 0;
    const pendingPay = hasPendingPaymentClaim(inv);
    let styleKey = status;
    if (pendingPay && (status === "disputed" || hasClaim)) styleKey = "paid_unconfirmed";
    else if (status === "partially_paid" && hasClaim) styleKey = "disputed";
    const cls = STATUS_STYLES[styleKey] || STATUS_STYLES.invoiced;
    return (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${cls}`} data-testid="invoice-status-pill">
            {invoiceStatusDisplay(inv)}
        </span>
    );
}

function formatMsgTime(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        return d.toLocaleString(undefined, {
            month: "short", day: "numeric", year: "numeric",
            hour: "numeric", minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

function calendarDayKey(iso) {
    if (!iso) return null;
    try {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return null;
        return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    } catch {
        return null;
    }
}

function formatDaySeparator(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        const now = new Date();
        const opts = { weekday: "short", month: "short", day: "numeric" };
        if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
        return d.toLocaleDateString(undefined, opts);
    } catch {
        return iso;
    }
}

function initialsFromName(name) {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

/** Client display name — never the raw email address. */
function clientSenderLabel(m, inv) {
    const named = (inv?.counterparty_name || "").trim();
    if (named) return named;
    const from = (m?.from || "").trim();
    if (!from) return "Client";
    const angled = from.match(/^"?([^"<]+)"?\s*<[^>]+>/);
    if (angled) {
        const name = angled[1].trim();
        if (name && !name.includes("@")) return name;
    }
    if (from.includes("@")) return "Client";
    return from;
}

function subjectsDiffer(msgSubject, threadSubject) {
    const a = (msgSubject || "").trim().toLowerCase();
    const b = (threadSubject || "").trim().toLowerCase();
    if (!a) return false;
    if (!b) return true;
    const stripRe = (s) => s.replace(/^(re|fw|fwd)\s*:\s*/gi, "").trim();
    return stripRe(a) !== stripRe(b);
}

function MessageAvatar({ isYou, label }) {
    if (isYou) {
        return (
            <span
                className="inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary text-[9px] font-semibold text-primary-foreground"
                aria-hidden
            >
                You
            </span>
        );
    }
    return (
        <span
            className="inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground"
            aria-hidden
        >
            {initialsFromName(label)}
        </span>
    );
}

/** Turn residual HTML / quoted-reply chrome into the new message text only. */
function emailBodyToText(raw) {
    if (!raw) return "";
    let text = String(raw);
    const looksHtml = /<\/?[a-z][\s\S]*>/i.test(text);
    if (looksHtml) {
        text = text
            .replace(/<style[\s\S]*?<\/style>/gi, "")
            .replace(/<script[\s\S]*?<\/script>/gi, "")
            .replace(/<div[^>]*class=["'][^"']*gmail_quote[^"']*["'][^>]*>[\s\S]*$/i, "")
            .replace(/<br\s*\/?>/gi, "\n")
            .replace(/<\/p>/gi, "\n\n")
            .replace(/<\/div>/gi, "\n")
            .replace(/<\/li>/gi, "\n")
            .replace(/<\/h[1-6]>/gi, "\n\n")
            .replace(/<[^>]+>/g, "");
        const ta = typeof document !== "undefined" ? document.createElement("textarea") : null;
        if (ta) {
            ta.innerHTML = text;
            text = ta.value;
        } else {
            text = text
                .replace(/&nbsp;/g, " ")
                .replace(/&lt;/g, "<")
                .replace(/&gt;/g, ">")
                .replace(/&amp;/g, "&")
                .replace(/&quot;/g, '"');
        }
    }

    const cutPatterns = [
        /\nOn .+wrote:\s*$/im,
        /\nOn .+wrote:\s*\n/i,
        /\n-{2,}\s*Original Message\s*-{2,}/i,
        /\nFrom:\s.+\nSent:\s/i,
        /\nLe .+a écrit\s*:/i,
    ];
    for (const pat of cutPatterns) {
        const m = pat.exec(text);
        if (m && m.index > 0) {
            text = text.slice(0, m.index);
            break;
        }
    }

    const lines = [];
    for (const line of text.split("\n")) {
        const stripped = line.trimStart();
        if (stripped.startsWith(">")) break;
        if (/^On .+ wrote:$/i.test(stripped)) break;
        lines.push(line);
    }
    return lines.join("\n").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function headerFactLine(inv) {
    if (hasPendingPaymentClaim(inv)) {
        return factualDigestLine(inv, "confirm_prompts");
    }
    if (inv.status === "promise_broken") {
        return factualDigestLine(inv, "broken_promises");
    }
    if (inv.status === "promised" && inv.promise_date) {
        return `Promise date ${formatDate(inv.promise_date)}`;
    }
    if (inv.status === "overdue") return factualDigestLine(inv, "due_overdue");
    if (
        inv.status === "disputed"
        || inv.disputed_claim_amount != null
        || (inv.payment_claim_amount != null && Number(inv.payment_claim_amount) > 0.005)
    ) {
        return factualDigestLine(inv, "needs_reply");
    }
    if (inv.due_date) return `Due ${formatDate(inv.due_date)}`;
    if (inv.promise_date) return `Promised ${formatDate(inv.promise_date)}`;
    return null;
}

function HeaderSkeleton() {
    return (
        <div className="space-y-3" data-testid="invoice-detail-skeleton">
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-7 w-3/4" />
            <Skeleton className="h-4 w-24" />
        </div>
    );
}

/**
 * Invoice detail modal. Follow up / Reply / Adjust expand an inline composer
 * (no second modal). Esc/scrim collapses composer first, then closes.
 */
export function InvoiceDetailDrawer({ invoiceId, preview = null, open, onClose, onChanged }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");
    const [busy, setBusy] = useState(false);
    /** Mounted (includes exit animation). */
    const [composePresent, setComposePresent] = useState(false);
    /** Expanded = open; false triggers bottom→top collapse. */
    const [composeExpanded, setComposeExpanded] = useState(false);
    const [composeIntent, setComposeIntent] = useState(null);
    const composeDirtyRef = useRef(false);
    const collapseTimerRef = useRef(null);

    const refresh = useCallback(() => {
        if (!invoiceId) return;
        setErr("");
        api.get(`/invoices/${invoiceId}/conversation`)
            .then(({ data: res }) => setData(res))
            .catch((e) => setErr(extractError(e)));
    }, [invoiceId]);

    useEffect(() => {
        if (!open || !invoiceId) return;
        setData(null);
        setErr("");
        if (collapseTimerRef.current) {
            clearTimeout(collapseTimerRef.current);
            collapseTimerRef.current = null;
        }
        setComposePresent(false);
        setComposeExpanded(false);
        setComposeIntent(null);
        composeDirtyRef.current = false;
        refresh();
    }, [open, invoiceId, refresh]);

    const inv = data?.invoice || (preview && preview._id === invoiceId ? preview : null);

    function finishCollapseComposer() {
        collapseTimerRef.current = null;
        setComposePresent(false);
        setComposeExpanded(false);
        setComposeIntent(null);
        composeDirtyRef.current = false;
    }

    function collapseComposer() {
        if (!composePresent) return;
        setComposeExpanded(false);
        if (collapseTimerRef.current) clearTimeout(collapseTimerRef.current);
        collapseTimerRef.current = window.setTimeout(finishCollapseComposer, 300);
    }

    /** Collapse composer only — used by Cancel (and after Send). */
    function tryCollapseComposer() {
        if (!composePresent) return true;
        if (!confirmDiscardComposer(composeDirtyRef.current)) return false;
        collapseComposer();
        return true;
    }

    /** Close the whole invoice modal (Esc / scrim / X). Composer is not collapsed separately. */
    function requestModalClose() {
        if (composePresent && !confirmDiscardComposer(composeDirtyRef.current)) return;
        onClose?.();
    }

    async function act(action) {
        if (!inv) return;
        setBusy(true);
        try {
            await api.post(`/invoices/${inv._id}/action`, { action });
            toast.success(
                action === "mark_paid" ? "Marked paid"
                    : action === "deny_payment_claim" ? "Marked not yet received"
                      : "Updated",
            );
            await onChanged?.();
            if (action === "mark_paid") {
                onClose?.();
            } else {
                refresh();
            }
        } catch (e) {
            toast.error(extractError(e));
        } finally {
            setBusy(false);
        }
    }

    function openComposer(intent = null) {
        if (collapseTimerRef.current) {
            clearTimeout(collapseTimerRef.current);
            collapseTimerRef.current = null;
        }
        setComposeIntent(intent);
        setComposePresent(true);
        setComposeExpanded(false);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => setComposeExpanded(true));
        });
    }

    const actions = (() => {
        if (!inv) return null;
        const s = inv.status;
        const composing = composePresent;
        if (s === "paid" || s === "written_off") return null;

        // Pending payment claim (full or partial, with or without dispute):
        // Received / Not yet only — never two action sets for one invoice.
        if (hasPendingPaymentClaim(inv)) {
            return (
                <>
                    <Button onClick={() => act("mark_paid")} disabled={busy} data-testid="detail-received">Received</Button>
                    <Button variant="outline" onClick={() => act("deny_payment_claim")} disabled={busy} data-testid="detail-not-yet">Not yet</Button>
                </>
            );
        }

        // One primary compose verb by situation + Mark paid secondary
        const needsCompose =
            s === "disputed"
            || inv.needs_reply
            || ["overdue", "promise_broken", "invoiced", "promised", "partially_paid", "stale"].includes(s);
        if (!needsCompose) return null;

        const isReply = s === "disputed" || inv.needs_reply;
        return (
            <>
                <Button
                    onClick={() => openComposer()}
                    disabled={busy || composing}
                    aria-pressed={composing}
                    data-testid={isReply ? "detail-reply" : "detail-follow-up"}
                >
                    <Send className="w-3.5 h-3.5 mr-1.5" />
                    {isReply ? "Reply" : "Follow up"}
                </Button>
                <Button variant="outline" onClick={() => act("mark_paid")} disabled={busy} data-testid="detail-mark-paid">
                    Mark paid
                </Button>
            </>
        );
    })();

    const threadUrl = gmailThreadUrl(data?.thread_id || inv?.source_thread_id);
    const fact = inv ? headerFactLine(inv) : null;
    const partial = inv && !hasPendingPaymentClaim(inv)
        && Number(inv.paid_amount || 0) > 0.005
        && Number(inv.balance_remaining ?? inv.amount ?? 0) > 0.005;
    const loadingThread = open && invoiceId && !data && !err;

    return (
        <SheetPrimitive.Root
            open={open}
            onOpenChange={(next) => {
                if (!next) requestModalClose();
            }}
        >
            <SheetPrimitive.Portal>
                <SheetPrimitive.Overlay
                    className={cn(
                        "fixed inset-0 z-50 bg-[rgba(0,0,0,0.45)]",
                        "data-[state=open]:animate-in data-[state=closed]:animate-out",
                        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                    )}
                />
                <div className="fixed inset-0 z-50 flex items-stretch justify-center sm:items-center sm:p-4 pointer-events-none">
                    <SheetPrimitive.Content
                        className={cn(
                            "pointer-events-auto relative z-50 bg-background shadow-lg outline-none",
                            "flex flex-col gap-0 p-0 overflow-hidden",
                            "w-full h-full rounded-none border-0",
                            "sm:w-[min(840px,92vw)] sm:min-w-[min(720px,92vw)] sm:max-w-[840px]",
                            "sm:h-fit sm:max-h-[90vh] sm:rounded-2xl sm:border sm:border-border",
                            "duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out",
                            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
                        )}
                        data-testid="invoice-detail-drawer"
                        aria-describedby={undefined}
                    >
                        <SheetPrimitive.Title className="sr-only">
                            Invoice {inv ? invoiceSubject(inv) : invoiceId || ""}
                        </SheetPrimitive.Title>
                        <button
                            type="button"
                            className="absolute right-4 top-4 z-10 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                            data-testid="invoice-detail-close"
                            onClick={requestModalClose}
                        >
                            <X className="h-4 w-4" />
                            <span className="sr-only">Close</span>
                        </button>

                        {/* Pinned header */}
                        <div className="flex-shrink-0 border-b border-border px-6 pt-6 pb-4 pr-12 space-y-3" data-testid="invoice-detail-header">
                            {err && !inv ? (
                                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{err}</div>
                            ) : null}
                            {!inv && loadingThread ? <HeaderSkeleton /> : null}
                            {inv ? (
                                <>
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <div className="text-xs text-muted-foreground">
                                                <Link
                                                    to={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
                                                    className="hover:underline"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    {inv.counterparty_name || inv.counterparty_email || "Client"}
                                                </Link>
                                                {inv.counterparty_name && inv.counterparty_email ? (
                                                    <span className="font-mono"> · {inv.counterparty_email}</span>
                                                ) : null}
                                            </div>
                                            <h1 className="font-heading font-bold text-xl md:text-2xl tracking-tight mt-1 break-words whitespace-normal">
                                                {invoiceSubject(inv)}
                                            </h1>
                                            {inv.invoice_ref && !isJunkInvoiceRef(inv.invoice_ref) && inv.invoice_ref !== inv.source_subject ? (
                                                <div className="text-xs font-mono text-muted-foreground mt-1">{inv.invoice_ref}</div>
                                            ) : null}
                                        </div>
                                        <div className="text-right flex-shrink-0">
                                            <div className="stat-number font-bold text-2xl tabular-nums">
                                                {formatMoney(inv.amount, inv.currency || "USD")}
                                            </div>
                                            {partial ? (
                                                <div className="text-xs text-green-700 mt-0.5">
                                                    {formatMoney(inv.paid_amount, inv.currency || "USD")} paid ·{" "}
                                                    {formatMoney(inv.balance_remaining, inv.currency || "USD")} left
                                                </div>
                                            ) : null}
                                        </div>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <StatusChip inv={inv} />
                                        {fact ? <span className="text-sm text-muted-foreground">{fact}</span> : null}
                                    </div>
                                    {actions ? (
                                        <div className="flex flex-wrap gap-2 pt-1" data-testid="invoice-detail-actions">
                                            {actions}
                                        </div>
                                    ) : null}
                                </>
                            ) : null}
                        </div>

                        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                            {/* Inline composer — expands/collapses above conversation */}
                            {composePresent && inv ? (
                                <div
                                    className={cn(
                                        "grid transition-[grid-template-rows] duration-300 ease-out",
                                        composeExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                                    )}
                                    data-testid="invoice-inline-composer"
                                >
                                    <div className="min-h-0 overflow-hidden">
                                        <div
                                            className={cn(
                                                "border-b border-border bg-background px-6 py-4",
                                                "sm:max-h-[50vh] sm:overflow-y-auto",
                                                "transition-opacity duration-300 ease-out",
                                                composeExpanded ? "opacity-100" : "opacity-0",
                                            )}
                                        >
                                            <ChaseComposer
                                                invoice={inv}
                                                active={composePresent && composeExpanded}
                                                initialIntent={composeIntent}
                                                showBack
                                                onDirtyChange={(d) => { composeDirtyRef.current = d; }}
                                                onCancel={() => { tryCollapseComposer(); }}
                                                onSent={async () => {
                                                    collapseComposer();
                                                    refresh();
                                                    await onChanged?.();
                                                }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            ) : null}

                            {/* Conversation — hidden on mobile while composing */}
                            <div
                                className={cn(
                                    "min-h-0 overflow-y-auto px-6 py-4",
                                    composePresent && composeExpanded
                                        ? "hidden sm:block sm:flex-1 sm:max-h-[40vh]"
                                        : "flex-1",
                                )}
                                data-testid="invoice-conversation-scroll"
                            >
                                {err && inv ? (
                                    <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{err}</div>
                                ) : null}

                                <section className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="invoice-conversation">
                                    <div className="px-5 py-3 border-b border-border flex items-center justify-between sticky top-0 bg-card z-[1]">
                                        <h2 className="text-sm font-semibold">Conversation</h2>
                                        {threadUrl ? (
                                            <a
                                                href={threadUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                                            >
                                                Open in Gmail <ExternalLink className="w-3 h-3" />
                                            </a>
                                        ) : null}
                                    </div>

                                    {loadingThread ? (
                                        <div className="px-5 py-10 space-y-4">
                                            <Skeleton className="h-3 w-1/3" />
                                            <Skeleton className="h-16 w-full" />
                                            <Skeleton className="h-3 w-1/4" />
                                            <Skeleton className="h-20 w-full" />
                                        </div>
                                    ) : null}

                                    {data?.gmail_error ? (
                                        <div className="px-5 py-4 text-sm text-amber-800 bg-amber-50 border-b border-amber-100">
                                            {data.gmail_error}. Showing what we know from tracking.
                                        </div>
                                    ) : null}

                                    {data && !data.messages?.length ? (
                                        <div className="px-5 py-10 text-sm text-muted-foreground text-center">
                                            No messages loaded yet.
                                            {inv?.source_subject ? ` Subject: ${inv.source_subject}` : ""}
                                        </div>
                                    ) : null}

                                    {data?.messages?.length ? (
                                        <ul className="divide-y divide-border" data-testid="conversation-messages">
                                            {[...data.messages].reverse().map((m, idx, msgs) => {
                                                const prev = msgs[idx - 1];
                                                const day = calendarDayKey(m.date);
                                                const prevDay = prev ? calendarDayKey(prev.date) : null;
                                                const showDay = Boolean(day && day !== prevDay);
                                                const isYou = m.direction === "you";
                                                const sender = isYou ? "You" : clientSenderLabel(m, inv);
                                                const showSubject = subjectsDiffer(m.subject, inv?.source_subject);
                                                return (
                                                    <li key={m.id} data-testid="conversation-message">
                                                        {showDay ? (
                                                            <div
                                                                className="flex items-center justify-center gap-3 px-5 py-3 bg-muted/20"
                                                                data-testid="conversation-day-separator"
                                                            >
                                                                <span className="h-px flex-1 bg-border" />
                                                                <span className="text-[11px] font-medium text-muted-foreground tabular-nums whitespace-nowrap">
                                                                    {formatDaySeparator(m.date)}
                                                                </span>
                                                                <span className="h-px flex-1 bg-border" />
                                                            </div>
                                                        ) : null}
                                                        <div
                                                            className={cn(
                                                                "px-5 py-4 border-l-[3px]",
                                                                isYou
                                                                    ? "bg-primary/[0.04] border-l-primary"
                                                                    : "bg-white border-l-border",
                                                            )}
                                                        >
                                                            <div className="flex items-start justify-between gap-3">
                                                                <div className="flex items-center gap-2.5 min-w-0">
                                                                    <MessageAvatar isYou={isYou} label={sender} />
                                                                    <div className="min-w-0">
                                                                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                                                                            <span className="text-sm font-semibold truncate">{sender}</span>
                                                                            {m.state_markers?.length ? (
                                                                                <span className="inline-flex flex-wrap gap-1">
                                                                                    {m.state_markers.map((label) => (
                                                                                        <span
                                                                                            key={label}
                                                                                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border border-border bg-background text-muted-foreground"
                                                                                        >
                                                                                            → {label}
                                                                                        </span>
                                                                                    ))}
                                                                                </span>
                                                                            ) : null}
                                                                        </div>
                                                                        {showSubject ? (
                                                                            <div className="text-[11px] text-muted-foreground mt-0.5 truncate">{m.subject}</div>
                                                                        ) : null}
                                                                    </div>
                                                                </div>
                                                                <div className="text-[11px] font-mono text-muted-foreground tabular-nums flex-shrink-0">
                                                                    {formatMsgTime(m.date)}
                                                                </div>
                                                            </div>
                                                            <pre className="mt-3 text-sm text-foreground whitespace-pre-wrap break-words font-sans leading-relaxed" data-testid="conversation-body">
                                                                {emailBodyToText(m.body) || "(empty)"}
                                                            </pre>
                                                            {m.attachment_names?.length ? (
                                                                <div className="mt-2 text-[11px] text-muted-foreground">
                                                                    Attachments: {m.attachment_names.join(", ")}
                                                                </div>
                                                            ) : null}
                                                        </div>
                                                    </li>
                                                );
                                            })}
                                        </ul>
                                    ) : null}

                                    {data?.client_ever_replied === false && data.messages?.length > 0 ? (
                                        <div className="px-5 py-3 border-t border-border text-xs text-muted-foreground bg-muted/30">
                                            Client has never responded on this thread.
                                        </div>
                                    ) : null}
                                </section>
                            </div>
                        </div>
                    </SheetPrimitive.Content>
                </div>
            </SheetPrimitive.Portal>
        </SheetPrimitive.Root>
    );
}
