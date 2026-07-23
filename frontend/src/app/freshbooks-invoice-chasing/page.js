import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "FreshBooks Invoice Chasing (Coming Soon) — Payment Follow-Up | Scotive",
    description:
        "FreshBooks invoice chasing is on the Scotive roadmap. Track unpaid FreshBooks invoices, sync paid status, and send human-approved payment follow-ups from your email — multi-accounting by design.",
    path: "/freshbooks-invoice-chasing",
    noindex: true,
    keywords: [
        "FreshBooks payment follow up",
        "FreshBooks invoice chasing",
        "FreshBooks collections",
        "FreshBooks overdue invoices",
    ],
});

export default function FreshBooksInvoiceChasingPage() {
    return (
        <MarketingShell testId="seo-freshbooks-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="FreshBooks · Coming soon"
                title="Payment follow-up for FreshBooks invoices"
                description="Scotive will treat FreshBooks as another accounting source for unpaid invoices — same ledger, same reply intelligence, same approve-before-send chase. Built for multi-tool teams, not one vendor lock-in."
            >
                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/register" className="inline-flex items-center rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90">
                        Start free
                    </Link>
                    <Link href="/integrations" className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted">
                        All integrations
                    </Link>
                </div>
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Planned FreshBooks capabilities</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Import unpaid and overdue FreshBooks invoices</li>
                        <li>Sync paid signals so chasing stops when you&apos;re paid</li>
                        <li>Combine with email conversations for promise-aware follow-ups</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Available accounting today</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        <Link href="/quickbooks-invoice-chasing" className="text-foreground underline underline-offset-2">
                            QuickBooks Online
                        </Link>{" "}
                        is live. FreshBooks and{" "}
                        <Link href="/zoho-books-invoice-chasing" className="text-foreground underline underline-offset-2">
                            Zoho Books
                        </Link>{" "}
                        are next — vote with{" "}
                        <a href="mailto:support@scotive.com" className="text-foreground underline underline-offset-2">
                            support@scotive.com
                        </a>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
