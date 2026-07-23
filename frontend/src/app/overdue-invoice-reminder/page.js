import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Overdue Invoice Reminder Software — Tone That Matches How Late It Is | Scotive",
    description:
        "Overdue invoice reminder software that drafts friendly, firm, or final follow-ups from invoice state — you approve before send. Works with email and accounting (Gmail + QuickBooks Online today).",
    path: "/overdue-invoice-reminder",
    keywords: [
        "overdue invoice reminder",
        "overdue invoice tracker",
        "late invoice follow up",
        "invoice reminder software",
    ],
});

export default function OverdueInvoiceReminderPage() {
    return (
        <MarketingShell testId="seo-overdue-reminder" activePath="/chase-unpaid-invoices">
            <MarketingHero
                eyebrow="Overdue invoice reminders"
                title="Reminders that match how overdue you really are"
                description="Generic reminder blasts ignore promises, disputes, and partial payments. Scotive drafts overdue invoice reminders from live invoice state — then waits for your approval."
            >
                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/register" className="inline-flex items-center rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90">
                        Start free
                    </Link>
                    <Link href="/chase-unpaid-invoices" className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted">
                        Chase unpaid invoices
                    </Link>
                </div>
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Why overdue reminders fail</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Competitors often send fixed sequences on a timer. If a client already promised Friday —
                        or disputed a line item — a blunt “your invoice is overdue” email damages the relationship.
                        Scotive reads the thread and ledger first.
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">State-derived tones</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Friendly reminder when something just slipped past due</li>
                        <li>Firm follow-up when a promise date breaks</li>
                        <li>Final notice when silence stretches</li>
                        <li>Clarifying reply when the client asks a question or disputes</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Email + accounting, not one vendor only</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Track overdue invoices from Gmail and QuickBooks Online today. Outlook, Zoho Books, and
                        FreshBooks are on the roadmap — same reminder workflow, more sources.{" "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            See integrations
                        </Link>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
