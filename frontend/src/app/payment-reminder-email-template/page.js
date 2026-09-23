import Link from "next/link";
import { FaqSection } from "@/components/FaqSection";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import { EmailTemplate, RelatedResources, SeoEyebrow } from "@/components/SeoPage";
import { PRICE_AFTER_TRIAL, TRIAL_CTA, TRIAL_LABEL } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/payment-reminder-email-template";
const TITLE = "Payment Reminder Email Template · Scotive";
const DESCRIPTION =
    "Payment reminder email templates with invoice number, amount, due date, and a payment link. Use them for a heads-up before due, then let Scotive draft from the Gmail or Outlook thread. 30-day free trial.";

const FAQS = [
    {
        question: "Should I send these if they already replied?",
        answer:
            "No. If they already replied, do not paste another reminder on that thread. Scotive pauses Friendly and waits for you.",
    },
    {
        question: "Where does the payment link come from?",
        answer:
            "Use the pay URL you already have in QuickBooks, Xero, FreshBooks, Stripe, PayPal, or your bank. Scotive puts that existing link in the draft. It is not a payments company.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [
        "payment reminder email template",
        "outstanding payment reminder",
        "unpaid invoice reminder",
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

export default function PaymentReminderEmailTemplatePage() {
    return (
        <MarketingShell testId="seo-payment-reminder-email-template" activePath={PATH}>
            <MarketingHero
                eyebrow="Templates"
                title="Payment reminder email template"
                description="Copy these for a short heads-up before due, or an outstanding payment reminder a few days later. Every one includes invoice number, amount, due date, and a payment link. If you have a pile of open invoices, Scotive writes the next one from the Gmail or Outlook thread instead of you pasting."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/past-due-invoice-reminder"
                    secondaryLabel="Past due wording"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
                    <SeoEyebrow index={1}>What to include</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        Four things every payment reminder should have
                    </h2>
                    <ul className="mt-6 space-y-2 type-body text-muted-foreground list-disc pl-5">
                        <li>Invoice number</li>
                        <li>Amount</li>
                        <li>Due date</li>
                        <li>A payment link they already know how to use</li>
                    </ul>
                    <p className="type-body mt-4 text-muted-foreground">
                        Swap the examples (INV-2041, $2,400, Sarah) for yours. Send from your own Gmail or
                        Outlook address — people ignore mail from the invoicing-tool domain.
                    </p>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
                    <div>
                        <SeoEyebrow index={2}>Copy and send</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">Three templates</h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            These stay friendly. Overdue situations that need more context live on the{" "}
                            <Link
                                href="/past-due-invoice-reminder"
                                className="text-foreground underline underline-offset-2"
                            >
                                past due invoice reminder
                            </Link>{" "}
                            page.
                        </p>
                    </div>

                    <EmailTemplate
                        label="Before due — short heads-up"
                        subject="Invoice INV-2041 is due Friday"
                        body={`Hi Sarah,

A quick heads-up that invoice INV-2041 for $2,400 is due this Friday, 18 April.

You can pay here: [payment link]

Thanks,
Alex`}
                    />

                    <EmailTemplate
                        label="Outstanding payment reminder — due date just passed"
                        subject="Friendly reminder on INV-2041 ($2,400)"
                        body={`Hi Sarah,

Just a friendly reminder that invoice INV-2041 for $2,400 was due Friday, 18 April.

If it is already on a payment run, you can ignore this. Otherwise you can pay here: [payment link]

Thanks,
Alex`}
                    />

                    <EmailTemplate
                        label="Unpaid invoice reminder — still friendly"
                        subject="Following up on INV-2041"
                        body={`Hi Sarah,

Following up on invoice INV-2041 for $2,400, due 18 April, which is still open on our side.

Happy to resend the invoice or the payment link if that helps: [payment link]

Thanks,
Alex`}
                    />
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
                    <SeoEyebrow index={3}>When not to paste these</SeoEyebrow>
                    <h2 className="type-title text-3xl md:text-4xl">
                        Skip the template if they already talked
                    </h2>
                    <p className="type-body text-muted-foreground">
                        If they already replied, named a pay date, said they paid, or paid in part, a generic
                        outstanding payment reminder is the wrong email. That is when a dated reminder from
                        QuickBooks, Xero, or FreshBooks feels dumb — and when Scotive pauses Friendly and
                        puts the invoice in Needs you.
                    </p>
                    <p className="type-body text-muted-foreground">
                        One late invoice: paste a template. A pile of open invoices:{" "}
                        {TRIAL_LABEL.toLowerCase()}. {PRICE_AFTER_TRIAL}
                    </p>
                </div>
            </section>

            <FaqSection items={FAQS} />
            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Stop pasting the same reminder."
                description="Scotive drafts the next payment reminder from that client’s own words, puts your pay link in, and pauses when they reply."
            />
        </MarketingShell>
    );
}
