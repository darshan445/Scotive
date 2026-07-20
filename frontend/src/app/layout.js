import {
    Bricolage_Grotesque,
    Inter,
    JetBrains_Mono,
} from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-sans",
    display: "swap",
});

const bricolage = Bricolage_Grotesque({
    subsets: ["latin"],
    variable: "--font-heading",
    display: "swap",
});

const jetbrains = JetBrains_Mono({
    subsets: ["latin"],
    variable: "--font-mono",
    display: "swap",
});

export const metadata = {
    metadataBase: new URL(SITE_URL),
    title: {
        default: "Scotive — Payment ops inside Gmail",
        template: "%s · Scotive",
    },
    description:
        "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices — automatically detecting invoices you've sent, reading client replies for promises, disputes, and payments.",
    applicationName: "Scotive",
    keywords: [
        "invoice tracking",
        "Gmail invoice tracker",
        "accounts receivable",
        "chase unpaid invoices",
        "freelance invoicing",
        "payment follow-up",
        "payment ops",
    ],
    authors: [{ name: "Scotive" }],
    creator: "Scotive",
    publisher: "Scotive",
    category: "business",
    alternates: {
        canonical: "/",
    },
    openGraph: {
        type: "website",
        locale: "en_US",
        url: SITE_URL,
        siteName: "Scotive",
        title: "Scotive — Payment ops inside Gmail",
        description:
            "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices. No manual data entry. Nothing is sent without your review.",
        images: [
            {
                url: "/logo512.png",
                width: 512,
                height: 512,
                alt: "Scotive",
            },
        ],
    },
    twitter: {
        card: "summary",
        title: "Scotive — Payment ops inside Gmail",
        description:
            "Gmail-native invoice tracking tool to chase unpaid invoices — with drafts you review before anything sends.",
        images: ["/logo512.png"],
    },
    robots: {
        index: true,
        follow: true,
        googleBot: {
            index: true,
            follow: true,
            "max-image-preview": "large",
            "max-snippet": -1,
            "max-video-preview": -1,
        },
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
    width: "device-width",
    initialScale: 1,
    maximumScale: 5,
};

export default function RootLayout({ children, modal }) {
    return (
        <html
            lang="en"
            className={`${inter.variable} ${bricolage.variable} ${jetbrains.variable}`}
        >
            <body className="min-h-screen bg-background text-foreground antialiased font-sans">
                <Providers>
                    {children}
                    {modal}
                </Providers>
            </body>
        </html>
    );
}
