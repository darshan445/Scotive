import "./globals.css";
import { Providers } from "@/components/Providers";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com";

export const metadata = {
    metadataBase: new URL(SITE_URL),
    title: {
        default: "Scotive — Payment ops inside Gmail",
        template: "%s · Scotive",
    },
    description:
        "Scotive watches your Gmail and tracks who owes you money — detecting invoices you've sent, reading client replies for promises and payments, and drafting follow-ups you review before anything sends.",
    applicationName: "Scotive",
    keywords: [
        "invoice tracking",
        "Gmail",
        "accounts receivable",
        "freelance invoicing",
        "payment follow-up",
    ],
    authors: [{ name: "Scotive" }],
    openGraph: {
        type: "website",
        locale: "en_US",
        url: SITE_URL,
        siteName: "Scotive",
        title: "Scotive — Payment ops inside Gmail",
        description:
            "Scotive watches your Gmail and tracks who owes you money. No manual data entry. Nothing is sent without your review.",
    },
    twitter: {
        card: "summary",
        title: "Scotive — Payment ops inside Gmail",
        description:
            "Gmail-native invoice tracking with drafts you review before anything sends.",
    },
    icons: {
        icon: [
            { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
            { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
            { url: "/favicon.png", type: "image/png" },
        ],
        apple: [{ url: "/apple-touch-icon.png" }],
    },
};

export const viewport = {
    themeColor: "#114B3F",
};

export default function RootLayout({ children, modal }) {
    return (
        <html lang="en">
            <head>
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link
                    href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700;12..96,800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
                    rel="stylesheet"
                />
            </head>
            <body className="min-h-screen bg-background text-foreground antialiased">
                <Providers>
                    {children}
                    {modal}
                </Providers>
            </body>
        </html>
    );
}
