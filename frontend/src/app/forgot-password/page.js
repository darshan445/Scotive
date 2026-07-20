import ForgotPasswordPage from "@/views/ForgotPassword";
import { GuestRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Forgot password",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <GuestRoute>
            <ForgotPasswordPage />
        </GuestRoute>
    );
}
