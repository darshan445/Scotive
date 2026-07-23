import PrivacyPage from "@/views/Privacy";

export const metadata = {
    title: "Privacy Policy",
    description:
        "How Scotive collects, uses, and protects your account, email, and accounting connection data for invoice chasing.",

    alternates: { canonical: "/privacy" },
};

export default function Page() {
    return <PrivacyPage />;
}
