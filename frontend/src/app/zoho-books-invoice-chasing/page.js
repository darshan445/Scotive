import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Zoho Books Invoice Chasing (Coming Soon) — Collections Follow-Up | Scotive",
    description:
        "Zoho Books invoice chasing is on the Scotive roadmap. Pull unpaid invoices into one ledger, sync paid signals, and chase with human-approved email follow-ups — alongside Gmail and QuickBooks Online.",
    path: "/zoho-books-invoice-chasing",
    keywords: [
        "Zoho Books collections",
        "Zoho Books invoice chasing",
        "Zoho unpaid invoices",
        "Zoho Books AR automation",
    ],
});

export default function ZohoBooksInvoiceChasingPage() {
    return (
        <MarketingShell testId="seo-zoho-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="Zoho Books · Coming soon"
                title="Chase Zoho Books invoices without a separate collections stack"
                description="Scotive will connect Zoho Books as an accounting feed — unpaid invoices in, paid signals synced — while email conversations drive the chase. Not locked to QuickBooks forever."
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
                    <h2 className="type-title text-2xl md:text-3xl">Planned Zoho Books capabilities</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Import open / overdue invoices into the Scotive ledger</li>
                        <li>Keep paid status aligned when Zoho marks an invoice paid</li>
                        <li>Pair with email (Gmail today; Outlook next) for reply-aware follow-ups</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Live today: QuickBooks Online</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Need accounting-backed chasing now?{" "}
                        <Link href="/quickbooks-invoice-chasing" className="text-foreground underline underline-offset-2">
                            QuickBooks Online invoice chasing
                        </Link>{" "}
                        is available. Request Zoho priority at{" "}
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
