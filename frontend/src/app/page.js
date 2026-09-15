import LandingPage from "@/views/Landing";
import { GuestRoute } from "@/components/ProtectedRoute";
import { JsonLd } from "@/components/JsonLd";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE, SITE_URL } from "@/lib/seo";

const TITLE = DEFAULT_TITLE;
const DESCRIPTION = DEFAULT_DESCRIPTION;

export const metadata = {
    title: {
        absolute: TITLE,
    },
    description: DESCRIPTION,
    keywords: [
        "invoice reminder software",
        "past due invoice reminder",
        "payment reminder software",
        "quickbooks invoice reminders",
        "xero invoice reminders",
    ],
    alternates: { canonical: SITE_URL },
    openGraph: {
        url: SITE_URL,
        title: TITLE,
        description: DESCRIPTION,
    },
    twitter: {
        title: TITLE,
        description: DESCRIPTION,
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
