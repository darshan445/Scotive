import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Invoice Chasing Software — Automate Follow-Ups You Still Control | Scotive",
    description:
        "Invoice chasing software that tracks overdue invoices, reads client replies, and drafts payment follow-ups you approve. Unlike heavy AR suites, Scotive stays human — email + accounting integrations.",
    path: "/invoice-chasing-software",
    keywords: ["invoice chasing software", "automated invoice reminders", "invoice chase tool"],
});

export default function InvoiceChasingSoftwarePage() {
    return (
        <MarketingShell testId="seo-invoice-chasing" activePath="/invoice-chasing-software">
            <MarketingHero
                eyebrow="Invoice chasing software"
                title="Chase invoices without becoming a collections department"
                description="Competitors like Chaser and Upflow automate AR for finance teams. Scotive fits freelancers, agencies, consultants, and any team that bills clients: track unpaid invoices, understand replies, and send follow-ups only when you approve."
            >
                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/register" className="inline-flex items-center rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90">
                        Start free
                    </Link>
                    <Link href="/integrations" className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted">
                        See integrations
                    </Link>
                </div>
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Who uses invoice chasing software</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Freelancers, agencies, consultants, professional services firms, studios, and small
                        businesses — anyone who sends invoices and follows up when payment is late. Scotive is
                        built for that reality, not only for enterprise finance departments.
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">What invoice chasing software should do</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Know which invoices are still unpaid — without rebuilding a ledger by hand</li>
                        <li>Follow up consistently when due dates slip or promises break</li>
                        <li>Keep tone professional and relationship-safe</li>
                        <li>Stop the moment you confirm payment — no nagging after you&apos;re paid</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">How Scotive is different</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Most AR platforms push automated sequences from a separate system. Scotive watches the
                        conversations you already have, drafts the next email in-thread, and never sends without
                        your click. Connect Gmail today (Outlook next) and optionally QuickBooks Online (Zoho Books
                        and FreshBooks on the roadmap).
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Built to rank — and to get you paid</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Whether you searched for invoice chasing software, payment follow-up tools, or an overdue
                        invoice tracker, Scotive combines tracking, reply intelligence, and human-approved sends in
                        one calm workflow.{" "}
                        <Link href="/chase-unpaid-invoices" className="text-foreground underline underline-offset-2">
                            Learn how to chase unpaid invoices
                        </Link>
                        {" · "}
                        <Link href="/accounts-receivable-automation" className="text-foreground underline underline-offset-2">
                            AR automation overview
                        </Link>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
