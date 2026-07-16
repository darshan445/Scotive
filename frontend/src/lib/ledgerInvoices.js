/** Closed invoices — hidden from the open ledger tab. */
export const HISTORY_INVOICE_STATUSES = new Set(["paid", "written_off"]);

export const STATUS_FILTER_CHIPS = [
    { key: "all", label: "All" },
    { key: "overdue", label: "Overdue" },
    { key: "promised", label: "Promised" },
    { key: "disputed", label: "Disputed" },
    { key: "paid_unconfirmed", label: "Says paid" },
    { key: "invoiced", label: "Invoiced" },
    { key: "partially_paid", label: "Partially paid" },
    { key: "promise_broken", label: "Broken promise" },
];

export const SORT_OPTIONS = [
    { key: "due_soonest", label: "Due soonest" },
    { key: "oldest", label: "Oldest first" },
    { key: "largest", label: "Largest amount" },
    { key: "most_overdue", label: "Most overdue" },
];

export function isTrackingPaused(inv) {
    return Boolean(inv?.tracking_paused);
}

/** Active open rows — excludes paid/written_off and user-paused. */
export function isOpenLedgerInvoice(inv) {
    return inv?.status
        && !HISTORY_INVOICE_STATUSES.has(inv.status)
        && !isTrackingPaused(inv);
}

export function isHistoryLedgerInvoice(inv) {
    return inv?.status && HISTORY_INVOICE_STATUSES.has(inv.status);
}

/** User-paused open invoices (Paused tab). */
export function isPausedLedgerInvoice(inv) {
    return isTrackingPaused(inv) && inv?.status && !HISTORY_INVOICE_STATUSES.has(inv.status);
}

/**
 * Amount that counts toward Outstanding / You're Owed / client subtotals.
 * Unconfirmed payment claims never reduce this.
 */
export function outstandingBalance(inv) {
    if (!inv) return 0;
    const amt = Number(inv.amount || 0);
    const bal = inv.balance_remaining != null ? Number(inv.balance_remaining) : amt;
    const pending = Boolean(inv.payment_claim_pending) || inv.status === "paid_unconfirmed";
    if (!pending) return bal;

    if (inv.claim_balance_before != null) {
        return Math.max(0, Number(inv.claim_balance_before));
    }
    if (inv.claim_paid_before != null) {
        return Math.max(0, Math.round((amt - Number(inv.claim_paid_before || 0)) * 100) / 100);
    }
    const claim = Number(inv.payment_claim_amount);
    if (Number.isFinite(claim) && claim > 0.005) {
        if (bal + 0.005 < amt && Math.abs((bal + claim) - amt) <= Math.max(0.02, amt * 0.001)) {
            return Math.round((bal + claim) * 100) / 100;
        }
        if (bal <= 0.005) {
            return Math.abs(claim - amt) <= 0.02 ? Math.max(claim, amt) : Math.round((bal + claim) * 100) / 100;
        }
        return bal;
    }
    if (inv.status === "paid_unconfirmed" && bal <= 0.005) return amt;
    return bal;
}

function _ts(iso) {
    if (!iso) return 0;
    const t = Date.parse(iso);
    return Number.isFinite(t) ? t : 0;
}

function _dayTs(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    d.setHours(0, 0, 0, 0);
    return d.getTime();
}

function matchesStatusFilter(inv, filter) {
    if (!filter || filter === "all") return true;
    if (filter === "disputed") {
        return inv.status === "disputed"
            || (inv.disputed_claim_amount != null && Number(inv.disputed_claim_amount) > 0);
    }
    if (filter === "overdue") {
        return inv.status === "overdue" || inv.status === "promise_broken";
    }
    if (filter === "partially_paid") {
        return inv.status === "partially_paid"
            || (Number(inv.paid_amount || 0) > 0.005
                && Number(inv.balance_remaining ?? inv.amount ?? 0) > 0.005
                && !inv.payment_claim_pending
                && inv.status !== "paid_unconfirmed"
                && !HISTORY_INVOICE_STATUSES.has(inv.status));
    }
    if (filter === "paid_unconfirmed") {
        return inv.status === "paid_unconfirmed" || inv.payment_claim_pending;
    }
    return inv.status === filter;
}

