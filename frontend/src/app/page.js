import LandingPage from "@/views/Landing";
import { GuestRoute } from "@/components/ProtectedRoute";
import { JsonLd } from "@/components/JsonLd";

export const metadata = {
    title: {
        absolute:
            "Scotive — Invoice Tracking Tool to Chase Unpaid Invoices | Gmail-Native",
    },
    description:
        "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices — automatically detecting invoices you've sent, reading client replies for promises, disputes, and payments.",
    alternates: { canonical: "/" },
    openGraph: {
        url: "/",
        title: "Scotive — Invoice Tracking Tool to Chase Unpaid Invoices | Gmail-Native",
        description:
            "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices — detecting invoices you've sent and reading client replies for promises, disputes, and payments.",
    },
    twitter: {
        title: "Scotive — Invoice Tracking Tool to Chase Unpaid Invoices | Gmail-Native",
        description:
            "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices.",
    },
};

export default function HomePage() {
    return (
        <>
            <JsonLd />
            <GuestRoute>
                <LandingPage />
            </GuestRoute>
        </>
    );
}
