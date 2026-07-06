import { formatMoney } from "@/components/LedgerCard";

/** Gmail thread deep link (opens in user's default account). */
export function gmailThreadUrl(threadId) {
    if (!threadId) return null;
    return `https://mail.google.com/mail/u/0/#inbox/${encodeURIComponent(threadId)}`;
}

export function formatTimelineDay(iso) {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        const now = new Date();
        const opts = { month: "short", day: "numeric" };
        if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
        return d.toLocaleDateString(undefined, opts);
    } catch {
        return iso;
    }
}

function truncateQuote(text, max = 80) {
    const t = String(text || "").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, max - 1)}…`;
}

/** One readable timeline row — returns { day, body, sub, threadId }. */
export function formatTimelineEntry(ev, invoice) {
    const day = formatTimelineDay(ev.date);
    const cur = invoice?.currency || ev.currency || "USD";
    const kind = ev.kind || "note";

    if (kind === "invoice_sent") {
        const amt = formatMoney(ev.amount ?? invoice?.amount, cur);
        const due = ev.due_date || invoice?.due_date;
        const dueBit = due ? `, due ${formatTimelineDay(due)}` : "";
        return { day, body: `You sent invoice — ${amt}${dueBit}`, threadId: ev.thread_id };
    }

    if (kind === "payment_promise") {
        const quote = ev.quote ? truncateQuote(ev.quote) : "payment promised";
        const promise = ev.promise_date || invoice?.promise_date;
        const tail = promise ? ` → promise set for ${formatTimelineDay(promise)}` : "";
        return {
            day,
            body: `Client: "${quote}"${tail}`,
            threadId: ev.thread_id,
        };
    }

    if (kind === "payment_claim") {
        const quote = ev.quote ? truncateQuote(ev.quote) : "payment sent";
        return { day, body: `Client: "${quote}"`, threadId: ev.thread_id };
    }

    if (kind === "dispute") {
        const quote = ev.quote ? truncateQuote(ev.quote) : "disputed the invoice";
        return { day, body: `Client: "${quote}"`, threadId: ev.thread_id };
    }

    if (kind === "partial_payment") {
        const amt = ev.amount != null ? formatMoney(ev.amount, cur) : "a partial payment";
        const quote = ev.quote ? ` — "${truncateQuote(ev.quote)}"` : "";
        return { day, body: `Client reported ${amt}${quote}`, threadId: ev.thread_id };
    }

    if (kind === "receipt") {
        const amt = ev.amount != null ? formatMoney(ev.amount, cur) : "Payment";
        const who = ev.payer_name ? ` from ${ev.payer_name}` : "";
        return { day, body: `${amt} received${who}`, threadId: ev.thread_id };
    }

    if (kind === "mark_paid") {
        return { day, body: "You marked this invoice paid", threadId: null };
    }

    if (kind === "manual_add") {
        const amt = formatMoney(invoice?.amount, cur);
        return { day, body: `You added invoice manually — ${amt}`, threadId: null };
    }

    if (kind === "went_stale") {
        return { day, body: "No activity for 120+ days", threadId: null };
    }

    const label = kind.replace(/_/g, " ");
    const quote = ev.quote ? ` — "${truncateQuote(ev.quote)}"` : "";
    return { day, body: `${label}${quote}`, threadId: ev.thread_id };
}
