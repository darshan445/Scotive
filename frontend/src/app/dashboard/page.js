import { Suspense } from "react";
import DashboardPage from "@/views/Dashboard";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Dashboard",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <ProtectedRoute>
            <Suspense fallback={null}>
                <DashboardPage />
            </Suspense>
        </ProtectedRoute>
    );
}
