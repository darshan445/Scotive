import RegisterPage from "@/views/Register";
import { GuestRoute } from "@/components/ProtectedRoute";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Create account",
    description:
        "Create a Scotive account. Start a 30-day free trial — no card required.",
    alternates: { canonical: absoluteUrl("/register") },
    openGraph: { url: absoluteUrl("/register") },
};

export default function Page() {
    return (
        <GuestRoute>
            <RegisterPage />
        </GuestRoute>
    );
}
