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

const PATH = "/xero-invoice-reminders";
const TITLE = "Xero Invoice Reminders · Scotive";
const DESCRIPTION =
    "Xero invoice reminders cap out and send from xero.com. Keep Xero for invoicing. Scotive follows up from Gmail or Outlook on the thread for that invoice. 30-day free trial.";

const FAQS = [
    {
        question: "Should I turn Xero reminders off?",
        answer:
            "You can keep Xero as the invoicing tool. Scotive sends from your Gmail or Outlook address on the matching thread, so clients are not getting another note from xero.com on top of a live conversation.",
    },
    {
        question: "Does Scotive replace Xero?",
        answer:
            "No. Create invoices and record payment in Xero — or QuickBooks or FreshBooks. Scotive matches each open invoice to the inbox thread and drafts the next follow-up.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: ["xero invoice reminders"],
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

export default function XeroInvoiceRemindersPage() {
    return (
        <MarketingShell testId="seo-xero-invoice-reminders" activePath={PATH}>
            <MarketingHero
                eyebrow="Xero"
                title="Xero invoice reminders stop — and they are not from your inbox"
                description="Xero can send a handful of automatic reminders, then go quiet. Those emails come from xero.com, which people ignore or filter. Keep Xero. Scotive reads the Gmail or Outlook thread on that invoice and drafts the next follow-up from your address."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/invoice-reminder-software"
                    secondaryLabel="Invoice reminder software"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={1}>Where Xero reminders fall short</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            A cap, a calendar, and the wrong sender
                        </h2>
                        <p className="type-body mt-3">
                            Xero invoice reminders know due date and paid or not. They do not know the
                            conversation, and they are not unlimited.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-3 gap-4">
                        <SeoCard
                            title="They cap out"
                            detail="Xero stops after a set number of automatic reminders. If invoices routinely take more nudges than that, the calendar goes silent while the invoice is still open."
                        />
                        <SeoCard
                            title="They send from xero.com"
                            detail="Mail from the invoicing domain is easier to ignore or filter. People respond to a person — your Gmail or Outlook address — on the thread they already have."
                        />
                        <SeoCard
                            title="They do not pause"
                            detail="If the client already replied, the next Xero reminder can still go. Scotive pauses Friendly and waits for you."
                        />
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
                    <SeoEyebrow index={2}>Keep Xero</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        Invoices stay in Xero. Follow-up runs from Gmail or Outlook.
                    </h2>
                    <p className="type-body text-muted-foreground">
                        Connect Xero — or QuickBooks or FreshBooks — plus Gmail or Outlook. Scotive matches
                        each invoice to its thread, sends Friendly reminders you approve, pauses the moment
                        they reply, and puts your existing pay link in the draft. Firmer emails wait for a click.
                    </p>
                    <p className="type-body text-muted-foreground">{TRIAL_LABEL}.</p>
                </div>
            </section>

            <FaqSection items={FAQS} />
            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Keep Xero. Follow up from your inbox."
                description="Scotive drafts the next reminder from what they said in Gmail or Outlook — and pauses when they talk back."
            />
        </MarketingShell>
    );
}
