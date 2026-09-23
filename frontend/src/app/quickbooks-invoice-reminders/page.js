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

const PATH = "/quickbooks-invoice-reminders";
const TITLE = "QuickBooks Invoice Reminders · Scotive";
const DESCRIPTION =
    "QuickBooks invoice reminders know the due date. They do not read the Gmail or Outlook thread. Keep QuickBooks Online. Scotive matches each invoice to the conversation and drafts the next follow-up. 30-day free trial.";

const FAQS = [
    {
        question: "Do I turn off QuickBooks automatic invoice reminders?",
        answer:
            "You can keep QuickBooks as the invoicing tool. Scotive follows up from Gmail or Outlook on the thread that belongs to that invoice, so you are not stacking a canned QuickBooks note on top of a live conversation.",
    },
    {
        question: "Does Scotive replace QuickBooks?",
        answer:
            "No. You still create invoices and mark them paid in QuickBooks — or Xero or FreshBooks, if that is what you use. Scotive reads those invoices and the matching inbox thread.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [
        "quickbooks invoice reminders",
        "quickbooks automatic invoice reminders",
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

export default function QuickBooksInvoiceRemindersPage() {
    return (
        <MarketingShell testId="seo-quickbooks-invoice-reminders" activePath={PATH}>
            <MarketingHero
                eyebrow="QuickBooks"
                title="QuickBooks invoice reminders know the date — not the thread"
                description="QuickBooks Online can send automatic invoice reminders on a schedule. It cannot see that the client already replied in Gmail or Outlook. Keep QuickBooks. Scotive matches the thread, sends Friendly reminders from your address, and pauses the moment they talk."
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
                        <SeoEyebrow index={1}>What QuickBooks sees</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Automatic invoice reminders vs the inbox
                        </h2>
                        <p className="type-body mt-3">
                            QuickBooks invoice reminders are good at amount, due date, and paid or not. They
                            are blind to the thread where the work actually happens.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-2 gap-4">
                        <SeoCard
                            badge="QuickBooks"
                            title="Knows the calendar"
                            detail="Due date passed, reminder 1, reminder 2. If automatic sending glitches, you may think reminders went out when they did not — people still have to check invoice history."
                        />
                        <SeoCard
                            badge="Gmail or Outlook"
                            title="Knows what they said"
                            detail="Paying Friday, a missing PO, “we already paid,” a question on scope. None of that is a due-date stamp. Scotive matches that thread to the QuickBooks invoice."
                        />
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
                    <SeoEyebrow index={2}>Why people still chase by hand</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        QuickBooks automatic invoice reminders do not pause
                    </h2>
                    <p className="type-body text-muted-foreground">
                        If the client already replied, the next QuickBooks reminder can still fire. You are
                        the one who notices. Scotive pauses Friendly when they talk, puts the invoice in
                        Needs you, and does not chase once QuickBooks — or Xero or FreshBooks — shows paid.
                    </p>
                    <p className="type-body text-muted-foreground">
                        Friendly follow-ups can send on a schedule you approve, from your Gmail or Outlook
                        address, with the pay link you already use. Firmer emails wait for a click.{" "}
                        {TRIAL_LABEL}.
                    </p>
                </div>
            </section>

            <FaqSection items={FAQS} />
            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Keep QuickBooks. Follow up from your inbox."
                description="Connect Gmail or Outlook and QuickBooks, Xero, or FreshBooks. Scotive sends Friendly reminders from your inbox and pauses the moment they reply."
            />
        </MarketingShell>
    );
}
