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
    title: "Unpaid Invoices — How to Collect & Chase Without Awkward Emails | Scotive",
    description:
        "Unpaid invoices pile up when promises live in email and balances live in accounting. Scotive tracks who still owes you, drafts invoice collection follow-ups, and waits for your approval before send.",
    path: "/chase-unpaid-invoices",
    keywords: [
        "unpaid invoices",
        "chase unpaid invoices",
        "how to collect unpaid invoices",
        "invoice collection",
        "how to chase unpaid invoices",
        "overdue invoice follow up",
    ],
});

const UNPAID_FAQS = [
    {
        question: "How do I collect unpaid invoices without damaging the relationship?",
        answer:
            "Start with a clear ledger (what's open, overdue, or promised), then send short, factual follow-ups that match the situation — not the same “pay now” blast every time. Scotive drafts those emails from invoice state; you approve tone before they go out from your Gmail.",
    },
    {
        question: "What's the difference between unpaid invoices and overdue invoices?",
        answer:
            "Unpaid means the balance isn't settled yet. Overdue means the due date has passed. A client can have an unpaid invoice that isn't overdue yet, or an overdue invoice with a new pay promise. Scotive tracks both so you don't chase the wrong way.",
    },
    {
        question: "How does invoice collection work in Scotive?",
        answer:
            "Connect Gmail (and optionally QuickBooks Online). Scotive builds a list of unpaid invoices, updates status from replies, and drafts collection-minded follow-ups. You review and send — nothing auto-sends. When you're paid, mark it paid (and sync to QBO when linked).",
    },
    {
        question: "What should I do when a client says they already paid?",
        answer:
            "Treat it as a payment claim until money hits your account. Scotive can flag “says paid” so you confirm the deposit instead of escalating a chase. Don't thank them as if the cash landed until you've verified it.",
    },
];

export default function ChaseUnpaidInvoicesPage() {
    return (
        <MarketingShell testId="seo-chase-unpaid" activePath="/chase-unpaid-invoices">
            <MarketingHero
                eyebrow="Unpaid invoices"
                title="A calmer way to handle unpaid invoices"
                description="Unpaid invoices aren't a spreadsheet problem — they're a conversation problem. Scotive turns email + accounting into one ledger, then helps you chase and collect with follow-ups you still approve."
            >
                <MarketingHeroCtas
                    secondaryHref="/guides/polite-reminder-for-unpaid-invoice"
                    secondaryLabel="Read reminder tips first"
                />
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                <MarketingSolveBlock
                    title="Scotive turns unpaid invoices into a clear “who to chase” list"
                    problem="If you landed here looking for unpaid invoices or invoice collection help, you don’t need another template alone — you need the list, the context, and the next email ready."
                    points={[
                        "Pull open invoices from Gmail and/or QuickBooks Online",
                        "Update status from client replies (promise, dispute, partial, says paid)",
                        "Draft the chase in the existing thread — you edit and approve",
                        "Mark paid when cash lands so you stop nagging settled invoices",
                    ]}
                    ctaLabel="Start free — chase unpaid invoices with Scotive"
                />

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Why unpaid invoices slip through</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        You sent the invoice. The client said “Friday.” Someone disputed a line. Accounting still
                        shows open. Your inbox holds the real story — and chasing unpaid invoices by hand means
                        reconstructing that story every week. That&apos;s how invoice collection becomes stressful
                        and inconsistent.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">How to collect unpaid invoices (a practical workflow)</h2>
                    <ol className="mt-4 space-y-4 type-body text-muted-foreground list-decimal pl-5">
                        <li>
                            <strong className="text-foreground">Know what&apos;s actually unpaid</strong> — import
                            or detect invoices from Gmail and/or QuickBooks Online; skip the ones already paid.
                        </li>
                        <li>
                            <strong className="text-foreground">Read the last reply</strong> — promise, dispute,
                            partial payment, or “I paid already” change what you should say next.
                        </li>
                        <li>
                            <strong className="text-foreground">Send one clear follow-up</strong> — short, factual,
                            state-aware. Scotive drafts; you approve and send from your mailbox.
                        </li>
                        <li>
                            <strong className="text-foreground">Close the loop</strong> — mark paid when funds land
                            so you stop chasing and your books stay clean.
                        </li>
                    </ol>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Invoice collection without sounding like collections</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        “Invoice collection” search results often push agencies and legal options. For freelancers
                        and agencies, the first job is consistent, polite chasing — then escalate only when silence
                        or broken promises pile up. Scotive keeps that ladder human: friendly when it just slipped,
                        firmer when a promise breaks, clarifying when they ask a question.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Who this is for</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Freelancers, agencies, consultants, studios, professional services, and any small team
                        whose cash flow depends on clients paying unpaid invoices on time.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Related</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        <Link href="/accounts-receivable-automation" className="text-foreground underline underline-offset-2">
                            Accounts receivable automation
                        </Link>
                        {" · "}
                        <Link href="/overdue-invoice-reminder" className="text-foreground underline underline-offset-2">
                            Payment &amp; overdue reminders
                        </Link>
                        {" · "}
                        <Link href="/guides/invoice-follow-up-email-templates" className="text-foreground underline underline-offset-2">
                            Follow-up email templates
                        </Link>
                        {" · "}
                        <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                            Invoice chasing software
                        </Link>
                    </p>
                </div>
            </section>

            <FaqSection items={UNPAID_FAQS} title="Unpaid invoices FAQ" />
            <MarketingCta
                title="Ready to stop guessing which invoices are still unpaid?"
                description="Connect Gmail, optionally QuickBooks, and let Scotive build the ledger and draft the next chase. You approve every send."
                buttonLabel="Start free with Scotive"
            />
        </MarketingShell>
    );
}
