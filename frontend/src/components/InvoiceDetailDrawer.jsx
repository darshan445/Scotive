"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ExternalLink, X } from "lucide-react";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { ChaseComposer, confirmDiscardComposer } from "@/components/ChaseComposer";
import { CheckBackSelect, SnoozeControl } from "@/components/WaitUntilControl";
import { stopInvoiceChase } from "@/components/InvoiceOverflowMenu";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, extractError, unwrapData } from "@/lib/api";
import { formatMoney } from "@/components/LedgerCard";
import { invoiceSubject } from "@/lib/invoiceCopy";
import {
    cadenceLine,
    dueMeta,
    invoiceNumber,
    invoiceWithWaitSuggestion,
    isApprovalDraft,
    isNeedsYouInvoice,
    isPaidInvoice,
    latestActivity,
    plusBusinessDays,
    remainingLabel,
} from "@/lib/chase";
import { gmailThreadUrl } from "@/lib/invoiceTimeline";
import { cn } from "@/lib/utils";

function formatMsgTime(iso) {
    if (!iso) return "";
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: "short", day: "numeric",
            hour: "numeric", minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

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
            .replace(/<[^>]+>/g, "");
        const ta = typeof document !== "undefined" ? document.createElement("textarea") : null;
        if (ta) {
            ta.innerHTML = text;
            text = ta.value;
        }
    }
    text = text
        .replace(/&nbsp;/g, " ")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&amp;/g, "&");
    const cut = [/\nOn .+wrote:\s*\n/i, /\n-{2,}\s*Original Message\s*-{2,}/i, /\nFrom:\s.+\nSent:\s/i];
    for (const pat of cut) {
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

function conversationMessages(data) {
    const home = Array.isArray(data?.threads)
        ? data.threads.find((thread) => thread.is_primary) || data.threads[0]
        : null;
    const raw = data?.messages?.length ? data.messages : (home?.messages || []);
    return [...raw].sort((a, b) => new Date(b.date) - new Date(a.date));
}

function latestInbound(messages = [], inv) {
    const inbound = messages.find((m) => m.direction !== "you");
    if (inbound) {
        return {
            from: inbound.from || inv?.counterparty_email,
            date: inbound.date,
            body: emailBodyToText(inbound.body),
        };
    }
    const quote = inv?.reason_quote || inv?.last_human_inbound_quote;
    if (!quote && !inv?.last_human_inbound_at) return null;
    return {
        from: inv?.counterparty_email,
        date: inv?.last_human_inbound_at,
        body: quote || "",
    };
}

export function InvoiceDetailDrawer({ invoiceId, preview = null, open, onClose, onChanged }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");
    const [threadOpen, setThreadOpen] = useState(false);
    const [followUpDate, setFollowUpDate] = useState(plusBusinessDays(3));
    const composeDirtyRef = useRef(false);

    const refresh = useCallback(() => {
        if (!invoiceId) return;
        setErr("");
        api.get(`/v1/invoices/${invoiceId}/conversation`)
            .then(({ data: res }) => setData(unwrapData(res)))
            .catch((e) => setErr(extractError(e)));
    }, [invoiceId]);

    useEffect(() => {
        if (!open || !invoiceId) return;
        setData(null);
        setErr("");
        setThreadOpen(false);
        composeDirtyRef.current = false;
        refresh();
    }, [open, invoiceId, refresh]);

    const inv = data?.invoice || (preview && preview._id === invoiceId ? preview : null);

    useEffect(() => {
        if (!inv) return;
        const suggested = invoiceWithWaitSuggestion(inv).suggested_wait_date;
        setFollowUpDate(suggested || plusBusinessDays(3));
    }, [inv?._id, inv?.suggested_wait_date, inv?.reason_quote]);

    function requestClose() {
        if (!confirmDiscardComposer(composeDirtyRef.current)) return;
        onClose?.();
    }

    async function afterAction() {
        composeDirtyRef.current = false;
        refresh();
        await onChanged?.();
        onClose?.();
    }

    const history = conversationMessages(data);
    const inbound = latestInbound(history, inv);
    const due = inv ? dueMeta(inv) : null;
    const activity = inv ? latestActivity(inv) : null;
    const left = remainingLabel(inv);
    const threadUrl = gmailThreadUrl(data?.thread_id || inv?.source_thread_id);
    const needsYou = inv && isNeedsYouInvoice(inv);
    const firm = inv && isApprovalDraft(inv);
    const conversation = needsYou && !firm;
    const loading = open && invoiceId && !data && !err && !inv;

    return (
        <SheetPrimitive.Root
            open={open}
            onOpenChange={(next) => {
                if (!next) requestClose();
            }}
        >
            <SheetPrimitive.Portal>
                <SheetPrimitive.Overlay
                    className={cn(
                        "fixed inset-0 z-50 bg-black/40",
                        "data-[state=open]:animate-in data-[state=closed]:animate-out",
                        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                    )}
                />
                <SheetPrimitive.Content
                    className={cn(
                        "fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col bg-background shadow-2xl outline-none",
                        "sm:w-[min(520px,92vw)] sm:border-l sm:border-border",
                        "data-[state=open]:animate-in data-[state=closed]:animate-out",
                        "data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
                        "duration-200",
                    )}
                    data-testid="invoice-detail-drawer"
                    aria-describedby={undefined}
                >
                    <SheetPrimitive.Title className="sr-only">
                        Review {inv ? invoiceSubject(inv) : invoiceId || ""}
                    </SheetPrimitive.Title>

                    <header className="flex-shrink-0 border-b border-border px-5 pt-5 pb-4 pr-12" data-testid="invoice-detail-header">
                        <button
                            type="button"
                            className="absolute right-4 top-4 rounded-sm text-muted-foreground hover:text-foreground"
                            data-testid="invoice-detail-close"
                            onClick={requestClose}
                        >
                            <X className="h-4 w-4" />
                            <span className="sr-only">Close</span>
                        </button>
                        {err && !inv ? (
                            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>
                        ) : null}
                        {loading ? (
                            <div className="space-y-2" data-testid="invoice-detail-skeleton">
                                <Skeleton className="h-4 w-40" />
                                <Skeleton className="h-6 w-2/3" />
                            </div>
                        ) : null}
                        {inv ? (
                            <>
                                <Link
                                    href={`/clients/${encodeURIComponent(inv.counterparty_email || "")}`}
                                    className="text-base font-semibold text-foreground hover:underline"
                                >
                                    {inv.counterparty_name || inv.counterparty_email || "Client"}
                                </Link>
                                <div className="mt-1 flex items-baseline justify-between gap-3 text-sm">
                                    <div className="tabular-nums text-muted-foreground">
                                        Invoice {invoiceNumber(inv)}
                                        <span className="mx-1.5 text-border">·</span>
                                        <span className="font-medium text-foreground">{formatMoney(inv.amount, inv.currency || "USD")}</span>
                                        {left ? <span className="ml-1.5 text-xs text-emerald-700">{left}</span> : null}
                                    </div>
                                    {due ? (
                                        <div className={`text-right text-xs ${due.tone === "rose" ? "text-rose-600" : due.tone === "amber" ? "text-amber-700" : "text-muted-foreground"}`}>
                                            Due {due.due}{due.relative ? ` (${due.relative})` : ""}
                                        </div>
                                    ) : null}
                                </div>
                            </>
                        ) : null}
                    </header>

                    <div className="flex-1 min-h-0 overflow-y-auto px-5 py-5 space-y-5">
                        {inv && isPaidInvoice(inv) ? (
                            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                                {inv.chase_result || "Collected. Chase is closed."}
                            </div>
                        ) : null}

                        {inv && !needsYou && !isPaidInvoice(inv) ? (
                            <div className="rounded-lg border border-border bg-muted/40 px-4 py-3">
                                <div className="text-sm font-medium">{cadenceLine(inv).title}</div>
                                {cadenceLine(inv).detail ? (
                                    <div className="mt-0.5 text-xs text-muted-foreground">{cadenceLine(inv).detail}</div>
                                ) : null}
                            </div>
                        ) : null}

                        {needsYou && !isPaidInvoice(inv) ? (
                            <>
                                <section>
                                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        Latest thread context
                                    </div>
                                    <div className="rounded-lg border border-border bg-muted/30 px-4 py-3" data-testid="latest-inbound">
                                        {activity?.title ? (
                                            <div className="text-sm font-medium">{activity.title}</div>
                                        ) : null}
                                        {conversation && inbound?.body ? (
                                            <blockquote className="mt-2 text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
                                                {inbound.body}
                                            </blockquote>
                                        ) : activity?.detail ? (
                                            <div className="mt-0.5 text-sm text-muted-foreground">{activity.detail}</div>
                                        ) : null}
                                    </div>
                                </section>

                                <section data-testid="invoice-inline-composer">
                                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        Email to send
                                    </div>
                                    <ChaseComposer
                                        invoice={inv}
                                        active={open}
                                        embedded
                                        showBack={false}
                                        autoDraft={false}
                                        defaultSubject={data?.threads?.[0]?.subject || inv.pending_subject || (inv.invoice_ref ? `Re: Invoice ${inv.invoice_ref}` : "")}
                                        initialDraft={firm && inv.pending_body ? {
                                            subject: inv.pending_subject,
                                            body: inv.pending_body,
                                            is_reply: false,
                                        } : null}
                                        waitUntil={followUpDate}
                                        sendLabel={firm ? "Approve & send from Gmail" : "Send reply"}
                                        onDirtyChange={(d) => { composeDirtyRef.current = d; }}
                                        onCancel={requestClose}
                                        onSent={afterAction}
                                        beforeSend={<CheckBackSelect value={followUpDate} onChange={setFollowUpDate} />}
                                    />
                                </section>

                                <div className="border-t border-border mt-6 pt-5">
                                    <div className="mb-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        Or don’t send an email
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <SnoozeControl invoice={inv} label="Snooze instead" onChanged={afterAction} />
                                        <Button
                                            variant="ghost"
                                            className="text-rose-700 hover:text-rose-800"
                                            onClick={() => {
                                                if (typeof window !== "undefined" && !window.confirm(`Permanently stop reminders for Invoice ${invoiceNumber(inv)}?`)) return;
                                                stopInvoiceChase(inv._id, { onChanged: afterAction });
                                            }}
                                            data-testid="drawer-stop-chasing"
                                        >
                                            Stop chasing
                                        </Button>
                                    </div>
                                </div>
                            </>
                        ) : null}

                        {history.length || threadUrl ? (
                            <section className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                {history.length ? (
                                    <button
                                        type="button"
                                        className="text-xs font-medium text-muted-foreground hover:text-foreground"
                                        onClick={() => setThreadOpen((v) => !v)}
                                    >
                                        {threadOpen ? "Hide thread" : `Thread (${history.length})`}
                                    </button>
                                ) : null}
                                {threadUrl ? (
                                    <a
                                        href={threadUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                                    >
                                        Open in Gmail <ExternalLink className="w-3 h-3" />
                                    </a>
                                ) : null}
                                {threadOpen ? (
                                    <ul className="mt-3 w-full space-y-3" data-testid="conversation-messages">
                                        {history.map((m) => (
                                            <li key={m.id} className="rounded-lg border border-border px-3 py-2.5" data-testid="conversation-message">
                                                <div className="flex justify-between gap-2 text-[11px] text-muted-foreground">
                                                    <span className="font-medium text-foreground">{m.direction === "you" ? "You" : (inv?.counterparty_name || "Client")}</span>
                                                    <span className="tabular-nums">{formatMsgTime(m.date)}</span>
                                                </div>
                                                <pre className="mt-1.5 text-sm whitespace-pre-wrap font-sans" data-testid="conversation-body">
                                                    {emailBodyToText(m.body) || "(empty)"}
                                                </pre>
                                            </li>
                                        ))}
                                    </ul>
                                ) : null}
                            </section>
                        ) : null}
                    </div>
                </SheetPrimitive.Content>
            </SheetPrimitive.Portal>
        </SheetPrimitive.Root>
    );
}
