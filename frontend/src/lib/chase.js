function formatDate(iso) {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    } catch {
        return iso;
    }
}

function formatMoney(n, currency = "USD") {
    if (n == null) return "—";
    try {
        return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(n));
    } catch {
        return `$${Number(n).toFixed(2)}`;
    }
}

export const BUCKETS = {
    needs_you: "needs_you",
    watching: "watching",
    auto_reminders: "auto_reminders",
    paid: "paid",
    stopped: "stopped",
};

export const BUCKET_LABELS = {
    needs_you: "Needs you",
    watching: "Watching",
    auto_reminders: "Auto reminders",
    paid: "Paid",
    stopped: "Stopped",
};

const APPROVAL_STEPS = new Set(["firm_plus_7", "urgent_plus_14", "broken_promise"]);

function lastFriendlyOffset(inv) {
    const offset = Number(inv?.last_friendly_offset);
    return Number.isFinite(offset) ? offset : 7;
}

export function isApprovalDraft(inv) {
    if (!inv) return false;
    if (inv.reason === "firm_ready" || inv.reason === "final_ready") return true;
    return inv.pending_outbox_status === "draft" && APPROVAL_STEPS.has(inv.pending_step);
}

export function invoiceBucket(inv) {
    if (!inv) return BUCKETS.watching;
    if (inv.status === "paid" || inv.books_status === "paid" || inv.books_status === "voided") return BUCKETS.paid;
    if (inv.status === "stopped" || inv.chase_status === "stopped") return BUCKETS.stopped;
    if (
        inv.status === "needs_you"
        || inv.chase_status === "needs_you"
        || inv.reason === "wait_date_passed"
        || isApprovalDraft(inv)
        || (Boolean(inv.last_human_inbound_at || inv.reason === "replied") && !inv.expected_pay_date)
        || (
            Number.isFinite(Number(inv.days_late))
            && Number(inv.days_late) > lastFriendlyOffset(inv)
            && !inv.last_human_inbound_at
            && !hasFutureFollowUp(inv)
        )
    ) return BUCKETS.needs_you;
    if (hasFutureFollowUp(inv)) return BUCKETS.watching;
    return BUCKETS.auto_reminders;
}

export function isPaidInvoice(inv) {
    return invoiceBucket(inv) === BUCKETS.paid;
}

export function isStoppedInvoice(inv) {
    return invoiceBucket(inv) === BUCKETS.stopped;
}

export function isNeedsYouInvoice(inv) {
    return invoiceBucket(inv) === BUCKETS.needs_you;
}

export function isWatchingInvoice(inv) {
    return invoiceBucket(inv) === BUCKETS.watching;
}

export function isAutoReminderInvoice(inv) {
    return invoiceBucket(inv) === BUCKETS.auto_reminders;
}

export function hasFutureFollowUp(inv) {
    if (!inv?.expected_pay_date) return false;
    const day = new Date(inv.expected_pay_date);
    if (Number.isNaN(day.getTime())) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    day.setHours(0, 0, 0, 0);
    return day >= today;
}

export function isSleepingInvoice(inv) {
    if (!inv) return false;
    if (inv.status === "paid" || inv.books_status === "paid" || inv.books_status === "voided") return false;
    if (inv.status === "stopped" || inv.chase_status === "stopped") return false;
    return hasFutureFollowUp(inv);
}

export function relativeAgo(iso) {
    if (!iso) return null;
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return null;
    const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days === 1) return "yesterday";
    if (days < 21) return `${days} days ago`;
    return formatDate(iso);
}

/** Compact table timing: 11h ago, 5d ago. */
export function relativeAgoCompact(iso) {
    if (!iso) return null;
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return null;
    const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
}

export function clientShortName(inv) {
    const name = String(inv?.counterparty_name || "").trim();
    if (name) return name.split(/\s+/)[0];
    const email = String(inv?.counterparty_email || "").trim();
    if (email.includes("@")) return email.split("@")[0];
    return "They";
}

export function shortWaitDate(iso) {
    if (!iso) return null;
    try {
        return new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    } catch {
        return iso;
    }
}

