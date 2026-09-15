import { Suspense } from "react";
import LoginPage from "@/views/Login";
import { GuestRoute } from "@/components/ProtectedRoute";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Log in",
    description:
        "Log in to Scotive.",
    alternates: { canonical: absoluteUrl("/login") },
    openGraph: { url: absoluteUrl("/login") },
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
