import Link from "next/link";
import { FaqSection } from "@/components/FaqSection";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import { RelatedResources, SeoCard, SeoEyebrow } from "@/components/SeoPage";
import { PRICE_AFTER_TRIAL, TRIAL_CTA } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/invoice-reminder-software";
const TITLE = "Invoice Reminder Software · Scotive";
const DESCRIPTION =
    "Invoice reminder software that matches each open invoice from QuickBooks, Xero, or FreshBooks to the Gmail or Outlook thread. Friendly reminders send from your inbox and pause the moment they reply. Firm waits for a click. 30-day free trial.";

const FAQS = [
    {
        question: "Is this a replacement for QuickBooks, Xero, or FreshBooks?",
        answer:
            "No. Those stay your invoicing tools. Scotive sits on top: it matches each open invoice to the Gmail or Outlook thread and runs the follow-up from your address.",
    },
    {
        question: "Will it send every reminder on its own?",
        answer:
            "Friendly reminders can go out on the schedule you approve. Anything firmer waits for a click.",
    },
    {
        question: "What happens when a client replies?",
        answer:
            "Friendly reminders stop. The invoice moves to Needs you. You write the next email, then pick a date to check back if they still have not paid. Scotive does not send another ‘just checking in’ on an open conversation.",
    },
];

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [
        "invoice reminder software",
        "payment reminder software",
        "automated invoice reminders",
        "invoice chasing software",
        "automated invoice follow up",
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

export default function InvoiceReminderSoftwarePage() {
    return (
        <MarketingShell testId="seo-invoice-reminder-software" activePath={PATH}>
            <MarketingHero
                eyebrow="Software"
                title="Invoice reminder software that reads the conversation"
                description="Scotive matches each open invoice from QuickBooks, Xero, or FreshBooks to the Gmail or Outlook thread, sends Friendly reminders you approve, and pauses the moment they reply. Firm emails wait for a click."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/pricing"
                    secondaryLabel="View pricing"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={1}>The gap</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Your invoicing tools already send reminders — they only know the date.
                        </h2>
                        <p className="type-body mt-3">
                            QuickBooks, Xero, and FreshBooks can fire a note on day 7. They cannot see what the
                            client said in Gmail or Outlook, so they keep sending after the client already
                            talked — and they never write the next email from your inbox.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <SeoCard
                            title="A calendar is not context"
                            detail="Day 7 overdue is not the same as “paying Friday,” a PO question, or “we already paid.” Date-based reminders treat all of those as the same stamp."
                        />
                        <SeoCard
                            title="The canned note still leaves you writing"
                            detail="The invoicing tool sends from its own domain. You are still in Gmail or Outlook guessing “just checking in” — and waiting weeks because it feels awkward."
                        />
                        <SeoCard
                            title="They do not know when to stop"
                            detail="If the client already replied, the next dated reminder still goes. You are the one who has to notice and pull it back."
                        />
                        <SeoCard
                            title="After they talk, you are the system"
                            detail="A reply, a pay date they named, or “we already paid” is not on the reminder calendar. You rebuild the next chase from sent mail."
                        />
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-12">
                        <SeoEyebrow index={2}>What Scotive does</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Match the thread to that invoice. Then run the next follow-up from your inbox.
                        </h2>
                        <p className="type-body mt-3">
                            Connect Gmail or Outlook — or both — and QuickBooks, Xero, or FreshBooks. Scotive
                            pulls the invoices, then the conversations that belong to them.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <SeoCard
                            badge="01"
                            title="The thread is the brake"
                            detail="A reply, a pay date they named, or “we already paid” is not another overdue stamp. Friendly stops so you are not the one who has to notice."
                        />
                        <SeoCard
                            badge="02"
                            title="The next email is already drafted"
                            detail="Friendly reminders go from your address, on the same thread, with a pay link. When they reply, you write the next email."
                        />
                        <SeoCard
                            badge="03"
                            title="It knows when to hold"
                            detail="If they replied, Friendly stops. You pick a date to check back if still unpaid. Firm emails still need a click."
                        />
                        <SeoCard
                            badge="04"
                            title="Needs you, Watching, or Paid"
                            detail="Replies and Firm sit in Needs you. A check-back date sits in Watching. Paid in the books ends the chase."
                        />
                    </div>
                </div>
            </section>

            <section className="py-16 md:py-20 border-t border-border/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                    <div>
                        <SeoEyebrow index={3}>Payment reminder software</SeoEyebrow>
                        <h2 className="type-title text-3xl md:text-4xl">
                            Payment reminder software that sits on the tools you already use
                        </h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            You keep QuickBooks, Xero, or FreshBooks for creating invoices, due dates, and
                            paid or not. Scotive is the follow-up layer on Gmail or Outlook: same thread, same
                            invoice, a payment link from the tool you already use — not a new place to get paid.
                        </p>
                    </div>
                    <div>
                        <h2 className="type-title text-3xl md:text-4xl">Automated invoice reminders — with a brake</h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            You approve the friendly schedule once. A short heads-up before due. A reminder
                            around due date. Another a few days later. After that, firmer emails wait for you —
                            a bot that keeps nagging after someone already talked starts to hurt the relationship.
                        </p>
                        <p className="type-body mt-3 text-muted-foreground">
                            If they reply, Friendly stops and the invoice moves to Needs you. You write the
                            next email, then pick a date to check back if they still have not paid. When the
                            invoicing tool shows paid, the chase stops.
                        </p>
                    </div>
                    <p className="type-body text-sm text-muted-foreground">
                        {PRICE_AFTER_TRIAL} See{" "}
                        <Link href="/pricing" className="text-foreground underline underline-offset-2">
                            pricing
                        </Link>
                        .
                    </p>
                </div>
            </section>

            <FaqSection items={FAQS} />
            <RelatedResources currentPath={PATH} />
            <MarketingCta
                title="Get paid without the awkward follow-up."
                description="Invoice reminder software that sends Friendly reminders from Gmail or Outlook, pauses the moment they reply, and waits for your click on anything firmer."
            />
        </MarketingShell>
    );
}
