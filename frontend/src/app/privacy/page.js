import PrivacyPage from "@/views/Privacy";
import { absoluteUrl } from "@/lib/seo";

export const metadata = {
    title: "Privacy Policy",
    description:
        "How Scotive collects, uses, and protects your account, email, and accounting connection data for invoice chasing.",
    alternates: { canonical: absoluteUrl("/privacy") },
    openGraph: { url: absoluteUrl("/privacy") },
};

export default function Page() {
    return <PrivacyPage />;
}
