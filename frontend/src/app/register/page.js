import RegisterPage from "@/views/Register";
import { GuestRoute } from "@/components/ProtectedRoute";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Create account",
    description:
        "Start free with Scotive — invoice chasing software for email and accounting. Approve every follow-up before it sends.",
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
