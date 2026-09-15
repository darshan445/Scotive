import {
    MarketingHero,
    MarketingShell,
} from "@/components/MarketingShell";
import { PricingPlans } from "@/components/PricingPlans";
import { MONTHLY_PRICE, ANNUAL_TOTAL, TRIAL_LABEL } from "@/lib/site";
import { absoluteUrl } from "@/lib/seo";

const PATH = "/pricing";
const TITLE = "Pricing · Scotive";
const DESCRIPTION =
    `Start with a 30-day free trial. Then $${MONTHLY_PRICE}/month, or $${ANNUAL_TOTAL}/year (2 months free). Follow up on unpaid invoices from your inbox, on a schedule you approve.`;

export const metadata = {
    title: { absolute: TITLE },
    description: DESCRIPTION,
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

export default function PricingPage() {
    return (
        <MarketingShell testId="pricing-page" activePath="/pricing">
            <MarketingHero
                eyebrow={TRIAL_LABEL}
                title="One plan. Start free."
                description="Agencies and consultants with a pile of open invoices. Every account includes a 30-day free trial — no card required to start."
            />

            <section className="pb-20 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
                <PricingPlans />
                <p className="mt-8 text-center text-sm text-muted-foreground">
                    Firmer follow-ups always need your approval. Reminders pause when a client replies.
                </p>
            </section>
        </MarketingShell>
    );
}
