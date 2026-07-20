import { Suspense } from "react";
import LoginPage from "@/views/Login";
import { GuestRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Log in",
    description: "Log in to Scotive to track invoices and follow-ups from Gmail.",
    robots: { index: false, follow: false },
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
