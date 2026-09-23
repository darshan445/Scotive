import Link from "next/link";
import { ArrowRight } from "lucide-react";
import {
    MarketingCta,
    MarketingHero,
    MarketingHeroCtas,
    MarketingShell,
} from "@/components/MarketingShell";
import { RESOURCE_LINKS } from "@/lib/guides";
import { PRICE_AFTER_TRIAL, TRIAL_CTA } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/guides";
const TITLE = "Resources · Scotive";
const DESCRIPTION =
    "Invoice reminder software, past due emails, payment reminder templates, and how to follow up from Gmail or Outlook — on invoices from QuickBooks, Xero, or FreshBooks. 30-day free trial.";

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
    keywords: [
        "invoice reminder software",
        "past due invoice reminder",
        "payment reminder email template",
        "how to chase outstanding invoices",
    ],
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

export default function ResourcesIndexPage() {
    return (
        <MarketingShell testId="guides-index" activePath="/guides">
            <MarketingHero
                eyebrow="Resources"
                title="Follow-up that matches the conversation — not just the due date."
                description="Scotive matches each open invoice from QuickBooks, Xero, or FreshBooks to the Gmail or Outlook thread, sends Friendly reminders you approve, and pauses the moment they reply."
            >
                <MarketingHeroCtas
                    primaryLabel={TRIAL_CTA}
                    secondaryHref="/invoice-reminder-software"
                    secondaryLabel="Invoice reminder software"
                />
            </MarketingHero>
            <section className="py-14 md:py-16 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {RESOURCE_LINKS.map((item) => (
                        <Link
                            key={item.path}
                            href={item.path}
                            className="surface-card p-6 hover:shadow-md transition-shadow block group"
                        >
                            <h2 className="type-title text-xl group-hover:underline underline-offset-2">
                                {item.title}
                            </h2>
                            <p className="type-body mt-2 text-sm text-muted-foreground">{item.description}</p>
                            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary">
                                Read
                                <ArrowRight className="w-3.5 h-3.5" />
                            </span>
                        </Link>
                    ))}
                </div>
                <p className="type-body mt-10 text-sm text-muted-foreground">
                    {PRICE_AFTER_TRIAL}
                </p>
            </section>
            <MarketingCta
                title="Get paid without the awkward follow-up."
                description="Connect Gmail or Outlook, plus QuickBooks, Xero, or FreshBooks. Every invoice gets a state and a next email in their words."
            />
        </MarketingShell>
    );
}
