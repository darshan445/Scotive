import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "How to Chase Unpaid Invoices Without Awkward Emails | Scotive",
    description:
        "Chase unpaid invoices with a ledger that updates from email replies and accounting tools. Scotive drafts follow-ups for promises, disputes, and overdue balances — you approve every send.",
    path: "/chase-unpaid-invoices",
    keywords: ["chase unpaid invoices", "how to chase unpaid invoices", "overdue invoice follow up"],
});

export default function ChaseUnpaidInvoicesPage() {
    return (
        <MarketingShell testId="seo-chase-unpaid" activePath="/chase-unpaid-invoices">
            <MarketingHero
                eyebrow="Chase unpaid invoices"
                title="A calmer way to follow up on money you’re owed"
                description="Late payments aren’t a character flaw — they’re an ops problem. Scotive turns scattered sent mail and accounting invoices into a prioritized “needs you today” list."
            />

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Who chases unpaid invoices with Scotive</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Freelancers, agencies, consultants, studios, professional services, and small businesses —
                        anyone whose cash flow depends on clients paying invoices on time.
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Why unpaid invoices slip</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Promises live in reply chains. Disputes change the amount. Accounting shows open balances
                        while your inbox holds the story. Chasing unpaid invoices manually means reconstructing
                        that story every week.
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">A practical chase workflow</h2>
                    <ol className="mt-4 space-y-4 type-body text-muted-foreground list-decimal pl-5">
                        <li>
                            <strong className="text-foreground">Detect or import</strong> — invoices from email
                            and/or QuickBooks Online (more accounting tools coming).
                        </li>
                        <li>
                            <strong className="text-foreground">Read replies</strong> — promises, disputes, and
                            “says paid” claims update status automatically.
                        </li>
                        <li>
                            <strong className="text-foreground">Approve the nudge</strong> — state-aware drafts
                            (friendly → firm → final) you edit and send from your own mailbox.
                        </li>
                    </ol>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Related</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Looking for the category page? See{" "}
                        <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                            invoice chasing software
                        </Link>
                        . Using QuickBooks?{" "}
                        <Link href="/quickbooks-invoice-chasing" className="text-foreground underline underline-offset-2">
                            QuickBooks invoice chasing
                        </Link>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
