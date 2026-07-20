const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com";

export default function robots() {
    return {
        rules: [
            {
                userAgent: "*",
                allow: "/",
                disallow: [
                    "/dashboard",
                    "/clients",
                    "/review",
                    "/settings",
                    "/invoices/",
                    "/api/",
                ],
            },
        ],
        sitemap: `${SITE.replace(/\/$/, "")}/sitemap.xml`,
        host: SITE.replace(/\/$/, ""),
    };
}
