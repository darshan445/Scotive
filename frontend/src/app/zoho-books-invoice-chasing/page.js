import Link from "next/link";
import {
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
    MarketingSolveBlock,
} from "@/components/MarketingShell";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/zoho-books-invoice-chasing";
const TITLE = "Zoho Books · Scotive";
const DESCRIPTION =
    "QBO / Xero / Zoho / FreshBooks create invoice, due date, paid/unpaid, books. Existing tools = invoicing + ledger. Scotive = chase on top of that ledger and that inbox. Zoho Books is coming soon. You keep QBO/Xero. We run the chase. $49/month, or $490/year.";

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [],
    alternates: { canonical: absoluteUrl(PATH) },
    robots: { index: false, follow: true },
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

export default function ZohoBooksInvoiceChasingPage() {
    return (
        <MarketingShell testId="seo-zoho-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="Zoho Books · Coming soon"
                title="Not a new books app. You keep QBO/Xero. We run the chase."
                description="QBO / Xero / Zoho / FreshBooks (create invoice, due date, paid/unpaid, books). Existing tools = invoicing + ledger. Scotive = chase on top of that ledger and that inbox. QuickBooks and Xero remind a due date. Scotive reminds a conversation."
            >
                <MarketingHeroCtas
                    primaryLabel="Start 30-day free trial"
                    secondaryHref="/integrations"
                    secondaryLabel="See integrations"
                />
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                <MarketingSolveBlock
                    title="Chase on top of that ledger and that inbox"
                    problem="You already invoiced them. Scotive watches the thread and the open invoice, and handles the next chase."
                    points={[
                        "We match the Gmail/Outlook thread to that invoice so you don't send 'just checking in' on an open reply.",
                        "Reminders pause when they talk back. Accounting reminders don't.",
                        "The next email is in their words, from your address. You approve Firm/Final.",
                        "Pay link in the draft — their existing QBO/Stripe/PayPal/bank pay URL. Scotive is not a payments company.",
                    ]}
                    ctaLabel="Start 30-day free trial"
                />

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">
                        QBO / Xero / Zoho / FreshBooks (create invoice, due date, paid/unpaid, books)
                    </h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Optionally connect invoicing/accounting (QBO, Xero, and others). They keep QBO/Xero as
                        the ledger. Scotive is the chase layer on email + that ledger. Zoho Books is coming soon.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        Live today: connect Gmail or Outlook.{" "}
                        <Link href="/quickbooks-invoice-reminders" className="text-foreground underline underline-offset-2">
                            QuickBooks invoice reminders
                        </Link>
                        : QBO reminds a due date; it does not read the thread.
                    </p>
                </div>

                <div>
                    <pre className="type-body overflow-x-auto rounded-xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground whitespace-pre">{`Client work
 → QBO / Xero / Zoho / FreshBooks (create invoice, due date, paid/unpaid, books)
 → Gmail / Outlook (the actual conversation)
 → Scotive (match thread to invoice, state, cadence, pause, pay link, drafts)`}</pre>
                    <p className="type-body mt-4 text-muted-foreground">
                        Cadence runs Friendly, pauses on reply/promise, pay link in the draft, keep QBO/Xero.
                        $49/month, or $490/year (2 months free). Agency / studio ops or founder, Gmail or Outlook + QBO.
                    </p>
                    <p className="type-body mt-3 text-muted-foreground">
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            Integrations
                        </Link>
                        {" · "}
                        <Link href="/invoice-reminder-software" className="text-foreground underline underline-offset-2">
                            Invoice reminder software
                        </Link>
                        {" · "}
                        <Link href="/freshbooks-invoice-reminders" className="text-foreground underline underline-offset-2">
                            FreshBooks
                        </Link>
                        .
                    </p>
                </div>
            </section>
        </MarketingShell>
    );
}
