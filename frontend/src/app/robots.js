export default function robots() {
    const site = process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com";
    return {
        rules: {
            userAgent: "*",
            allow: ["/", "/login", "/register"],
            disallow: ["/dashboard", "/clients", "/review", "/settings", "/invoices"],
        },
        sitemap: `${site}/sitemap.xml`,
    };
}
