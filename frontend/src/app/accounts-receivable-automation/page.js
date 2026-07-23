import Link from "next/link";
import { MarketingCta, MarketingHero, MarketingShell } from "@/components/MarketingShell";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
    title: "Accounts Receivable Automation for Small Teams | Scotive",
    description:
        "Accounts receivable automation without enterprise bloat — track open invoices, escalate follow-ups, and match payments. Scotive connects email and accounting so AR stays visible and human.",
    path: "/accounts-receivable-automation",
    keywords: [
        "accounts receivable automation",
        "AR automation software",
        "accounts receivable follow up",
        "invoice to cash",
    ],
});

export default function ArAutomationPage() {
    return (
        <MarketingShell testId="seo-ar-automation" activePath="/accounts-receivable-automation">
            <MarketingHero
                eyebrow="Accounts receivable automation"
                title="AR automation that respects the relationship"
                description="Enterprise AR platforms optimize DSO with heavy workflows. Scotive automates the tedious parts — detection, status, drafts — while you keep judgment and approval on every client email."
            />

            <section className="py-14 md:py-16 max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">What AR automation usually means</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        Tools in this space (Chaser, Upflow, Gaviti, and others) sync aging reports, schedule
                        reminder sequences, and forecast cash. That&apos;s powerful for finance teams — and often
                        more than freelancers or 2–10 person studios need.
                    </p>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Scotive&apos;s AR layer</h2>
                    <ul className="mt-4 space-y-3 type-body text-muted-foreground list-disc pl-5">
                        <li>Open / overdue / promised / disputed ledger with evidence from email</li>
                        <li>Optional accounting sync for unpaid invoices and paid status (QuickBooks Online live)</li>
                        <li>Escalation-minded drafts you still send yourself</li>
                        <li>Daily digest of what needs attention</li>
                    </ul>
                </div>
                <div>
                    <h2 className="type-title text-2xl md:text-3xl">Connect your stack</h2>
                    <p className="type-body mt-3 text-muted-foreground">
                        See current and upcoming connectors on{" "}
                        <Link href="/integrations" className="text-foreground underline underline-offset-2">
                            Integrations
                        </Link>
                        .
                    </p>
                </div>
            </section>
            <MarketingCta />
        </MarketingShell>
    );
}
