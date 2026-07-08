/** Closed invoices — hidden from the open ledger tab. */
export const HISTORY_INVOICE_STATUSES = new Set(["paid", "written_off"]);

export function isOpenLedgerInvoice(inv) {
    return inv?.status && !HISTORY_INVOICE_STATUSES.has(inv.status);
}

export function isHistoryLedgerInvoice(inv) {
    return inv?.status && HISTORY_INVOICE_STATUSES.has(inv.status);
}

function _ts(iso) {
    if (!iso) return 0;
    const t = Date.parse(iso);
    return Number.isFinite(t) ? t : 0;
}

/** Open rows keep API due/promise order; only filter out closed statuses. */
export function openLedgerInvoices(invoices = []) {
    return invoices.filter(isOpenLedgerInvoice);
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
