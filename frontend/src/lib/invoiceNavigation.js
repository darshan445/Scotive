/** Open `/invoices/:id` as a modal route so the current page stays mounted. */
export function navigateToInvoice(navigate, location, invoiceId) {
    if (!invoiceId) return;
    navigate(`/invoices/${invoiceId}`, {
        state: { backgroundLocation: location.state?.backgroundLocation || location },
    });
}
