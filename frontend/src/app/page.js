import LandingPage from "@/views/Landing";
import { GuestRoute } from "@/components/ProtectedRoute";
import { JsonLd } from "@/components/JsonLd";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE } from "@/lib/seo";

export const metadata = {
    title: {
        absolute: DEFAULT_TITLE,
    },
    description: DEFAULT_DESCRIPTION,
    alternates: { canonical: "/" },
    openGraph: {
        url: "/",
        title: DEFAULT_TITLE,
        description: DEFAULT_DESCRIPTION,
    },
    twitter: {
        title: DEFAULT_TITLE,
        description:
            "Invoice chasing software for email + accounting. Approve every follow-up before it sends.",
    },
};

export default function HomePage() {
    return (
        <>
            <JsonLd />
            <GuestRoute>
                <LandingPage />
            </GuestRoute>
        </>
    );
}
