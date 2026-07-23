import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Outlook Invoice Chasing (Coming Soon) — Microsoft 365 AR Follow-Up | Scotive",
    description:
        "Outlook / Microsoft 365 invoice chasing is on the Scotive roadmap. Same conversation-aware unpaid invoice tracking and human-approved follow-ups — not locked to Gmail forever.",
    path: "/outlook-invoice-chasing",
    noindex: true,
    keywords: [
        "Outlook invoice chasing",
        "Microsoft 365 accounts receivable",
        "Outlook unpaid invoice tracker",
        "Office 365 invoice follow up",
    ],
});

export default function OutlookInvoiceChasingPage() {
    return (
        <MarketingShell testId="seo-outlook-chasing" activePath="/integrations">
            <MarketingHero
                eyebrow="Outlook · Coming soon"
                title="Invoice chasing for Outlook and Microsoft 365"
                description="Scotive is not a Gmail-only product. Outlook / Microsoft 365 support is on the roadmap so teams on Microsoft mail get the same reply intelligence and approval-first chase drafts."
            >
                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/register" className="inline-flex items-center rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90">
                        Start free with Gmail today
                    </Link>
                    <Link href="/integrations" className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted">
                        All integrations
                    </Link>
                </div>
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">What’s coming</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Detect invoices and payment conversations in Outlook mail</li>
                        <li>Read client replies for promises, disputes, and payment claims</li>
                        <li>Draft follow-ups you approve before send from your Microsoft address</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Available now</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Use{" "}
                        <Link href="/" className="text-foreground underline underline-offset-2">
                            Scotive
                        </Link>{" "}
                        with Gmail today, optionally{" "}
                        <Link href="/quickbooks-invoice-chasing" className="text-foreground underline underline-offset-2">
                            QuickBooks Online
                        </Link>
                        . Want Outlook sooner? Email{" "}
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
