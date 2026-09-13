import Link from "next/link";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
    MarketingSolveBlock,
} from "@/components/MarketingShell";
import { FaqSection } from "@/components/FaqSection";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Accounts Receivable Automation for Freelancers & Agencies | Scotive",
    description:
        "Accounts receivable automation that tracks unpaid invoices, reads client replies, and drafts follow-ups you approve. AR automation software for SMBs — Gmail + QuickBooks Online, not enterprise bloat.",
    path: "/accounts-receivable-automation",
    keywords: [
        "accounts receivable automation",
        "accounts receivable automation software",
        "AR automation software",
        "automated accounts receivable",
        "what is accounts receivable automation",
        "AR automation",
    ],
});

const AR_FAQS = [
    {
        question: "What is accounts receivable automation?",
        answer:
            "Accounts receivable automation uses software to track open invoices, spot overdue balances, follow up on late payments, and update status when clients reply or pay — so you spend less time chasing cash by hand. Scotive automates detection and drafts while you still approve every email.",
    },
    {
        question: "How does AR automation software work with email?",
        answer:
            "Scotive connects Gmail, reads invoice and reply threads, and keeps a live ledger (invoiced, overdue, promised, disputed, partially paid, and more). When a follow-up is due, it drafts a chase in your thread — nothing sends until you click approve.",
    },
    {
        question: "Is accounts receivable automation only for enterprise finance teams?",
        answer:
            "No. Large AR platforms (HighRadius, Bill.com-class suites) serve finance orgs. Scotive is AR automation for freelancers, agencies, consultants, and small teams that bill clients — lighter process, human-approved sends.",
    },
    {
        question: "What tools does Scotive connect for AR automation?",
        answer:
            "Gmail and QuickBooks Online are live. Outlook, Zoho Books, and FreshBooks are on the roadmap. The product is built around email + accounting, not a single vendor lock-in.",
    },
];

export default function ArAutomationPage() {
    return (
        <MarketingShell testId="seo-ar-automation" activePath="/accounts-receivable-automation">
            <MarketingHero
                eyebrow="Accounts receivable automation"
                title="AR automation without the enterprise stack"
                description="Accounts receivable automation should mean fewer missed follow-ups — not a six-month finance rollout. Scotive tracks unpaid invoices from email and accounting, drafts the next chase, and waits for your approval."
            >
                <MarketingHeroCtas
                    secondaryHref="/chase-unpaid-invoices"
                    secondaryLabel="See unpaid invoice chasing"
                />
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                <MarketingSolveBlock
                    title="Use Scotive for AR automation that fits how you already bill"
                    problem="You searched accounts receivable automation because unpaid invoices and late follow-ups are eating your week. Scotive is the lightweight way to fix that — without an enterprise AR rollout."
                    points={[
                        "Connect Gmail (and QuickBooks Online if you use it) in minutes",
                        "See every open invoice status: overdue, promised, disputed, partially paid, says paid",
                        "Get a draft follow-up matched to that state — you approve before it sends",
                        "Mark paid when money lands so chasing stops automatically",
                    ]}
                    ctaLabel="Start free — solve unpaid invoices with Scotive"
                />

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">What is accounts receivable automation?</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        In plain terms: software that helps you get paid faster by watching open invoices,
                        escalating when they go overdue, and capturing what clients say in replies — promises,
                        disputes, “I already paid,” partial payments. That&apos;s accounts receivable automation.
                        Done well, it cuts manual chasing without turning every client into a collections case.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">AR automation software for people who bill clients</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Search results for accounts receivable automation are full of enterprise platforms —
                        HighRadius, Billtrust, NetSuite-adjacent suites. Those tools optimize DSO for large
                        finance teams. Freelancers, agencies, and small businesses usually need something
                        closer to the work they already do: invoice in Gmail or QuickBooks, follow up politely,
                        know who still owes what.
                    </p>
                    <ul className="mt-4 space-y-3 type-body text-muted-foreground list-disc pl-5">
                        <li>
                            <strong className="text-foreground">Ledger from real conversations</strong> — open,
                            overdue, promised, broken promise, disputed, partially paid, says paid
                        </li>
                        <li>
                            <strong className="text-foreground">Human-approved follow-ups</strong> — drafts you
                            edit and send; never auto-blast
                        </li>
                        <li>
                            <strong className="text-foreground">Email + accounting</strong> — Gmail and QuickBooks
                            Online today; more connectors on the roadmap
                        </li>
                        <li>
                            <strong className="text-foreground">Invoice collection without the drama</strong> —
                            tone matches state (friendly → firm → final), not a fixed spam sequence
                        </li>
                    </ul>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">How Scotive automates AR (and what stays manual)</h2>
                    <ol className="mt-4 space-y-4 type-body text-muted-foreground list-decimal pl-5">
                        <li>
                            <strong className="text-foreground">Connect</strong> — Gmail (and optionally QuickBooks
                            Online) so invoices and threads land in one place.
                        </li>
                        <li>
                            <strong className="text-foreground">Detect &amp; sync</strong> — historical fetch plus
                            ongoing sync for new invoices and replies.
                        </li>
                        <li>
                            <strong className="text-foreground">Prioritize</strong> — dashboard of what needs you:
                            overdue, promises, disputes, payment claims.
                        </li>
                        <li>
                            <strong className="text-foreground">Approve the send</strong> — Scotive drafts; you
                            send from your mailbox. Mark paid when money lands.
                        </li>
                    </ol>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Benefits of accounts receivable automation</h2>
                    <ul className="mt-4 space-y-3 type-body text-muted-foreground list-disc pl-5">
                        <li>Fewer unpaid invoices that “fell through the cracks”</li>
                        <li>Faster follow-up when due dates slip or promises break</li>
                        <li>Clearer cash picture without rebuilding a spreadsheet every Monday</li>
                        <li>Client relationships protected — you control tone and timing</li>
                    </ul>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Related pages</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Practical chase:{" "}
                        <Link href="/chase-unpaid-invoices" className="text-foreground underline underline-offset-2">
                            unpaid invoices &amp; invoice collection
                        </Link>
                        . Reminders:{" "}
                        <Link href="/overdue-invoice-reminder" className="text-foreground underline underline-offset-2">
                            overdue invoice &amp; payment reminders
                        </Link>
                        . Category:{" "}
                        <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                            invoice chasing software
                        </Link>
                        .{" "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            Integrations
                        </Link>
                        .
                    </p>
                </div>
            </section>

            <FaqSection items={AR_FAQS} title="Accounts receivable automation FAQ" />
            <MarketingCta
                title="Ready for AR automation that doesn’t take over your week?"
                description="Start with Gmail. Optionally add QuickBooks. Scotive builds the unpaid-invoice ledger, drafts follow-ups from real replies, and never sends without you."
                buttonLabel="Start free with Scotive"
            />
        </MarketingShell>
    );
}
