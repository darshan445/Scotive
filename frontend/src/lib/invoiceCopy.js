import { formatDate } from "@/components/LedgerCard";

/** User-facing status labels — internal key `overdue` displays as Past due. */
export const STATUS_LABELS = {
    invoiced: "Invoiced",
    overdue: "Past due",
    promised: "Promised",
    promise_broken: "Promise broken",
    broken_promise: "Promise broken",
    disputed: "Disputed",
    partially_paid: "Partially paid",
    paid_unconfirmed: "Says paid",
    paid: "Paid",
    written_off: "Written off",
    stale: "Gone quiet",
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
    const status = inv?.status;
    const claimed = inv?.disputed_claim_amount;
    const hasClaim = claimed != null && Number(claimed) > 0;
    const pendingPay = hasPendingPaymentClaim(inv);
    const confirmedPartial = !pendingPay && (
        status === "partially_paid"
        || (Number(inv?.paid_amount || 0) > 0.005
            && Number(inv?.balance_remaining ?? inv?.amount ?? 0) > 0.005)
    );

    if (pendingPay && (status === "disputed" || hasClaim)) {
        return "Disputed · says paid";
    }
    if (pendingPay || status === "paid_unconfirmed") {
        return "Says paid";
    }
    if ((status === "disputed" || hasClaim) && confirmedPartial) {
        return "Disputed · partially paid";
    }
    if (status === "partially_paid" && hasClaim) {
        return "Disputed · partially paid";
    }
    if (status === "disputed" && hasClaim) {
        return statusLabel(status);
    }
    return statusLabel(status);
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
    const status = invoiceStatusDisplay(inv);
    if (inv?.status === "stale") return `${status} · No activity 120+ days`;
    if (inv?.promise_date) return `${status} · ${formatDate(inv.promise_date)}`;
    if (inv?.due_date) {
        const due = formatDate(inv.due_date);
        if (inv.status === "overdue") {
            const late = pastDueDaysLabel(inv.due_date);
            return late ? `${status} · ${due} (${late})` : `${status} · ${due}`;
        }
        return `${status} · Due ${due}`;
    }
    const sent = inv?.source_date || inv?.created_at;
    return sent ? `${status} · ${formatDate(sent)}` : status;
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
