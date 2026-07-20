import LandingPage from "@/views/Landing";
import { GuestRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Payment ops inside Gmail",
    description:
        "Scotive watches your Gmail and tracks who owes you money — automatically detecting invoices you've sent, reading client replies for promises, disputes, and payments. No manual data entry. Nothing is sent without your review.",
    alternates: { canonical: "/" },
};

export default function HomePage() {
    return (
        <GuestRoute>
            <LandingPage />
        </GuestRoute>
    );
}
