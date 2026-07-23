import { DEFAULT_DESCRIPTION, SITE_URL } from "@/lib/seo";

const SITE = SITE_URL;

/** JSON-LD for Google rich results / knowledge understanding. */
export function JsonLd() {
    const data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": `${SITE}/#organization`,
                name: "Scotive",
                url: SITE,
                logo: `${SITE}/logo512.png`,
                description:
                    "Invoice chasing software for freelancers and small teams — track unpaid invoices from email and accounting tools, with human-approved follow-ups.",
                email: "support@scotive.com",
            },
            {
                "@type": "WebSite",
                "@id": `${SITE}/#website`,
                url: SITE,
                name: "Scotive",
                publisher: { "@id": `${SITE}/#organization` },
                description: DEFAULT_DESCRIPTION,
            },
            {
                "@type": "SoftwareApplication",
                name: "Scotive",
                applicationCategory: "BusinessApplication",
                operatingSystem: "Web",
                url: SITE,
                description:
                    "Invoice chasing and accounts receivable follow-up software. Connects email (Gmail today; Outlook next) and accounting (QuickBooks Online today; Zoho Books and FreshBooks next). Drafts payment follow-ups you approve before send.",
                featureList: [
                    "Invoice tracking from email and accounting",
                    "Client reply intelligence (promises, disputes, payment claims)",
                    "Human-approved chase drafts",
                    "QuickBooks Online unpaid invoice import and paid sync",
                ],
                offers: {
                    "@type": "Offer",
                    price: "0",
                    priceCurrency: "USD",
                    description: "Free to start",
                },
            },
        ],
    };

    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
        />
    );
}
