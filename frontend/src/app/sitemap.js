const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com").replace(
    /\/$/,
    "",
);

export default function sitemap() {
    const now = new Date();
    const pages = [
        { path: "", priority: 1, changeFrequency: "weekly" },
        { path: "/invoice-chasing-software", priority: 0.9, changeFrequency: "weekly" },
        { path: "/chase-unpaid-invoices", priority: 0.9, changeFrequency: "weekly" },
        { path: "/accounts-receivable-automation", priority: 0.9, changeFrequency: "weekly" },
        { path: "/overdue-invoice-reminder", priority: 0.85, changeFrequency: "weekly" },
        { path: "/integrations", priority: 0.85, changeFrequency: "weekly" },
        { path: "/quickbooks-invoice-chasing", priority: 0.85, changeFrequency: "weekly" },
        { path: "/outlook-invoice-chasing", priority: 0.75, changeFrequency: "monthly" },
        { path: "/zoho-books-invoice-chasing", priority: 0.75, changeFrequency: "monthly" },
        { path: "/freshbooks-invoice-chasing", priority: 0.75, changeFrequency: "monthly" },
        { path: "/register", priority: 0.8, changeFrequency: "monthly" },
        { path: "/login", priority: 0.5, changeFrequency: "monthly" },
        { path: "/terms", priority: 0.3, changeFrequency: "yearly" },
        { path: "/privacy", priority: 0.3, changeFrequency: "yearly" },
    ];
    return pages.map(({ path, priority, changeFrequency }) => ({
        url: path ? `${SITE}${path}` : SITE,
        lastModified: now,
        changeFrequency,
        priority,
    }));
}
