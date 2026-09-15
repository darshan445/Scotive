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
    "Invoice reminder software that reads the Gmail or Outlook thread on each invoice from QuickBooks, Xero, or FreshBooks. Automated reminders pause when the client replies or promises a date. 30-day free trial.";

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
            "The reminder schedule pauses. If they promised a date, Scotive waits until that date. If they asked a question, disputed the invoice, or said they already paid, it waits for you.",
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
                description="Scotive fetches invoices from invoicing tools like QuickBooks, Xero, or FreshBooks. For each one, it reads the Gmail or Outlook thread, tracks where it stands, and drafts a personalized follow-up in their words."
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
                            client said in Gmail or Outlook, so they cannot tell promised from ignored, or
                            “we already paid” from still unpaid.
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
                            title="Overdue is not a status"
                            detail="Promised, disputed, says-paid, waiting on your reply — none of that lives in the reminder calendar."
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
                            title="The thread is the context"
                            detail="Promised Friday, a PO question, and “we already paid” are different states — not the same overdue stamp."
                        />
                        <SeoCard
                            badge="02"
                            title="The next email is already drafted"
                            detail="Written from what that client actually said. You review it. One click sends from your address."
                        />
                        <SeoCard
                            badge="03"
                            title="It knows when to hold"
                            detail="If they replied or named a pay date, the chase waits. Firmer emails still need a click."
                        />
                        <SeoCard
                            badge="04"
                            title="Status from the conversation"
                            detail="Each invoice has a state from invoiced to paid, so you are not rebuilding it from sent mail."
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
                            If they reply, the schedule holds. If they promise a day, it waits until that day.
                            If they dispute, say they paid, or need an answer from you, it waits. When the
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
                description="Invoice reminder software that drafts the next email in their words — from Gmail or Outlook, on invoices from QuickBooks, Xero, or FreshBooks."
            />
        </MarketingShell>
    );
}
