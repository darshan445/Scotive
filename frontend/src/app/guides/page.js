import Link from "next/link";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
    MarketingSolveBlock,
} from "@/components/MarketingShell";
import { GUIDES } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Guides — Invoice Follow-Ups, Reminders & Getting Paid | Scotive",
    description:
        "Practical guides on invoice follow-up emails, unpaid invoice reminders, and how to politely chase payment — for freelancers, agencies, and teams that bill clients. Then let Scotive draft the next one.",
    path: "/guides",
    keywords: [
        "invoice follow up",
        "unpaid invoice reminder",
        "invoice reminder email template",
        "how to politely follow up on an invoice",
    ],
});

export default function GuidesIndexPage() {
    return (
        <MarketingShell testId="guides-index" activePath="/guides">
            <MarketingHero
                eyebrow="Guides"
                title="Get paid without the awkward chase"
                description="Short, practical writing on invoice follow-ups, unpaid reminders, and broken payment promises. Use the templates today — or let Scotive draft the next chase from your real invoices."
            >
                <MarketingHeroCtas
                    secondaryHref="/invoice-chasing-software"
                    secondaryLabel="See the product"
                />
            </MarketingHero>
            <section className="py-12 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <MarketingSolveBlock
                    title="Templates help once. Scotive helps every unpaid invoice."
                    problem="These guides teach tone and timing. Scotive connects Gmail (and QuickBooks), tracks what’s unpaid, and drafts the next follow-up so you’re not rewriting the same email every week."
                    points={[
                        "Ledger of unpaid / overdue / promised invoices",
                        "Drafts matched to client replies — you approve every send",
                        "Free to start · disconnect anytime",
                    ]}
                    ctaLabel="Start free with Scotive"
                />
                <ul className="space-y-6">
                    {GUIDES.map((guide) => (
                        <li key={guide.slug} className="border-b border-border pb-6 last:border-0">
                            <Link href={guide.path} className="group block">
                                <h2 className="type-title text-xl md:text-2xl group-hover:underline underline-offset-2">
                                    {guide.title}
                                </h2>
                                <p className="type-body mt-2 text-sm text-muted-foreground">
                                    {guide.description}
                                </p>
                            </Link>
                        </li>
                    ))}
                </ul>
                <p className="type-body text-sm text-muted-foreground">
                    Looking for the product? See{" "}
                    <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                        invoice chasing software
                    </Link>
                    {" · "}
                    <Link href="/chase-unpaid-invoices" className="text-foreground underline underline-offset-2">
                        unpaid invoices
                    </Link>
                    {" · "}
                    <Link href="/accounts-receivable-automation" className="text-foreground underline underline-offset-2">
                        AR automation
                    </Link>
                    .
                </p>
            </section>
            <MarketingCta
                title="Done reading. Ready to stop chasing by hand?"
                description="Connect Gmail, see what’s unpaid, and approve Scotive’s next follow-up draft."
                buttonLabel="Start free with Scotive"
            />
        </MarketingShell>
    );
}
