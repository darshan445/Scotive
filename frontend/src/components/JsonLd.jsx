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
                logo: {
                    "@type": "ImageObject",
                    url: `${SITE}/logo512.png`,
                },
                image: `${SITE}/scotive-icon.png`,
                description:
                    "Invoice chasing software for freelancers, agencies, consultants, and any team that bills clients — track unpaid invoices from email and accounting tools, with human-approved follow-ups.",
                email: "contact@scotive.com",
                sameAs: [],
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
                "@id": `${SITE}/#software`,
                name: "Scotive",
                applicationCategory: "BusinessApplication",
                operatingSystem: "Web",
                url: SITE,
                image: `${SITE}/logo512.png`,
                description:
                    "Invoice chasing software that tracks unpaid invoices from Gmail and QuickBooks Online, reads client replies for promises and disputes, and drafts follow-ups you approve before sending. Outlook, Zoho Books, and FreshBooks on the roadmap.",
                audience: {
                    "@type": "Audience",
                    audienceType:
                        "Freelancers, agencies, consultants, professional services, and businesses that bill clients",
                },
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
                provider: { "@id": `${SITE}/#organization` },
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
