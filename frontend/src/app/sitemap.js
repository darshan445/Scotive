import { SITE_URL } from "@/lib/seo";
import { GUIDES } from "@/lib/guides";

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
        { path: "/guides", priority: 0.9, changeFrequency: "weekly" },
        ...GUIDES.map((g) => ({
            path: g.path,
            priority: 0.85,
            changeFrequency: "monthly",
        })),
        { path: "/register", priority: 0.8, changeFrequency: "monthly" },
        { path: "/login", priority: 0.5, changeFrequency: "monthly" },
        { path: "/terms", priority: 0.3, changeFrequency: "yearly" },
        { path: "/privacy", priority: 0.3, changeFrequency: "yearly" },
    ];
    // Coming-soon integration pages are noindex — omit from sitemap until live.
    return pages.map(({ path, priority, changeFrequency }) => ({
        url: path ? `${SITE_URL}${path}` : SITE_URL,
        lastModified: now,
        changeFrequency,
        priority,
    }));
}
