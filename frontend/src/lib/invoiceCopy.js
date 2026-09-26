import { formatDate } from "@/components/LedgerCard";
import { chaseReason, invoiceBucket, BUCKET_LABELS } from "@/lib/chase";

/** User-facing status labels — chase buckets, plus leftover keys. */
export const STATUS_LABELS = {
    needs_you: "Needs you",
    watching: "Watching",
    auto_reminders: "Auto reminders",
    paid: "Paid",
    stopped: "Stopped",
    invoiced: "Watching",
    overdue: "Watching",
    promised: "Watching",
    promise_broken: "Needs you",
    broken_promise: "Needs you",
    disputed: "Needs you",
    partially_paid: "Watching",
    paid_unconfirmed: "Needs you",
    written_off: "Paid",
    stale: "Watching",
    unmatched: "Auto reminders",
};

export function statusLabel(status) {
    return STATUS_LABELS[status] || (status || "invoiced").replace(/_/g, " ");
}

/** True while a client payment claim still needs Received / Not yet. */
export function hasPendingPaymentClaim(inv) {
    if (!inv) return false;
    if (inv.payment_claim_pending) return true;
    return inv.status === "paid_unconfirmed";
}

export function paymentClaimAmount(inv) {
    const n = Number(inv?.payment_claim_amount);
    return Number.isFinite(n) && n > 0.005 ? n : null;
}

function formatCurrency(amount, currency = "USD") {
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(amount || 0));
    } catch {
        return `$${Number(amount || 0).toFixed(2)}`;
    }
}

/** Combined status when an invoice is both disputed and partially paid / says paid. */
export function invoiceStatusDisplay(inv) {
    if (inv?.status === "needs_you" || inv?.chase_status === "needs_you") return "Needs you";
    if (inv?.status === "stopped" || inv?.chase_status === "stopped") return "Stopped";
    if (inv?.status === "paid" || inv?.books_status === "paid") return "Paid";
    if (inv?.books_status === "voided") return "Paid";
    return "Watching";
}

export function pastDueQuestion(inv) {
    if (!inv.due_date) return null;
    return `Was due ${formatDate(inv.due_date)} — has it arrived?`;
}

/** Dashboard-only factual context — dates/ledger math, never message quotes. */
export function factualDigestLine(inv, sectionKey) {
    const cur = inv?.currency || "USD";
    const payClaim = paymentClaimAmount(inv);
    const disputeClaim = inv?.disputed_claim_amount;

    if (sectionKey === "due_overdue") {
        return pastDueQuestion(inv);
    }
    if (sectionKey === "broken_promises") {
        return inv.promise_date
            ? `Promised ${formatDate(inv.promise_date)} — didn't arrive`
            : "Promise date passed — didn't arrive";
    }
    if (sectionKey === "confirm_prompts") {
        const parts = [];
        parts.push(`You billed ${formatCurrency(inv.amount, cur)}`);
        if (disputeClaim != null && Number(disputeClaim) > 0) {
            parts.push(`client claims ${formatCurrency(disputeClaim, cur)}`);
        }
        if (payClaim != null) {
            parts.push(`says ${formatCurrency(payClaim, cur)} sent`);
        }
        if (parts.length > 1 || payClaim != null) {
            return `${parts.join(" · ")} — did you receive it?`;
        }
        return "Says paid — did you receive it?";
    }
    if (sectionKey === "needs_reply") {
        if (inv.status === "promised" && inv.promise_date) {
            return `Promise date ${formatDate(inv.promise_date)}`;
        }
        const parts = [`You billed ${formatCurrency(inv.amount, cur)}`];
        if (disputeClaim != null && Number(disputeClaim) > 0) {
            parts.push(`client claims ${formatCurrency(disputeClaim, cur)}`);
        }
        if (payClaim != null) {
            parts.push(`says ${formatCurrency(payClaim, cur)} sent`);
        }
        if (parts.length > 1 || inv?.status === "disputed") {
            return parts.join(" · ");
        }
        return null;
    }
    if (sectionKey === "stale_prompts") {
        return "No email activity in 120+ days";
    }
    return null;
}

/** Full original subject — primary invoice identifier in the UI. */
export function invoiceSubject(inv) {
    const subject = (inv?.source_subject || "").trim();
    if (subject) return subject;
    return invoiceDisplayRef(inv);
}

export function watchingSubtitle(inv) {
    if (inv.ladder_exhausted) {
        return "Still open — no further auto-drafts";
    }
    if (inv.watching_for_reply) {
        return "Awaiting client reply after your follow-up";
    }
    return null;
}

/** When the user last sent a follow-up chase (app or inferred from sent mail). */
export function formatLastFollowUp(iso) {
    const raw = iso || null;
    if (!raw) return null;
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return null;

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfThatDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const dayDiff = Math.round((startOfToday - startOfThatDay) / (1000 * 60 * 60 * 24));

    if (dayDiff === 0) {
        const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
        return `Followed up today, ${time}`;
    }
    if (dayDiff === 1) return "Followed up yesterday";
    if (dayDiff > 1) return `Followed up ${dayDiff} days ago`;
    return null;
}

export function lastFollowUpSentAt(inv) {
    return inv?.last_followup_sent_at || inv?.last_chase_at || null;
}

const JUNK_INVOICE_REFS = new Set([
    "FOR", "THE", "A", "AN", "TO", "OF", "AND", "OR", "YOUR", "MY", "OUR", "THIS", "THAT",
]);

/** True when stored ref is a subject fragment, not a real invoice number. */
export function isJunkInvoiceRef(ref) {
    if (!ref || !String(ref).trim()) return true;
    const v = String(ref).trim().toUpperCase().replace(/\s+/g, "");
    if (JUNK_INVOICE_REFS.has(v)) return true;
    if (/^[A-Z]+$/.test(v) && v.length <= 5 && !v.startsWith("INV")) return true;
    return false;
}

/** Prefer a real invoice ref; fall back to email subject for descriptive invoices. */
export function invoiceDisplayRef(inv) {
    const ref = (inv?.invoice_ref || "").trim();
    const subject = (inv?.source_subject || "").trim();
    if (ref && !isJunkInvoiceRef(ref)) return ref;
    return subject || "Invoice";
}

/** Status + key date line for invoice cards (promise/due/sent). */
export function invoiceStatusDateLine(inv) {
    const bucket = invoiceBucket(inv);
    const reason = chaseReason(inv);
    const due = inv?.due_date ? `Due ${formatDate(inv.due_date)}` : null;
    if (reason.title && reason.title !== BUCKET_LABELS[bucket]) {
        return due ? `${reason.title} · ${due}` : reason.title;
    }
    return due ? `${BUCKET_LABELS[bucket]} · ${due}` : BUCKET_LABELS[bucket];
}

export function pastDueDaysLabel(dueDateIso) {
    if (!dueDateIso) return null;
    const due = new Date(dueDateIso);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    due.setHours(0, 0, 0, 0);
    const diff = Math.round((today - due) / (1000 * 60 * 60 * 24));
    if (diff <= 0) return null;
    return `${diff} day${diff === 1 ? "" : "s"} past due`;
}
