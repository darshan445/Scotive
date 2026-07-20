import ReviewQueuePage from "@/views/ReviewQueue";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export const metadata = {
    title: "Review",
    robots: { index: false, follow: false },
};

export default function Page() {
    return (
        <ProtectedRoute>
            <ReviewQueuePage />
        </ProtectedRoute>
    );
}