export function chaseReason(inv) {
    if (!inv) return { title: "", detail: null };
    const bucket = invoiceBucket(inv);
    const wait = shortWaitDate(inv.expected_pay_date);
    const replied = relativeAgo(inv.last_human_inbound_at);

    if (bucket === BUCKETS.paid) {
        return {
            title: inv.books_status === "voided" ? "Voided in the books" : "Paid in the books",
            detail: inv.paid_at ? formatDate(inv.paid_at) : null,
        };
    }
    if (bucket === BUCKETS.stopped) {
        return { title: "You stopped chasing", detail: "No automatic reminders. You can still send a draft." };
    }
    if (inv.reason === "wait_date_passed" || (inv.expected_pay_date && !isSleepingInvoice(inv) && bucket === BUCKETS.needs_you)) {
        return {
            title: wait ? `Follow-up date reached (${wait})` : "Follow-up date reached",
            detail: "Still unpaid in QuickBooks.",
        };
    }
    if (inv.reason === "replied" || (bucket === BUCKETS.needs_you && inv.last_human_inbound_at)) {
        return {
            title: replied ? `They wrote back ${replied}` : "They wrote back",
            detail: "The automated ladder is off. Review, then pick a date to follow up if still unpaid.",
        };
    }
    if (bucket === BUCKETS.needs_you) {
        return {
            title: "Needs you",
            detail: "Review, then pick a date to follow up if still unpaid.",
        };
    }
    if (isSleepingInvoice(inv)) {
        return {
            title: wait ? `Check back on ${wait}` : "Waiting on a date",
            detail: "If they reply sooner, this comes back to Needs you. If they don't, we'll bring it back on that date.",
        };
    }
    if (inv.unmatched) {
        return { title: "No email thread yet", detail: "Friendly reminders wait until we match the invoice email." };
    }
    if (inv.due_date) {
        return { title: `Due ${formatDate(inv.due_date)}`, detail: "Friendly cadence can send from your inbox." };
    }
    return { title: "Watching", detail: "Friendly cadence is on." };
}

export function bucketTone(bucket) {
    if (bucket === BUCKETS.needs_you) return "rose";
    if (bucket === BUCKETS.watching) return "sky";
    if (bucket === BUCKETS.auto_reminders) return "slate";
    if (bucket === BUCKETS.paid) return "emerald";
    if (bucket === BUCKETS.stopped) return "stone";
    return "slate";
}

export const BUCKET_PILL = {
    needs_you: "bg-rose-50 text-rose-800 border-rose-200",
    watching: "bg-sky-50 text-sky-800 border-sky-200",
    auto_reminders: "bg-slate-50 text-slate-700 border-slate-200",
    paid: "bg-emerald-50 text-emerald-800 border-emerald-200",
    stopped: "bg-stone-100 text-stone-700 border-stone-300",
};

export function remainingLabel(inv) {
    const left = Number(inv?.balance_remaining ?? inv?.amount ?? 0);
    const total = Number(inv?.amount ?? 0);
    if (left > 0.005 && total > 0.005 && left + 0.005 < total) {
        return `${formatMoney(left, inv.currency || "USD")} left`;
    }
    return null;
}

export function needsYouInvoices(invoices = []) {
    return invoices.filter(isNeedsYouInvoice).sort((a, b) => {
        const ka = Date.parse(a.last_human_inbound_at || a.status_updated_at || 0) || 0;
        const kb = Date.parse(b.last_human_inbound_at || b.status_updated_at || 0) || 0;
        return kb - ka;
    });
}

export function watchingInvoices(invoices = []) {
    return invoices.filter(isWatchingInvoice).sort((a, b) => {
        const da = Date.parse(a.expected_pay_date || a.due_date || 0) || Number.MAX_SAFE_INTEGER;
        const db = Date.parse(b.expected_pay_date || b.due_date || 0) || Number.MAX_SAFE_INTEGER;
        return da - db;
    });
}

