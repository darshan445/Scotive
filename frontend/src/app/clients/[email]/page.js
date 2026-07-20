import ClientDetailPage from "@/views/ClientDetail";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Client",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <ProtectedRoute>
            <ClientDetailPage />
        </ProtectedRoute>
    );
}