function sortInvoices(list, sortKey) {
    const rows = list.slice();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayTs = today.getTime();

    if (sortKey === "largest") {
        rows.sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0));
        return rows;
    }
    if (sortKey === "oldest") {
        rows.sort((a, b) => {
            const ka = _ts(a.source_date) || _ts(a.created_at);
            const kb = _ts(b.source_date) || _ts(b.created_at);
            return ka - kb;
        });
        return rows;
    }
    if (sortKey === "most_overdue") {
        rows.sort((a, b) => {
            const da = _dayTs(a.due_date);
            const db = _dayTs(b.due_date);
            const lateA = da != null ? Math.max(0, todayTs - da) : -1;
            const lateB = db != null ? Math.max(0, todayTs - db) : -1;
            return lateB - lateA;
        });
        return rows;
    }
    rows.sort((a, b) => {
        const ka = _dayTs(a.promise_date) ?? _dayTs(a.due_date);
        const kb = _dayTs(b.promise_date) ?? _dayTs(b.due_date);
        if (ka == null && kb == null) return 0;
        if (ka == null) return 1;
        if (kb == null) return -1;
        return ka - kb;
    });
    return rows;
}

/** Open rows with optional status filter + sort. */
export function openLedgerInvoices(invoices = [], { statusFilter = "all", sort = "due_soonest" } = {}) {
    const open = invoices.filter(isOpenLedgerInvoice).filter((inv) => matchesStatusFilter(inv, statusFilter));
    return sortInvoices(open, sort);
}

/** User-paused invoices — most recently paused first. */
export function pausedLedgerInvoices(invoices = []) {
    return invoices
        .filter(isPausedLedgerInvoice)
        .slice()
        .sort((a, b) => {
            const ka = _ts(a.status_updated_at) || _ts(a.source_date) || _ts(a.created_at);
            const kb = _ts(b.status_updated_at) || _ts(b.source_date) || _ts(b.created_at);
            return kb - ka;
        });
}

/** Group open invoices under client headers with subtotals. */
export function groupInvoicesByClient(invoices = []) {
    const map = new Map();
    for (const inv of invoices) {
        const key = inv.client_identity_key || (inv.counterparty_email || "").toLowerCase() || inv._id;
        if (!map.has(key)) {
            map.set(key, {
                key,
                name: inv.counterparty_name || inv.counterparty_email || "Client",
                email: inv.counterparty_email,
                invoices: [],
                subtotals: {},
            });
        }
        const g = map.get(key);
        g.invoices.push(inv);
        if (!g.name && inv.counterparty_name) g.name = inv.counterparty_name;
        const cur = (inv.currency || "USD").toUpperCase();
        const bal = outstandingBalance(inv);
        g.subtotals[cur] = (g.subtotals[cur] || 0) + bal;
    }
    return [...map.values()];
}

/** Paid / written-off — most recently closed first. */
export function historyLedgerInvoices(invoices = []) {
    return invoices
        .filter(isHistoryLedgerInvoice)
        .slice()
        .sort((a, b) => {
            const ka = _ts(a.paid_at) || _ts(a.status_updated_at) || _ts(a.source_date) || _ts(a.created_at);
            const kb = _ts(b.paid_at) || _ts(b.status_updated_at) || _ts(b.source_date) || _ts(b.created_at);
            return kb - ka;
        });
}

/** Totals for the paid / closed ledger tab. */
export function historyLedgerSummary(invoices = []) {
    const history = historyLedgerInvoices(invoices);
    const paid = history.filter((inv) => inv.status === "paid");
    const writtenOff = history.filter((inv) => inv.status === "written_off");

    const totalsByCurrency = {};
    for (const inv of paid) {
        const cur = (inv.currency || "USD").toUpperCase();
        totalsByCurrency[cur] = (totalsByCurrency[cur] || 0) + Number(inv.amount || 0);
    }

    const clients = new Set();
    for (const inv of history) {
        const key = inv.client_identity_key || inv.counterparty_email;
        if (key) clients.add(key);
    }

    return {
        totalsByCurrency,
        paidCount: paid.length,
        writtenOffCount: writtenOff.length,
        clientCount: clients.size,
    };
}
