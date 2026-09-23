/** Shared SEO copy, canonical site URL, and keyword strategy for Scotive marketing. */

/**
 * Canonical public origin. Always prefer www for production scotive.com so
 * metadata/sitemap/robots match Vercel (apex → www redirect).
 * Localhost and other hosts are left unchanged.
 */
export function normalizePublicSiteUrl(raw) {
    const fallback = "https://www.scotive.com";
    const input = (raw || fallback).trim();
    try {
        const u = new URL(input);
        if (u.hostname === "scotive.com") {
            u.hostname = "www.scotive.com";
        }
        // Strip trailing slash from origin
        return u.origin.replace(/\/$/, "");
    } catch {
        return fallback;
    }
}

export const SITE_URL = normalizePublicSiteUrl(
    process.env.NEXT_PUBLIC_SITE_URL || "https://www.scotive.com",
);

/** Pack §7.2 pass order, then §7.1 supporting terms. Chase layer, not AR / invoicing. */
export const PRIMARY_KEYWORDS = [
    "past due invoice reminder",
    "invoice reminder software",
    "payment reminder software",
    "automated invoice reminders",
    "overdue invoice reminder email",
    "past due invoice email",
    "payment reminder email template",
    "outstanding payment reminder",
    "how to chase outstanding invoices",
    "invoice follow up email",
    "quickbooks invoice reminders",
    "quickbooks automatic invoice reminders",
    "xero invoice reminders",
    "freshbooks invoice reminders",
    "unpaid invoice reminder",
    "automated invoice follow up",
    "invoice chasing software",
];

export const DEFAULT_TITLE = "Scotive — Get paid without the awkward follow-up";

export const DEFAULT_DESCRIPTION =
    "Get paid without the awkward follow-up. Scotive matches each open invoice from QuickBooks, Xero, or FreshBooks to the Gmail or Outlook thread, sends Friendly reminders you approve, and pauses the moment they reply. Firm emails wait for a click. 30-day free trial.";

/** Pack §5.2 — who pays. Not “anyone who bills.” */
export const AUDIENCE_BLURB =
    "Agency / studio ops or founder, ~8–40 people, B2B retainers, Gmail or Outlook + QBO. Consultant / fractional with 8+ open invoices.";

export const AUDIENCE_SHORT =
    "Agency / studio ops or founder; consultant with 8+ open invoices";

export function absoluteUrl(path = "/") {
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${SITE_URL}${p === "/" ? "" : p}`;
}

export function pageMetadata({
    title,
    description,
    path,
    keywords = [],
    noindex = false,
}) {
    const fullTitle = title.includes("Scotive") ? title : `${title} · Scotive`;
    const canonical = absoluteUrl(path);
    return {
        title: { absolute: fullTitle },
        description,
        keywords,
        alternates: { canonical },
        robots: noindex
            ? { index: false, follow: true }
            : { index: true, follow: true },
        openGraph: {
            url: canonical,
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
