import RegisterPage from "@/views/Register";
import { GuestRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Create account",
    description: "Start free with Scotive — payment ops inside Gmail.",
    alternates: { canonical: "/register" },
};

export default function Page() {
    return (
        <GuestRoute>
            <RegisterPage />
        </GuestRoute>
    );
}
