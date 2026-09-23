import Link from "next/link";
import {
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
    MarketingSolveBlock,
} from "@/components/MarketingShell";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/outlook-invoice-chasing";
const TITLE = "Outlook · Scotive";
const DESCRIPTION =
    "Gmail / Outlook is the actual conversation. We match the thread to that invoice so you don't send 'just checking in' on an open reply. Friendly reminders send from your inbox and pause the moment they talk. Firm waits for a click. $49/month, or $490/year.";

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [],
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

export default function OutlookInvoiceChasingPage() {
    return (
        <MarketingShell testId="seo-outlook-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="Chase layer"
                title="Gmail / Outlook (the actual conversation)"
                description="Connect Gmail or Outlook. You already invoiced them. Scotive watches the thread and the open invoice, and handles the next chase. QuickBooks and Xero remind a due date. Scotive reminds a conversation."
            >
                <MarketingHeroCtas
                    primaryLabel="Start 30-day free trial"
                    secondaryHref="/integrations"
                    secondaryLabel="See integrations"
                />
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                <MarketingSolveBlock
                    title="Not a new books app. You keep QBO/Xero. We run the chase."
                    problem="QBO knows it's overdue. It does not know they already replied."
                    points={[
                        "We match the Gmail/Outlook thread to that invoice so you don't send 'just checking in' on an open reply.",
                        "Friendly reminders pause when they talk back. Accounting reminders don't.",
                        "Firm emails wait for your click. Nothing firmer goes out alone.",
                        "Pay link in the draft — their existing QBO/Stripe/PayPal/bank pay URL. Scotive is not a payments company.",
                    ]}
                    ctaLabel="Start 30-day free trial"
                />

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">
                        Chase from the owner&apos;s Gmail/Outlook
                    </h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        QBO / Xero / FreshBooks know amount, due date, paid or not. They do not know the
                        Gmail/Outlook thread. They do not know &quot;Paying Friday,&quot; a dispute, &quot;we
                        already paid,&quot; a missing PO. A canned template from the accounting domain is not the
                        client&apos;s words, from the owner&apos;s inbox.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        Native reminders do not pause when the client replies. They send reminder 2 on top of an
                        open conversation. Scotive: chase from the owner&apos;s Gmail/Outlook; not a third cap of
                        noreply@ accounting mail. &quot;People respond to people.&quot; Sends from the user&apos;s
                        Gmail/Outlook, same thread, same invoice match.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        Client replied → Friendly stops. No &quot;just checking in&quot; on an open conversation.
                        Needs you. You write the next email, then pick a date to check back if they still have
                        not paid. Paid in the books → cadence dies. Never chase someone who paid.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">
                        Chase on top of that ledger and that inbox
                    </h2>
                    <pre className="type-body mt-4 overflow-x-auto rounded-xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground whitespace-pre">{`Client work
 → QBO / Xero / Zoho / FreshBooks (create invoice, due date, paid/unpaid, books)
 → Gmail / Outlook (the actual conversation)
 → Scotive (match thread to invoice, Friendly cadence, pause on reply, pay link, Firm you approve)`}</pre>
                </div>

                <div>
                    <p className="type-body text-muted-foreground">
                        Approved cadence = the user approves the rules once (or per client), not every Friendly
                        email. Typical ladder: before due: short heads-up; due / 1–3 days late: Friendly reminder
                        (can send on the clock); ~7 days: another Friendly; after that: Firm / Final still need a
                        click.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        Cadence runs Friendly, pauses on reply, pay link in the draft, keep QBO/Xero.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        $49/month, or $490/year (2 months free). Charge when there are more than a handful of open invoices. Agency / studio
                        ops or founder, ~8–40 people, B2B retainers, Gmail or Outlook + QBO. Consultant /
                        fractional with 8+ open invoices.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        <Link href="/invoice-reminder-software" className="text-foreground underline underline-offset-2">
                            Invoice reminder software
                        </Link>
                        {" · "}
                        <Link href="/quickbooks-invoice-reminders" className="text-foreground underline underline-offset-2">
                            QuickBooks invoice reminders
                        </Link>
                        {" · "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            Integrations
                        </Link>
                        .
                    </p>
                </div>
            </section>
        </MarketingShell>
    );
}
