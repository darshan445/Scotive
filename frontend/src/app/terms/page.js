import TermsPage from "@/views/Terms";

export const metadata = {
    title: "Terms of Service",
    description:
        "Terms of Service for using Scotive, including Gmail and optional QuickBooks Online.",

    alternates: { canonical: "/terms" },
};

export default function Page() {
    return <TermsPage />;
}
