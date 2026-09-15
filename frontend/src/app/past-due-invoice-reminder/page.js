import Link from "next/link";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import { RelatedResources, SeoCard, SeoEyebrow } from "@/components/SeoPage";
import { TRIAL_CTA, TRIAL_LABEL } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/past-due-invoice-reminder";
const TITLE = "Past Due Invoice Reminder · Scotive";
const DESCRIPTION =
    "A past due invoice reminder should match what the client said — promised Friday, already paid, a dispute — not another overdue stamp from QuickBooks, Xero, or FreshBooks. Scotive reads the Gmail or Outlook thread. 30-day free trial.";

const STATES = [
    {
        title: "I'll pay Friday",
        detail:
            "They named a date. Hold the reminder until that date. Sending “this is overdue” while they already promised a day is how you look like you are not listening.",
    },
    {
        title: "Promised and didn’t",
        detail:
            "That date passed and nothing landed. This needs you — not another generic past due invoice email. A firmer follow-up still waits for a click.",
    },
    {
        title: "Says paid",
        detail:
            "They said they paid. That is not the same as payment showing in QuickBooks, Xero, or FreshBooks. Mixing those up is how you get another week of back-and-forth.",
    },
    {
        title: "Partial",
        detail:
            "Some money in, a balance still open. A “full amount overdue” reminder is the wrong email. The useful question is what is still unpaid — and why.",
    },
    {
        title: "After they replied",
        detail:
            "If they already answered, do not send another “just checking in” on that thread. The past due reminder pauses until you have handled their question.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [
        "past due invoice reminder",
        "overdue invoice reminder email",
        "past due invoice email",
    ],
    alternates: { canonical: absoluteUrl(PATH) },
    robots: { index: true, follow: true },
    openGraph: {
        url: absoluteUrl(PATH),
        title: TITLE,
        description: DESCRIPTION,
        type: "website",
        siteName: "Scotive",
    },
    twitter: {
        card: "summary_large_image",
        title: TITLE,
        description: DESCRIPTION,
    },
};

export default function PastDueInvoiceReminderPage() {
    return (
        <MarketingShell testId="seo-past-due-reminder" activePath={PATH}>
            <MarketingHero
                eyebrow="Past due"
                title="Past due invoice reminder"
                description="When the due date has passed, the next email should know what they said — not only that it is late. Scotive reads the Gmail or Outlook thread on that invoice from QuickBooks, Xero, or FreshBooks, then drafts the overdue follow-up in their words."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/payment-reminder-email-template"
                    secondaryLabel="See email templates"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                    <SeoEyebrow index={1}>The problem</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        An overdue stamp is not an overdue invoice reminder email
                    </h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        QuickBooks, Xero, and FreshBooks know the due date. They send the same past due invoice
                        email whether the client promised Friday, asked about a PO, or already wrote back. That
                        is why people still open Gmail or Outlook and type “just checking in.”
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        A useful past due invoice reminder names the invoice, the amount, the due date, and a
                        way to pay — and it does not land on top of an open conversation.
                    </p>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={2}>What actually happened</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Five situations a dated reminder treats as the same
                        </h2>
                        <p className="type-body mt-3">
                            Scotive sets a state from the thread, then holds or drafts accordingly.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {STATES.map((item) => (
                            <SeoCard key={item.title} title={item.title} detail={item.detail} />
                        ))}
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
                    <SeoEyebrow index={3}>Not a collections letter</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">This is not a late payment notice</h2>
                    <p className="type-body text-muted-foreground">
                        A 90-day late payment notice is a collections letter. Scotive is the follow-up before
                        that: friendly reminders on a schedule you approve, firmer emails when you click, and a
                        stop when they talk — or when QuickBooks, Xero, or FreshBooks shows paid.
                    </p>
                    <p className="type-body text-muted-foreground">
                        For softer, before-due wording, use the{" "}
                        <Link
                            href="/payment-reminder-email-template"
                            className="text-foreground underline underline-offset-2"
                        >
                            payment reminder email template
                        </Link>
                        . {TRIAL_LABEL}.
                    </p>
                </div>
            </section>

            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Send the past due email that matches the thread."
                description="Scotive tracks promised, says-paid, disputed, and waiting on you — then drafts the next overdue invoice reminder from Gmail or Outlook."
            />
        </MarketingShell>
    );
}
