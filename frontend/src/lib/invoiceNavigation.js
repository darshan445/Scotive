/** Open invoice detail at /invoices/:id (Next intercepting route shows as modal when available). */
export function navigateToInvoice(router, _locationOrPathname, invoiceId) {
    if (!invoiceId) return;
    router.push(`/invoices/${invoiceId}`);
}
