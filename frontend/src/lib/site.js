/** Public product facts for marketing chrome. Briefing notes stay off the page. */

export const TRIAL_DAYS = 30;
export const TRIAL_LABEL = "30-day free trial";
export const TRIAL_CTA = "Start free trial";

/** One plan. Primary ICP (agency / consultant with a pile of open invoices). */
export const MONTHLY_PRICE = 29;
/** Standard SaaS annual: 2 months free (pay for 10, get 12) ≈ 17% off. */
export const ANNUAL_MONTHS_FREE = 2;
export const ANNUAL_TOTAL = MONTHLY_PRICE * (12 - ANNUAL_MONTHS_FREE);
export const ANNUAL_EFFECTIVE_MONTHLY = Math.round(ANNUAL_TOTAL / 12);

export const PRICE_AFTER_TRIAL = `Then $${MONTHLY_PRICE}/month, or $${ANNUAL_TOTAL}/year (2 months free).`;
export const PRICE_FOOTER = `$${MONTHLY_PRICE}/month · $${ANNUAL_TOTAL}/year · ${TRIAL_LABEL}`;

export const PLAN_FEATURES = [
    "Connect Gmail or Outlook — or both",
    "QuickBooks, Xero, or FreshBooks",
    "Reminder schedule you approve",
    "Pauses the moment a client replies",
    "You pick when to check back if still unpaid",
    "Payment link in every draft",
    "Firm emails wait for a click",
];

export const EMAIL_INTEGRATIONS = [
    {
        name: "Gmail",
        href: "/invoice-reminder-software",
        blurb: "Send from the thread in your inbox.",
        logo: "/integrations/gmail.svg?v=3",
    },
    {
        name: "Outlook",
        href: "/outlook-invoice-chasing",
        blurb: "Same chase, from Microsoft 365.",
        logo: "/integrations/outlook.svg?v=3",
    },
];

export const ACCOUNTING_INTEGRATIONS = [
    {
        name: "QuickBooks Online",
        href: "/quickbooks-invoice-reminders",
        blurb: "Open invoices, due dates, paid status.",
        logo: "/integrations/quickbooks.svg?v=2",
    },
    {
        name: "Xero",
        href: "/xero-invoice-reminders",
        blurb: "Keep Xero as the ledger.",
        logo: "/integrations/xero.svg?v=2",
    },
    {
        name: "FreshBooks",
        href: "/freshbooks-invoice-reminders",
        blurb: "Open invoices, due dates, paid status.",
        logo: "/integrations/freshbooks.svg?v=2",
    },
];

export const PRODUCT_PATHS = [
    "/invoice-reminder-software",
    "/past-due-invoice-reminder",
    "/payment-reminder-email-template",
    "/how-to-chase-outstanding-invoices",
    "/quickbooks-invoice-reminders",
    "/xero-invoice-reminders",
    "/freshbooks-invoice-reminders",
];
