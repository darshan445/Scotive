import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "QuickBooks Invoice Chasing — Get Paid Faster with Scotive",
    description:
        "Chase QuickBooks Online invoices with email-aware follow-ups. Scotive imports unpaid QBO invoices, syncs paid status, and drafts Gmail follow-ups you approve — not a full AR suite, just payment ops.",
    path: "/quickbooks-invoice-chasing",
    keywords: [
        "QuickBooks invoice chasing",
        "QuickBooks Online collections",
        "chase QuickBooks invoices",
        "QBO accounts receivable",
    ],
});

export default function QuickBooksChasingPage() {
    return (
        <MarketingShell testId="seo-qbo-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="QuickBooks Online"
                title="Invoice chasing for QuickBooks — without leaving your inbox"
                description="Connect QuickBooks Online to import open invoices and paid status. Scotive still uses your email for conversations and human-approved chases — so QBO is a feed, not another place you live."
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
                    <h2 className="type-title text-2xl md:text-3xl">What Scotive does with QuickBooks</h2>
                    <ul className="mt-4 space-y-3 type-body text-muted-foreground list-disc pl-5">
                        <li>Import unpaid invoices into one ledger alongside email-detected invoices</li>
                        <li>Mark Paid when QuickBooks shows Balance = 0</li>
                        <li>Optionally push paid when you confirm receipt in Scotive</li>
                        <li>Match Gmail threads so promises and disputes still update status</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Not only QuickBooks</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Scotive is multi-accounting by design. Zoho Books and FreshBooks are on the roadmap — same
                        chasing experience, more invoice sources. See{" "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            integrations
                        </Link>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
