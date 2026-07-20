import { Suspense } from "react";
import ResetPasswordPage from "@/views/ResetPassword";

export const metadata = {
    title: "Reset password",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <Suspense fallback={null}>
            <ResetPasswordPage />
        </Suspense>
    );
}
