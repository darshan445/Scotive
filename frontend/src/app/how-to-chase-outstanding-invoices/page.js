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

const PATH = "/how-to-chase-outstanding-invoices";
const TITLE = "How to Chase Outstanding Invoices · Scotive";
const DESCRIPTION =
    "How to chase outstanding invoices without relying on memory: one next follow-up per invoice, pause when they reply, and write the invoice follow-up email from Gmail or Outlook. 30-day free trial.";

const STEPS = [
    {
        title: "Give every unpaid invoice a next date",
        detail:
            "Do not rely on remembering who you emailed last week. Before due, a short heads-up. Around due, a friendly reminder. A few days later, another. After that, something firmer — but only when you mean it.",
    },
    {
        title: "Match the email to that invoice",
        detail:
            "The conversation lives in Gmail or Outlook. The amount and due date live in QuickBooks, Xero, or FreshBooks. If those stay in two piles, you will send “just checking in” on a thread that already answered you.",
    },
    {
        title: "Pause when they talk",
        detail:
            "A reply is not a cue for the next dated reminder. Friendly stops. The invoice moves to Needs you. You write the next email, then pick a date to check back if they still have not paid — not another canned nudge.",
    },
    {
        title: "Write the invoice follow-up email from what they said",
        detail:
            "Include invoice number, amount, due date, and a payment link. Then answer the last thing they actually wrote. People reply to people, not to mail from the invoicing-tool domain.",
    },
    {
        title: "Know when email is no longer enough",
        detail:
            "If they have gone quiet for a long stretch, a call to AP or pausing work may be the next step. Email cadence helps you get there with a record. It does not replace the phone.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: ["how to chase outstanding invoices", "invoice follow up email"],
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

export default function HowToChaseOutstandingInvoicesPage() {
    return (
        <MarketingShell testId="seo-how-to-chase-outstanding" activePath={PATH}>
            <MarketingHero
                eyebrow="How to"
                title="How to chase outstanding invoices"
                description="If you already send invoices and still follow up from Gmail or Outlook, the work is not “create another invoice.” It is knowing who owes what, what they said, and what to send next — without scrolling sent mail every week."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/invoice-reminder-software"
                    secondaryLabel="See the software"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={1}>A cadence you can keep</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Five steps that work when you have a pile of open invoices
                        </h2>
                        <p className="type-body mt-3">
                            Built for agencies and consultants who already use QuickBooks, Xero, or FreshBooks
                            and still write follow-ups by hand. One or two late invoices: a{" "}
                            <Link
                                href="/payment-reminder-email-template"
                                className="text-foreground underline underline-offset-2"
                            >
                                template
                            </Link>{" "}
                            is enough.
                        </p>
                    </div>
                    <div className="space-y-4">
                        {STEPS.map((step, i) => (
                            <SeoCard
                                key={step.title}
                                badge={String(i + 1).padStart(2, "0")}
                                title={step.title}
                                detail={step.detail}
                            />
                        ))}
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                    <SeoEyebrow index={2}>Invoice follow-up email</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        What the next invoice follow-up email should do
                    </h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Stay on the same thread. Name the invoice. Include a pay link. Answer their last
                        message if they sent one. Ready-to-copy wording for before due and just after due is
                        on the{" "}
                        <Link
                            href="/payment-reminder-email-template"
                            className="text-foreground underline underline-offset-2"
                        >
                            payment reminder email template
                        </Link>{" "}
                        page. For after they replied, promised Friday, or said they paid, see{" "}
                        <Link
                            href="/past-due-invoice-reminder"
                            className="text-foreground underline underline-offset-2"
                        >
                            past due invoice reminder
                        </Link>
                        .
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        Scotive does the matching and the chase: invoices from your invoicing tools, conversation
                        from Gmail or Outlook, Friendly reminders from your address. They pause the moment someone
                        replies. Firmer ones wait for a click. {TRIAL_LABEL}.
                    </p>
                </div>
            </section>

            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Stop chasing from memory."
                description="Connect Gmail or Outlook plus QuickBooks, Xero, or FreshBooks. Every outstanding invoice gets a next chase — Friendly on a clock, pause when they reply, Firm when you click."
            />
        </MarketingShell>
    );
}
