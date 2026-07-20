import ClientsPage from "@/views/Clients";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Clients",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <ProtectedRoute>
            <ClientsPage />
        </ProtectedRoute>
    );
}
