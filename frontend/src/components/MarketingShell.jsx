import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingHeader } from "@/components/MarketingHeader";
import { TRIAL_CTA, TRIAL_LABEL } from "@/lib/site";

/**
 * Shared chrome for public marketing pages.
 */
export function MarketingShell({
    children,
    testId = "marketing-page",
    activePath = "",
}) {
    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid={testId}>
            <MarketingHeader
                activePath={activePath}
                loginTestId={testId === "landing-page" ? "landing-signin" : undefined}
                signupTestId={testId === "landing-page" ? "landing-signup" : undefined}
            />
            <main className="flex-1">{children}</main>
            <MarketingFooter />
        </div>
    );
}

export function MarketingHero({ eyebrow, title, description, children }) {
    return (
        <section className="relative overflow-hidden border-b border-border bg-gradient-to-b from-primary/[0.06] to-background">
            <div className="relative max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-14 md:pt-20 pb-12 md:pb-16">
                {eyebrow ? <div className="eyebrow mb-3">{eyebrow}</div> : null}
                <h1 className="type-display text-4xl sm:text-5xl">{title}</h1>
                {description ? (
                    <p className="type-body mt-5 text-base md:text-lg text-muted-foreground">{description}</p>
                ) : null}
                {children}
            </div>
        </section>
    );
}

export function MarketingHeroCtas({
    primaryHref = "/register",
    primaryLabel = TRIAL_CTA,
    secondaryHref = "/pricing",
    secondaryLabel = "View pricing",
}) {
    return (
        <div className="mt-8 flex flex-wrap gap-3">
            <Link href={primaryHref} className="btn-pill-primary text-sm">
                {primaryLabel}
                <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link href={secondaryHref} className="btn-pill-outline text-sm py-2.5">
                {secondaryLabel}
            </Link>
        </div>
    );
}

export function MarketingSolveBlock({
    title = "How Scotive helps",
    problem,
    points = [],
    ctaLabel = TRIAL_CTA,
}) {
    return (
        <aside className="rounded-2xl border border-border bg-card px-5 py-6 md:px-8 md:py-8">
            <h2 className="type-title text-xl md:text-2xl text-foreground">{title}</h2>
            {problem ? (
                <p className="type-body mt-3 text-sm md:text-base text-muted-foreground">{problem}</p>
            ) : null}
            {points.length ? (
                <ul className="mt-4 space-y-2.5 type-body text-sm md:text-base text-muted-foreground list-disc pl-5">
                    {points.map((p) => (
                        <li key={p}>
                            <span className="text-foreground/90">{p}</span>
                        </li>
                    ))}
                </ul>
            ) : null}
            <div className="mt-6 flex flex-wrap items-center gap-3">
                <Link href="/register" className="btn-pill-primary text-sm">
                    {ctaLabel}
                    <ArrowRight className="w-3.5 h-3.5" />
                </Link>
                <span className="text-xs text-muted-foreground">{TRIAL_LABEL}</span>
            </div>
        </aside>
    );
}

export function MarketingCta({
    title = "Stop chasing unpaid invoices by hand.",
    description = "Connect email, match each open invoice to the thread, and let approved reminders run — pausing the moment someone replies.",
    buttonLabel = TRIAL_CTA,
}) {
    return (
        <section className="py-16 md:py-20">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="rounded-2xl ink-panel px-8 py-12 md:px-14 md:py-16 text-center">
                    <h2 className="type-display text-3xl md:text-4xl">{title}</h2>
                    <p className="type-body mt-4 opacity-80 max-w-xl mx-auto">{description}</p>
                    <Link href="/register" className="mt-8 btn-pill-primary bg-background text-foreground hover:bg-background/90">
                        {buttonLabel}
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </div>
        </section>
    );
}
