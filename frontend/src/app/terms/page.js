import TermsPage from "@/views/Terms";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Terms of Service",
    description:
        "Terms of Service for using Scotive invoice chasing software, including email and optional accounting integrations.",
    alternates: { canonical: absoluteUrl("/terms") },
    openGraph: { url: absoluteUrl("/terms") },
};

export default function Page() {
    return <TermsPage />;
}
