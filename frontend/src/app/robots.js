import { SITE_URL } from "@/lib/seo";

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
        sitemap: `${SITE_URL}/sitemap.xml`,
        host: SITE_URL,
    };
}
