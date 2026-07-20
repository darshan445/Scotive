import PrivacyPage from "@/views/Privacy";

export const metadata = {
    title: "Privacy Policy",
    description:
        "How Scotive collects, uses, and protects your Gmail and account data.",
    alternates: { canonical: "/privacy" },
};

export default function Page() {
    return <PrivacyPage />;
}
