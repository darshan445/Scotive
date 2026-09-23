import { AUDIENCE_SHORT, DEFAULT_DESCRIPTION, SITE_URL } from "@/lib/seo";
import { ANNUAL_TOTAL, MONTHLY_PRICE } from "@/lib/site";

const SITE = SITE_URL;
const DESCRIPTION = DEFAULT_DESCRIPTION;

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
                description: DESCRIPTION,
                email: "contact@scotive.com",
                sameAs: [],
            },
            {
                "@type": "WebSite",
                "@id": `${SITE}/#website`,
                url: SITE,
                name: "Scotive",
                publisher: { "@id": `${SITE}/#organization` },
                description: DESCRIPTION,
            },
            {
                "@type": "SoftwareApplication",
                "@id": `${SITE}/#software`,
                name: "Scotive",
                applicationCategory: "BusinessApplication",
                operatingSystem: "Web",
                url: SITE,
                image: `${SITE}/logo512.png`,
                description: DESCRIPTION,
                audience: {
                    "@type": "Audience",
                    audienceType: AUDIENCE_SHORT,
                },
                featureList: [
                    "Match Gmail/Outlook thread to invoice",
                    "Approved Friendly cadence from your inbox",
                    "Pauses the moment a client replies",
                    "Check-back date if still unpaid",
                    "Pay link in the draft",
                    "Firm emails wait for a click",
                    "Keep QBO/Xero as the ledger",
                ],
                offers: [
                    {
                        "@type": "Offer",
                        name: "Monthly",
                        price: String(MONTHLY_PRICE),
                        priceCurrency: "USD",
                    },
                    {
                        "@type": "Offer",
                        name: "Yearly",
                        price: String(ANNUAL_TOTAL),
                        priceCurrency: "USD",
                    },
                ],
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
