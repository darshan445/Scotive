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
    title: "Payment Reminders & Overdue Invoice Reminders You Approve | Scotive",
    description:
        "Payment reminders for overdue invoices that match how late the client really is — friendly, firm, or final. Scotive drafts overdue invoice reminders from live state; you approve before send.",
    path: "/overdue-invoice-reminder",
    keywords: [
        "payment reminders",
        "overdue invoice reminder",
        "invoice payment reminder",
        "late invoice payment",
        "overdue invoice tracker",
        "invoice reminder software",
    ],
});

const REMINDER_FAQS = [
    {
        question: "What are payment reminders for invoices?",
        answer:
            "Payment reminders are follow-up emails (or messages) that ask a client to settle an open or overdue invoice. Good reminders are short, factual, and match context — due date, prior promise, or dispute — instead of the same automated blast every time.",
    },
    {
        question: "When should I send an overdue invoice reminder?",
        answer:
            "Typically right after the due date if there's no reply, then again if a promised pay date slips. If the client asked a question or disputed the amount, answer that first — a blunt overdue reminder makes invoice collection harder.",
    },
    {
        question: "Does Scotive auto-send payment reminders?",
        answer:
            "No. Scotive drafts overdue invoice and payment reminders from invoice state. Nothing goes to the client until you review and approve. Sends go from your connected Gmail.",
    },
    {
        question: "Is this the same as “late payment” on a credit report?",
        answer:
            "No. Credit-report “late payment” content is about consumer credit scores. Scotive is for business invoices — late invoice payments from clients you bill. Different problem, different tools.",
    },
];

export default function OverdueInvoiceReminderPage() {
    return (
        <MarketingShell testId="seo-overdue-reminder" activePath="/overdue-invoice-reminder">
            <MarketingHero
                eyebrow="Payment reminders"
                title="Payment reminders that match how overdue you really are"
                description="Generic payment reminders ignore promises, disputes, and partial payments. Scotive drafts overdue invoice reminders from live invoice state — then waits for your approval before anything sends."
            >
                <MarketingHeroCtas
                    secondaryHref="/chase-unpaid-invoices"
                    secondaryLabel="Unpaid invoices workflow"
                />
            </MarketingHero>

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
                <MarketingSolveBlock
                    title="Scotive writes the payment reminder — you decide if it sends"
                    problem="You searched payment reminders or overdue invoice reminders because clients are late and you don’t want to sound like a bot. Scotive drafts the right tone from invoice state."
                    points={[
                        "Friendly when it just slipped past due",
                        "Firm when a promised pay date breaks",
                        "Clarifying when they ask a question or dispute",
                        "Always human-approved — never an auto-blast sequence",
                    ]}
                    ctaLabel="Start free — send smarter payment reminders"
                />

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Why payment reminders fail</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Timer-based reminder sequences treat every late invoice payment the same. If a client
                        already promised Friday — or disputed a line item — a blunt “your invoice is overdue”
                        email damages the relationship. Better payment reminders read the thread and the ledger
                        first.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Overdue invoice reminders by state</h2>
                    <ul className="mt-4 space-y-3 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                        <li>Friendly payment reminder when something just slipped past due</li>
                        <li>Firm follow-up when a promise date breaks</li>
                        <li>Final notice when silence stretches</li>
                        <li>Clarifying reply when the client asks a question or disputes</li>
                    </ul>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Late invoice payment vs credit “late payment”</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        If you searched “late payment,” Google often shows credit-report articles. Scotive is for
                        the other meaning: clients paying your invoices late. Same words, different intent — we
                        help you send payment reminders and collect unpaid balances, not fix a credit score.
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Email + accounting</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Track overdue invoices and send payment reminders from Gmail and QuickBooks Online today.
                        Outlook, Zoho Books, and FreshBooks are on the roadmap.{" "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            See integrations
                        </Link>
                        .
                    </p>
                </div>

                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Templates &amp; related</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        <Link href="/guides/polite-reminder-for-unpaid-invoice" className="text-foreground underline underline-offset-2">
                            Polite unpaid invoice reminder
                        </Link>
                        {" · "}
                        <Link href="/guides/invoice-follow-up-email-templates" className="text-foreground underline underline-offset-2">
                            Follow-up email templates
                        </Link>
                        {" · "}
                        <Link href="/accounts-receivable-automation" className="text-foreground underline underline-offset-2">
                            AR automation
                        </Link>
                    </p>
                </div>
            </section>

            <FaqSection items={REMINDER_FAQS} title="Payment reminders FAQ" />
            <MarketingCta
                title="Payment reminders without the awkward copy-paste"
                description="Scotive drafts overdue invoice reminders from live state in Gmail (and QuickBooks when connected). You approve; nothing auto-sends."
                buttonLabel="Start free with Scotive"
            />
        </MarketingShell>
    );
}
