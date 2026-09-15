import TermsPage from "@/views/Terms";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Terms of Service",
    description:
        "Terms of Service for Scotive. Not a new books app. You keep QBO/Xero. We run the chase.",
    alternates: { canonical: absoluteUrl("/terms") },
    openGraph: { url: absoluteUrl("/terms") },
};

export default function Page() {
    return <TermsPage />;
}
