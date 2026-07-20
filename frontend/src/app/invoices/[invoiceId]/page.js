import DashboardPage from "@/views/Dashboard";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { InvoiceDrawerClient } from "@/components/InvoiceDrawerClient";

export const metadata = {
    title: "Invoice",
    robots: { index: false, follow: false },
};

export default async function InvoicePage({ params }) {
    const { invoiceId } = await params;
    return (
        <ProtectedRoute>
            <DashboardPage />
            <InvoiceDrawerClient invoiceId={invoiceId} fallbackHref="/dashboard" />
        </ProtectedRoute>
    );
}
