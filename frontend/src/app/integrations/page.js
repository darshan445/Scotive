import Link from "next/link";
import { Inbox, MessageSquareQuote, PenLine, Receipt } from "lucide-react";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import {
    ACCOUNTING_INTEGRATIONS,
    EMAIL_INTEGRATIONS,
    PRICE_AFTER_TRIAL,
} from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/integrations";
const TITLE = "Integrations · Scotive";
const DESCRIPTION =
    "Connect Gmail or Outlook and QuickBooks, Xero, or FreshBooks. Scotive matches each open invoice to the thread, tracks the state from invoiced to paid, and drafts the next follow-up in that client’s own language.";

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [],
    alternates: { canonical: absoluteUrl(PATH) },
    robots: { index: true, follow: true },
    openGraph: {
        url: absoluteUrl(PATH),
        title: TITLE,
        description: DESCRIPTION,
        type: "website",
        siteName: "Scotive",
    },
    twitter: {
        card: "summary_large_image",
        title: TITLE,
        description: DESCRIPTION,
    },
};

const CONNECT_JOBS = [
    {
        icon: Receipt,
        title: "Open invoices, pulled in",
        body: "Amount, due date, and paid status from QuickBooks, Xero, or FreshBooks — the invoicing tools you already use.",
    },
    {
        icon: Inbox,
        title: "The thread, matched",
        body: "Each invoice is tied to the Gmail or Outlook conversation. Follow-ups send from your address, on that thread.",
    },
    {
        icon: MessageSquareQuote,
        title: "States from the conversation",
        body: "From invoiced to paid — unpaid, overdue, promised, replied, disputed, says-paid. The state comes from what they said, not a due-date calendar.",
    },
    {
        icon: PenLine,
        title: "The next email, in their words",
        body: "Scotive drafts the next follow-up from that client’s own messages and language. Highly personal — not a reminder template. A pay link sits in the draft.",
    },
];

const STACK = [
    {
        step: "01",
        title: "You invoice",
        body: "QuickBooks, Xero, or FreshBooks stays the ledger — create the invoice, due date, paid or not.",
    },
    {
        step: "02",
        title: "You talk",
        body: "The real conversation lives in Gmail or Outlook. That is where they reply, promise, or say they paid.",
    },
    {
        step: "03",
        title: "Scotive chases",
        body: "Match thread to invoice, track the state from that conversation, draft the next follow-up in their language, put a pay link in the draft.",
    },
];

function CatalogTile({ item }) {
    return (
        <Link href={item.href} className="integration-logo-tile-page">
            <img src={item.logo} alt="" className="h-10 w-auto max-h-10 max-w-[180px] object-contain" />
            <span className="text-sm font-medium text-foreground">{item.name}</span>
        </Link>
    );
}

function CatalogGroup({ id, title, items, columns = 3 }) {
    return (
        <div id={id} className="scroll-mt-28">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">{title}</h3>
            <div className={`grid gap-3 ${columns === 2 ? "sm:grid-cols-2 max-w-xl" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
                {items.map((item) => (
                    <CatalogTile key={item.name} item={item} />
                ))}
            </div>
        </div>
    );
}

export default function IntegrationsPage() {
    return (
        <MarketingShell testId="seo-integrations" activePath="/integrations">
            <MarketingHero
                eyebrow="Integrations"
                title="Connect inbox and invoicing. Scotive reads the conversation."
                description="Keep QuickBooks, Xero, or FreshBooks as the ledger. Chase from Gmail or Outlook. Matching the thread is how Scotive tracks each invoice from invoiced to paid — and drafts the next follow-up in that client’s own words."
            >
                <MarketingHeroCtas
                    primaryLabel="Start 30-day free trial"
                    secondaryHref="/pricing"
                    secondaryLabel="View pricing"
                />
            </MarketingHero>

            <section className="py-16 md:py-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-10">
                        <h2 className="type-title text-2xl md:text-3xl">What connecting does</h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            Two connections. Then Scotive can see the state of each invoice from the thread, and write the next follow-up in their language.
                        </p>
                    </div>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {CONNECT_JOBS.map((job) => (
                            <article key={job.title} className="surface-card p-6 flex flex-col gap-3">
                                <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/5 text-primary">
                                    <job.icon className="w-5 h-5" strokeWidth={2} />
                                </span>
                                <h3 className="type-title text-lg">{job.title}</h3>
                                <p className="type-body text-sm text-muted-foreground">{job.body}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section className="pb-16 md:pb-20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-8">
                        <h2 className="type-title text-2xl md:text-3xl">Available integrations</h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            Accounting first — that is the ledger. Email second — that is the conversation.
                        </p>
                    </div>
                    <div className="rounded-2xl bg-muted/40 border border-border/70 p-4 sm:p-6 space-y-8">
                        <CatalogGroup id="accounting" title="Accounting" items={ACCOUNTING_INTEGRATIONS} />
                        <CatalogGroup id="email" title="Email" items={EMAIL_INTEGRATIONS} columns={2} />
                    </div>
                </div>
            </section>

            <section className="pb-8 md:pb-12">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="max-w-2xl mb-10">
                        <h2 className="type-title text-2xl md:text-3xl">How they work together</h2>
                        <p className="type-body mt-3 text-muted-foreground">
                            Scotive sits on top of the stack you already pay for. It does not replace your invoicing tools.
                        </p>
                    </div>
                    <div className="grid md:grid-cols-3 gap-4">
                        {STACK.map((item) => (
                            <article key={item.step} className="surface-card p-6">
                                <div className="eyebrow mb-3">
                                    Step {item.step}
                                </div>
                                <h3 className="type-title text-lg">{item.title}</h3>
                                <p className="type-body mt-2 text-sm text-muted-foreground">{item.body}</p>
                            </article>
                        ))}
                    </div>
                    <p className="type-body mt-8 text-sm text-muted-foreground">
                        {PRICE_AFTER_TRIAL}
                    </p>
                </div>
            </section>

            <MarketingCta
                title="Connect once. Then you see the state — and the next email in their words."
                description="Gmail or Outlook, plus the invoicing tool you already use. Conversation states from invoiced to paid. The next follow-up drafted from what they said."
            />
        </MarketingShell>
    );
}
