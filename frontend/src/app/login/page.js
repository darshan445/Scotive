import { Suspense } from "react";
import LoginPage from "@/views/Login";
import { GuestRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Log in",
    description:
        "Log in to Scotive to track unpaid invoices and approve payment follow-ups from your connected tools.",
    alternates: { canonical: "/login" },
};

export default function Page() {
    return (
        <GuestRoute>
            <Suspense fallback={null}>
                <LoginPage />
            </Suspense>
        </GuestRoute>
    );
}
