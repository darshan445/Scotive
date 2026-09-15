/** Search landing pages listed on /guides and in Resources. Not a blog. */

export const RESOURCE_LINKS = [
    {
        path: "/invoice-reminder-software",
        title: "Invoice reminder software",
        navLabel: "Invoice reminder software",
        description:
            "Follow-ups from Gmail or Outlook, matched to invoices from QuickBooks, Xero, or FreshBooks — pausing when the client replies.",
    },
    {
        path: "/past-due-invoice-reminder",
        title: "Past due invoice reminder",
        navLabel: "Past due reminder",
        description:
            "When the due date passed, the next email should know if they promised Friday, said they paid, or already replied.",
    },
    {
        path: "/payment-reminder-email-template",
        title: "Payment reminder email template",
        navLabel: "Email templates",
        description:
            "Copy-paste reminder emails with invoice number, amount, due date, and a payment link — plus when not to send them.",
    },
    {
        path: "/how-to-chase-outstanding-invoices",
        title: "How to chase outstanding invoices",
        navLabel: "How to chase invoices",
        description:
            "A simple follow-up cadence for agencies and consultants with a pile of open invoices — not a memory exercise.",
    },
    {
        path: "/quickbooks-invoice-reminders",
        title: "QuickBooks invoice reminders",
        navLabel: "QuickBooks reminders",
        description:
            "QuickBooks knows the due date. It does not read the Gmail or Outlook thread. Keep QuickBooks; follow up from your inbox.",
    },
    {
        path: "/xero-invoice-reminders",
        title: "Xero invoice reminders",
        navLabel: "Xero reminders",
        description:
            "Xero reminders cap out and send from xero.com. Keep Xero; Scotive follows up from Gmail or Outlook.",
    },
    {
        path: "/freshbooks-invoice-reminders",
        title: "FreshBooks invoice reminders",
        navLabel: "FreshBooks reminders",
        description:
            "FreshBooks knows the due date. It does not read the Gmail or Outlook thread. Keep FreshBooks; follow up from your inbox.",
    },
];

/** @deprecated Use RESOURCE_LINKS */
export const GUIDE_LINKS = RESOURCE_LINKS;

export function relatedResources(currentPath) {
    return RESOURCE_LINKS.filter((item) => item.path !== currentPath);
}
