import Link from "next/link";
import { MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { GUIDES } from "@/lib/guides";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Guides — Invoice Follow-Ups, Reminders & Getting Paid | Scotive",
    description:
        "Practical guides on invoice follow-up emails, unpaid invoice reminders, and how to politely chase payment — for freelancers, agencies, and teams that bill clients.",
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
                description="Short, practical writing on invoice follow-ups, unpaid reminders, and broken payment promises — free to use whether or not you try Scotive."
            />
            <section className="py-12 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
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
                <p className="mt-10 type-body text-sm text-muted-foreground">
                    Looking for the product? See{" "}
                    <Link href="/invoice-chasing-software" className="text-foreground underline underline-offset-2">
                        invoice chasing software
                    </Link>{" "}
                    or{" "}
                    <Link href="/chase-unpaid-invoices" className="text-foreground underline underline-offset-2">
                        how to chase unpaid invoices
                    </Link>
                    .
                </p>
            </section>
        </MarketingShell>
    );
}
