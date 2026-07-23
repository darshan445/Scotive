/** Long-tail guide posts for SEO (index + sitemap). */

export const GUIDES = [
    {
        slug: "invoice-follow-up-email-templates",
        path: "/guides/invoice-follow-up-email-templates",
        title: "Invoice Follow-Up Email Templates That Don't Sound Awkward",
        description:
            "Copy-paste invoice follow-up and unpaid invoice reminder email templates — friendly, firm, and final — that sound like you, not a collections bot.",
        keywords: [
            "invoice follow up",
            "invoice reminder email template",
            "invoice reminder email sample",
            "invoice follow up email",
        ],
        published: "2026-07-23",
    },
    {
        slug: "polite-reminder-for-unpaid-invoice",
        path: "/guides/polite-reminder-for-unpaid-invoice",
        title: "How to Send a Polite Reminder for an Unpaid Invoice",
        description:
            "A practical unpaid invoice reminder workflow: when to nudge, what to say, and a polite reminder for an unpaid invoice you can send today.",
        keywords: [
            "unpaid invoice reminder",
            "reminder for unpaid invoice",
            "polite invoice reminder",
        ],
        published: "2026-07-23",
    },
    {
        slug: "how-to-follow-up-on-an-invoice-politely",
        path: "/guides/how-to-follow-up-on-an-invoice-politely",
        title: "How to Follow Up on an Invoice Without Sounding Rude",
        description:
            "How to politely follow up on an invoice: timing, tone, and wording that protects the relationship while getting you paid.",
        keywords: [
            "how to politely follow up on an invoice",
            "follow up on invoice politely",
            "polite invoice follow up",
        ],
        published: "2026-07-23",
    },
    {
        slug: "client-said-ill-pay-friday",
        path: "/guides/client-said-ill-pay-friday",
        title: "What to Do When a Client Says “I'll Pay Friday” — and Doesn't",
        description:
            "Broken payment promises are common. Here's how to follow up when a client said they'd pay Friday and didn't — without burning the relationship.",
        keywords: [
            "broken payment promise",
            "client said they would pay",
            "invoice follow up after promise",
        ],
        published: "2026-07-23",
    },
];

export function getGuide(slug) {
    return GUIDES.find((g) => g.slug === slug) || null;
}