export function autoReminderInvoices(invoices = []) {
    return invoices.filter(isAutoReminderInvoice).sort((a, b) => {
        const da = Date.parse(a.due_date || 0) || Number.MAX_SAFE_INTEGER;
        const db = Date.parse(b.due_date || 0) || Number.MAX_SAFE_INTEGER;
        return da - db;
    });
}

export function stoppedInvoices(invoices = []) {
    return invoices.filter(isStoppedInvoice).sort((a, b) => {
        const ka = Date.parse(a.stopped_at || a.status_updated_at || 0) || 0;
        const kb = Date.parse(b.stopped_at || b.status_updated_at || 0) || 0;
        return kb - ka;
    });
}

export function stoppedOnLabel(inv) {
    const day = formatShortDate(inv?.stopped_at || inv?.status_updated_at);
    return day && day !== "—" ? `Stopped on ${day}` : "Stopped";
}

export function openChaseInvoices(invoices = []) {
    return invoices.filter((inv) => !isPaidInvoice(inv));
}

/** They just wrote you — the next email is a reply, not a cold nudge. */
export function composeIsReply(inv) {
    return isNeedsYouInvoice(inv) && Boolean(inv?.last_human_inbound_at) && inv?.reason !== "wait_date_passed";
}

export function followUpLabel(inv) {
    return composeIsReply(inv) ? "Reply" : "Follow-up";
}

export function formatShortDate(iso) {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    } catch {
        return iso;
    }
}

export function dueMeta(inv) {
    const due = formatShortDate(inv?.due_date);
    const days = Number.isFinite(Number(inv?.days_late)) ? Number(inv.days_late) : null;
    if (days == null) return { due, relative: null, tone: "muted" };
    if (days > 0) return { due, relative: `${days}d overdue`, tone: "rose" };
    if (days === 0) return { due, relative: "Due today", tone: "amber" };
    const n = Math.abs(days);
    return { due, relative: n === 1 ? "in 1 day" : `in ${n} days`, tone: "muted" };
}

export function needsYouTrigger(inv) {
    if (isApprovalDraft(inv)) return "firm_review";
    if (inv?.reason === "wait_date_passed") return "follow_up_due";
    return "new_reply";
}

export const TRIGGER_TAGS = {
    new_reply: { label: "New reply", className: "bg-sky-50 text-sky-800 border-sky-200" },
    follow_up_due: { label: "Follow-up due", className: "bg-amber-50 text-amber-900 border-amber-200" },
    firm_review: { label: "Firm review", className: "bg-violet-50 text-violet-900 border-violet-200" },
};

/** Last thing that happened — the line an operator uses to decide the next email. */
export function latestActivity(inv) {
    if (!inv) return { title: "", detail: null, quote: null };
    const quote = inv.reason_quote || inv.last_human_inbound_quote || null;
    const sentAgo = relativeAgoCompact(inv.last_sent_at);
    const sentLabel = inv.last_sent_label;
    const sentLine = sentLabel
        ? `You sent ${sentLabel}${sentAgo ? ` (${sentAgo})` : ""}`
        : null;

    if (inv.reason === "wait_date_passed" || (inv.expected_pay_date && !isSleepingInvoice(inv) && invoiceBucket(inv) === BUCKETS.needs_you)) {
        const day = formatShortDate(inv.expected_pay_date);
        return {
            title: day ? `Check-back date reached (${day})` : "Check-back date reached",
            detail: "They never replied · Still unpaid in QuickBooks",
            quote: null,
        };
    }
    if (inv.reason === "firm_ready" || inv.reason === "final_ready") {
        const ready = inv.reason === "final_ready" ? "Ready for the last reminder" : "Ready for firm check-in";
        return {
            title: sentLine || "Friendly reminders finished",
            detail: `No reply · ${ready}`,
            quote: null,
        };
    }
    if (inv.reason === "replied" || (invoiceBucket(inv) === BUCKETS.needs_you && inv.last_human_inbound_at)) {
        const ago = relativeAgoCompact(inv.last_human_inbound_at);
        const name = clientShortName(inv);
        return {
            title: ago ? `${name} wrote (${ago}):` : `${name} wrote:`,
            detail: quote ? null : "The automated ladder is off.",
            quote,
        };
    }
    if (sentLine) return { title: sentLine, detail: null, quote };
    const fallback = chaseReason(inv);
    return { title: fallback.title, detail: fallback.detail, quote };
}

