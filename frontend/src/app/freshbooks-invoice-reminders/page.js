import { FaqSection } from "@/components/FaqSection";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import { RelatedResources, SeoCard, SeoEyebrow } from "@/components/SeoPage";
import { TRIAL_CTA, TRIAL_LABEL } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/freshbooks-invoice-reminders";
const TITLE = "FreshBooks Invoice Reminders · Scotive";
const DESCRIPTION =
    "FreshBooks invoice reminders know the due date. They do not read the Gmail or Outlook thread. Keep FreshBooks. Scotive matches each invoice to the conversation and drafts the next follow-up. 30-day free trial.";

const FAQS = [
    {
        question: "Do I turn off FreshBooks invoice reminders?",
        answer:
            "You can keep FreshBooks as the invoicing tool. Scotive follows up from Gmail or Outlook on the thread that belongs to that invoice, so you are not stacking a canned FreshBooks note on top of a live conversation.",
    },
    {
        question: "Does Scotive replace FreshBooks?",
        answer:
            "No. You still create invoices and mark them paid in FreshBooks — or QuickBooks or Xero, if that is what you use. Scotive reads those invoices and the matching inbox thread.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: ["freshbooks invoice reminders"],
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

export default function FreshBooksInvoiceRemindersPage() {
    return (
        <MarketingShell testId="seo-freshbooks-invoice-reminders" activePath={PATH}>
            <MarketingHero
                eyebrow="FreshBooks"
                title="FreshBooks invoice reminders know the date — not the thread"
                description="FreshBooks can send automatic invoice reminders when something is late. It cannot see that the client promised Friday in Gmail or Outlook. Keep FreshBooks. Scotive fetches the invoice, reads that conversation, and drafts the next follow-up from your address."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/invoice-reminder-software"
                    secondaryLabel="How the software works"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={1}>What FreshBooks sees</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            FreshBooks invoice reminders vs the inbox
                        </h2>
                        <p className="type-body mt-3">
                            FreshBooks invoice reminders are good at amount, due date, and paid or not. They
                            are blind to the thread where the client actually talks.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">
                        <SeoCard
                            badge="FreshBooks"
                            title="Knows the calendar"
                            detail="Due date passed, send a late reminder. That stamp does not know if they already replied, named a pay date, or said they paid."
                        />
                        <SeoCard
                            badge="Gmail or Outlook"
                            title="Knows what they said"
                            detail="Paying Friday, a missing PO, “we already paid,” a question on scope. Scotive matches that thread to the FreshBooks invoice."
                        />
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
                    <SeoEyebrow index={2}>Why people still chase by hand</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        FreshBooks invoice reminders do not pause
                    </h2>
                    <p className="type-body text-muted-foreground">
                        If the client already replied, the next FreshBooks reminder can still go. Mail from
                        the invoicing tool is also easier to ignore than a note from your Gmail or Outlook
                        address on the thread they already have. You are the one who notices and writes
                        “just checking in.”
                    </p>
                    <p className="type-body text-muted-foreground">
                        Scotive holds when they talk, waits until a promised date, and does not chase once
                        FreshBooks — or QuickBooks or Xero — shows paid. Friendly follow-ups can send on a
                        schedule you approve, with the pay link you already use. Firmer emails wait for a
                        click. {TRIAL_LABEL}.
                    </p>
                </div>
            </section>

            <FaqSection items={FAQS} />
            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Keep FreshBooks. Follow up from your inbox."
                description="Connect Gmail or Outlook and QuickBooks, Xero, or FreshBooks. Scotive drafts the next reminder from what they actually said."
            />
        </MarketingShell>
    );
}
