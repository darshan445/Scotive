import { InvoiceDrawerClient } from "@/components/InvoiceDrawerClient";

export default async function InvoiceModalPage({ params }) {
    const { invoiceId } = await params;
    return <InvoiceDrawerClient invoiceId={invoiceId} />;
}
