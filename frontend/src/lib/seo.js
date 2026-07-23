/** Shared SEO copy & keyword strategy for Scotive marketing pages. */

export const SITE_URL = (
    process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com"
).replace(/\/$/, "");

/** Primary + competitor-overlap keywords (Chaser/Upflow/PaidChaser style). */
export const PRIMARY_KEYWORDS = [
    "invoice chasing software",
    "chase unpaid invoices",
    "accounts receivable automation",
    "overdue invoice tracker",
    "overdue invoice reminder",
    "payment follow-up software",
    "invoice tracking tool",
    "AR collections software",
    "accounts receivable follow up",
    "unpaid invoice reminder",
    "invoice to cash",
    "automated invoice reminders",
];

/** Competitor-overlap terms (Chaser, Upflow, Gaviti, PaidChaser, ChaseAI). */
export const COMPETITOR_KEYWORDS = [
    "Chaser alternative",
    "Upflow alternative",
    "invoice collection software",
    "accounts receivable software for freelancers",
    "accounts receivable software for agencies",
    "payment reminder software",
];

export const INTEGRATION_KEYWORDS = [
    "Gmail invoice tracker",
    "Outlook invoice chasing",
    "QuickBooks invoice chasing",
    "QuickBooks Online AR",
    "Zoho Books collections",
    "FreshBooks payment follow up",
];

export const DEFAULT_DESCRIPTION =
    "Scotive is invoice chasing software that tracks unpaid invoices from your email and accounting tools — reads client replies for promises and disputes, and drafts follow-ups you approve before send. Gmail and QuickBooks Online today; Outlook, Zoho Books, and FreshBooks next.";

export const DEFAULT_TITLE =
    "Scotive — Invoice Chasing Software to Get Paid Faster";

/** Who Scotive is for — keep marketing copy broad, not freelancer-only. */
export const AUDIENCE_BLURB =
    "For freelancers, agencies, consultants, professional services, and any team that bills clients and chases payment.";

export const AUDIENCE_SHORT =
    "freelancers, agencies, and teams that bill clients";

export function absoluteUrl(path = "/") {
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${SITE_URL}${p === "/" ? "" : p}`;
}

export function pageMetadata({
    title,
    description,
    path,
    keywords = [],
}) {
    const fullTitle = title.includes("Scotive") ? title : `${title} · Scotive`;
    const kw = [
        ...new Set([
            ...PRIMARY_KEYWORDS,
            ...INTEGRATION_KEYWORDS,
            ...COMPETITOR_KEYWORDS,
            ...keywords,
        ]),
    ];
    return {
        title: { absolute: fullTitle },
        description,
        keywords: kw,
        alternates: { canonical: path },
        openGraph: {
            url: path,
            title: fullTitle,
            description,
            type: "website",
            siteName: "Scotive",
        },
        twitter: {
            card: "summary_large_image",
            title: fullTitle,
            description,
        },
    };
}
