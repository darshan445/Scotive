import {
    Inter,
    JetBrains_Mono,
} from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE, PRIMARY_KEYWORDS, SITE_URL } from "@/lib/seo";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-sans",
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
        default: DEFAULT_TITLE,
        template: "%s · Scotive",
    },
    description: DEFAULT_DESCRIPTION,
    applicationName: "Scotive",
    keywords: PRIMARY_KEYWORDS,
    authors: [{ name: "Scotive" }],
    creator: "Scotive",
    publisher: "Scotive",
    category: "business",
    alternates: {
        canonical: SITE_URL,
    },
    openGraph: {
        type: "website",
        locale: "en_US",
        url: SITE_URL,
        siteName: "Scotive",
        title: DEFAULT_TITLE,
        description: DEFAULT_DESCRIPTION,
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
        title: DEFAULT_TITLE,
        description: DEFAULT_DESCRIPTION,
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
    themeColor: "#1E4ED8",
    width: "device-width",
    initialScale: 1,
    maximumScale: 5,
};

export default function RootLayout({ children, modal }) {
    return (
        <html
            lang="en"
            className={`${inter.variable} ${jetbrains.variable}`}
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
