export default function sitemap() {
    const site = process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com";
    return [
        {
            url: site,
            lastModified: new Date(),
            changeFrequency: "weekly",
            priority: 1,
        },
        {
            url: `${site}/register`,
            lastModified: new Date(),
            changeFrequency: "monthly",
            priority: 0.5,
        },
        {
            url: `${site}/privacy`,
            lastModified: new Date(),
            changeFrequency: "yearly",
            priority: 0.4,
        },
        {
            url: `${site}/terms`,
            lastModified: new Date(),
            changeFrequency: "yearly",
            priority: 0.4,
        },
    ];
}
