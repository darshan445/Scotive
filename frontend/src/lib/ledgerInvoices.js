import {
    isNeedsYouInvoice,
    isPaidInvoice,
    isStoppedInvoice,
    isWatchingInvoice,
    isAutoReminderInvoice,
    needsYouInvoices,
    watchingInvoices,
    autoReminderInvoices,
    stoppedInvoices,
} from "@/lib/chase";

/** Closed invoices — hidden from the open ledger tab. */
export const HISTORY_INVOICE_STATUSES = new Set(["paid", "written_off"]);

export const STATUS_FILTER_CHIPS = [
    { key: "all", label: "All" },
    { key: "needs_you", label: "Needs you" },
    { key: "watching", label: "Watching" },
    { key: "auto_reminders", label: "Auto reminders" },
    { key: "stopped", label: "Stopped" },
];

export const SORT_OPTIONS = [
    { key: "due_soonest", label: "Due soonest" },
    { key: "oldest", label: "Oldest first" },
    { key: "largest", label: "Largest amount" },
    { key: "most_overdue", label: "Most overdue" },
];

export function isTrackingPaused(inv) {
    return isStoppedInvoice(inv);
}

export function isOpenLedgerInvoice(inv) {
    return Boolean(inv) && !isPaidInvoice(inv) && !isStoppedInvoice(inv);
}

export function isHistoryLedgerInvoice(inv) {
    return isPaidInvoice(inv);
}

export function isPausedLedgerInvoice(inv) {
    return isStoppedInvoice(inv);
}

export function outstandingBalance(inv) {
    if (!inv) return 0;
    const amt = Number(inv.amount || 0);
    const bal = inv.balance_remaining != null ? Number(inv.balance_remaining) : amt;
    return bal > 0 ? bal : 0;
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
    if (filter === "needs_you") return isNeedsYouInvoice(inv);
    if (filter === "watching") return isWatchingInvoice(inv);
    if (filter === "auto_reminders") return isAutoReminderInvoice(inv);
    if (filter === "stopped") return isStoppedInvoice(inv);
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
        const ka = _dayTs(a.expected_pay_date) ?? _dayTs(a.due_date);
        const kb = _dayTs(b.expected_pay_date) ?? _dayTs(b.due_date);
        if (ka == null && kb == null) return 0;
        if (ka == null) return 1;
        if (kb == null) return -1;
        return ka - kb;
    });
    return rows;
}

export function openLedgerInvoices(invoices = [], { statusFilter = "all", sort = "due_soonest" } = {}) {
    const open = invoices.filter(isOpenLedgerInvoice).filter((inv) => matchesStatusFilter(inv, statusFilter));
    return sortInvoices(open, sort);
}

export function pausedLedgerInvoices(invoices = []) {
    return stoppedInvoices(invoices);
}

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

export function historyLedgerSummary(invoices = []) {
    const history = historyLedgerInvoices(invoices);
    const paid = history.filter((inv) => inv.books_status !== "voided");
    const writtenOff = history.filter((inv) => inv.books_status === "voided");

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

export { needsYouInvoices, watchingInvoices, autoReminderInvoices, stoppedInvoices };