export function whyHere(inv) {
    if (!inv) return { title: "", detail: null, quote: null, trigger: null };
    const trigger = needsYouTrigger(inv);
    return { ...latestActivity(inv), trigger };
}

export function cadenceLine(inv) {
    if (isStoppedInvoice(inv)) {
        return { title: stoppedOnLabel(inv), detail: "No automatic reminders.", state: "stopped" };
    }
    if (inv?.cadence?.title) return inv.cadence;
    const reason = chaseReason(inv);
    return {
        title: reason.title,
        detail: reason.detail,
        state: isSleepingInvoice(inv) ? "sleeping" : inv?.unmatched ? "unmatched" : "queued",
    };
}

export function reviewActionLabel(_inv) {
    return "Review";
}

export function hadHumanReply(inv) {
    return Boolean(inv?.last_human_inbound_at || inv?.reason === "replied");
}

export function needsFollowUpLoop(inv) {
    if (!inv || isPaidInvoice(inv) || isStoppedInvoice(inv)) return false;
    if (inv.reason === "wait_date_passed") return true;
    if (hadHumanReply(inv)) return true;
    return isSleepingInvoice(inv);
}

export function invoiceNumber(inv) {
    const ref = String(inv?.invoice_ref || "").trim();
    if (!ref) return "Invoice";
    return ref.startsWith("#") ? ref : `#${ref}`;
}

export function gmailSearchUrl(query) {
    if (!query) return null;
    return `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`;
}

export function daysFromToday(n) {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return toIsoDay(d);
}

export function plusBusinessDays(n) {
    const d = new Date();
    let left = n;
    while (left > 0) {
        d.setDate(d.getDate() + 1);
        const day = d.getDay();
        if (day !== 0 && day !== 6) left -= 1;
    }
    return toIsoDay(d);
}

export function nextMondayIso() {
    const d = new Date();
    const delta = (1 - d.getDay() + 7) % 7 || 7;
    d.setDate(d.getDate() + delta);
    return toIsoDay(d);
}

function toIsoDay(value) {
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}

const WEEKDAYS = {
    sunday: 0, monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6,
    sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
};

/** Best wait date: server suggestion, else a weekday/ISO in the visible reply. */
export function waitSuggestion(inv, extraText = "") {
    if (inv?.suggested_wait_date) {
        return { date: inv.suggested_wait_date, quote: inv.suggested_wait_quote || extraText || null };
    }
    const text = extraText || inv?.reason_quote || inv?.last_human_inbound_quote || "";
    const asOf = inv?.last_human_inbound_at || Date.now();
    const date = detectWaitDate(text, asOf);
    if (!date) return null;
    return { date, quote: text };
}

export function detectWaitDate(text, asOf = new Date()) {
    const source = String(text || "");
    if (!source.trim()) return null;
    const start = new Date(asOf);
    if (Number.isNaN(start.getTime())) return null;
    start.setHours(0, 0, 0, 0);

    const iso = source.match(/\b(\d{4}-\d{2}-\d{2})\b/);
    if (iso) {
        const parsed = new Date(`${iso[1]}T00:00:00`);
        if (!Number.isNaN(parsed.getTime()) && parsed >= start) return iso[1];
    }

    const match = source.match(/\b(?:this|next)?\s*(sunday|monday|tuesday|wednesday|thursday|friday|saturday|sun|mon|tue|wed|thu|fri|sat)\b/i);
    if (!match) return null;
    const target = WEEKDAYS[match[1].toLowerCase()];
    let delta = (target - start.getDay() + 7) % 7;
    if (delta === 0) delta = 7;
    const next = new Date(start);
    next.setDate(start.getDate() + delta);
    return toIsoDay(next);
}

export function invoiceWithWaitSuggestion(inv, extraText = "") {
    const found = waitSuggestion(inv, extraText);
    if (!found) return inv;
    return { ...inv, suggested_wait_date: found.date, suggested_wait_quote: found.quote };
}
