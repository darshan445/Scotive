import SettingsPage from "@/views/Settings";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Settings",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <ProtectedRoute>
            <SettingsPage />
        </ProtectedRoute>
    );
}
