const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com").replace(
    /\/$/,
    "",
);

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
                    "Invoice tracking tool for freelancers who bill from Gmail — chase unpaid invoices without the awkward manual follow-up.",
            },
            {
                "@type": "WebSite",
                "@id": `${SITE}/#website`,
                url: SITE,
                name: "Scotive",
                publisher: { "@id": `${SITE}/#organization` },
                description:
                    "Scotive is an invoice tracking tool that watches your Gmail and helps you chase unpaid invoices. No manual data entry. Nothing is sent without your review.",
            },
            {
                "@type": "SoftwareApplication",
                name: "Scotive",
                applicationCategory: "BusinessApplication",
                operatingSystem: "Web",
                url: SITE,
                description:
                    "Gmail-native invoice tracking tool to chase unpaid invoices — detects invoices you've sent, reads client replies for promises and payments, and drafts follow-ups you approve before send.",
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
