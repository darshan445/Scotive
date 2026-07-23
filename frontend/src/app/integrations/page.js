import Link from "next/link";
import { Check, Clock } from "lucide-react";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Integrations — Email & Accounting for Invoice Chasing | Scotive",
    description:
        "Scotive integrations: Gmail and QuickBooks Online available now. Outlook, Zoho Books, and FreshBooks on the roadmap. Invoice chasing that meets you in the tools you already use.",
    path: "/integrations",
    keywords: [
        "Gmail QuickBooks integration",
        "Outlook invoice chasing",
        "Zoho Books collections",
        "FreshBooks payment follow up",
    ],
});

const EMAIL = [
    {
        name: "Gmail",
        status: "Available",
        detail: "Detect invoices in sent mail, read replies, send approved follow-ups from your address.",
        available: true,
    },
    {
        name: "Outlook / Microsoft 365",
        status: "Coming soon",
        detail: "Same conversation-aware chasing for teams on Outlook — on the roadmap.",
        available: false,
        href: "/outlook-invoice-chasing",
    },
];

const ACCOUNTING = [
    {
        name: "QuickBooks Online",
        status: "Available",
        detail: "Import open invoices, sync paid status, and keep Scotive aligned when QBO changes.",
        available: true,
        href: "/quickbooks-invoice-chasing",
    },
    {
        name: "Zoho Books",
        status: "Coming soon",
        detail: "Pull unpaid invoices and paid signals from Zoho Books into the same Scotive ledger.",
        available: false,
        href: "/zoho-books-invoice-chasing",
    },
    {
        name: "FreshBooks",
        status: "Coming soon",
        detail: "Chase FreshBooks invoices with the same reply intelligence and approval-first sends.",
        available: false,
        href: "/freshbooks-invoice-chasing",
    },
];

function IntegrationCard({ name, status, detail, available, href }) {
    const body = (
        <div className="surface-card p-6 h-full flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
                <h3 className="type-title text-lg">{name}</h3>
                <span
                    className={`inline-flex items-center gap-1 text-[11px] font-medium rounded-full px-2.5 py-1 ${
                        available
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-muted text-muted-foreground border border-border"
                    }`}
                >
                    {available ? <Check className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {status}
                </span>
            </div>
            <p className="type-body text-sm text-muted-foreground flex-1">{detail}</p>
            {href ? (
                <span className="text-sm font-medium text-primary">Learn more →</span>
            ) : null}
        </div>
    );
    if (href) {
        return (
            <Link href={href} className="block hover:opacity-95 transition-opacity">
                {body}
            </Link>
        );
    }
    return body;
}

export default function IntegrationsPage() {
    return (
        <MarketingShell testId="seo-integrations" activePath="/integrations">
            <MarketingHero
                eyebrow="Integrations"
                title="Email + accounting — not locked to one stack"
                description="Scotive is built as payment ops across the tools you already use. Start with what’s live; more connectors ship without changing how you chase."
            />

            <section className="py-12 md:py-16 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-14">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl mb-6">Email &amp; conversations</h2>
                    <div className="grid md:grid-cols-2 gap-4">
                        {EMAIL.map((item) => (
                            <IntegrationCard key={item.name} {...item} />
                        ))}
                    </div>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl mb-6">Accounting &amp; invoices</h2>
                    <div className="grid md:grid-cols-3 gap-4">
                        {ACCOUNTING.map((item) => (
                            <IntegrationCard key={item.name} {...item} />
                        ))}
                    </div>
                </div>
                <p className="type-body text-sm text-muted-foreground max-w-2xl">
                    Want a connector sooner? Email{" "}
                    <a href="mailto:support@scotive.com" className="text-foreground underline underline-offset-2">
                        support@scotive.com
                    </a>
                    . Meanwhile,{" "}
                    <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                        invoice chasing software overview
                    </Link>
                    .
                </p>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
