import { SITE_URL } from "@/lib/seo";

export default function sitemap() {
    const now = new Date();
    const pages = [
        { path: "", priority: 1, changeFrequency: "weekly" },
        { path: "/invoice-reminder-software", priority: 0.9, changeFrequency: "weekly" },
        { path: "/past-due-invoice-reminder", priority: 0.9, changeFrequency: "weekly" },
        { path: "/payment-reminder-email-template", priority: 0.9, changeFrequency: "weekly" },
        { path: "/how-to-chase-outstanding-invoices", priority: 0.9, changeFrequency: "weekly" },
        { path: "/quickbooks-invoice-reminders", priority: 0.9, changeFrequency: "weekly" },
        { path: "/xero-invoice-reminders", priority: 0.9, changeFrequency: "weekly" },
        { path: "/freshbooks-invoice-reminders", priority: 0.9, changeFrequency: "weekly" },
        { path: "/pricing", priority: 0.9, changeFrequency: "weekly" },
        { path: "/integrations", priority: 0.85, changeFrequency: "weekly" },
        { path: "/guides", priority: 0.9, changeFrequency: "weekly" },
        { path: "/register", priority: 0.8, changeFrequency: "monthly" },
        { path: "/login", priority: 0.5, changeFrequency: "monthly" },
        { path: "/contact", priority: 0.5, changeFrequency: "monthly" },
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
