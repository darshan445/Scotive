import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";

/**
 * Shared chrome for public SEO / marketing pages (non-auth).
 * Nav matches the homepage: Product · Guides · Integrations · Log in · Start free.
 */
export function MarketingShell({
    children,
    testId = "marketing-page",
    activePath = "",
}) {
    const nav = [
        { href: "/invoice-chasing-software", label: "Product" },
        { href: "/guides", label: "Guides" },
        { href: "/integrations", label: "Integrations" },
    ];

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid={testId}>
            <header className="border-b border-border/70 bg-background/80 backdrop-blur-md sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
                    <BrandMark size="md" />
                    <div className="flex items-center gap-2 sm:gap-4">
                        <nav className="hidden md:flex items-center gap-1 text-sm">
                            {nav.map((item) => (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`px-3 py-1.5 rounded-lg transition-colors ${
                                        activePath === item.href
                                            || (item.href === "/invoice-chasing-software"
                                                && [
                                                    "/accounts-receivable-automation",
                                                    "/chase-unpaid-invoices",
                                                    "/overdue-invoice-reminder",
                                                    "/invoice-chasing-software",
                                                    "/quickbooks-invoice-chasing",
                                                ].includes(activePath))
                                            ? "text-foreground bg-muted font-medium"
                                            : "text-muted-foreground hover:text-foreground hover:bg-muted"
                                    }`}
                                >
                                    {item.label}
                                </Link>
                            ))}
                        </nav>
                        <Link
                            href="/login"
                            className="text-sm font-medium px-3 py-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                            Log in
                        </Link>
                        <Link
                            href="/register"
                            className="inline-flex items-center gap-1.5 text-sm font-semibold bg-primary text-primary-foreground px-4 py-2 rounded-xl hover:bg-primary/90 transition-colors shadow-sm"
                        >
                            Start free
                            <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </div>
                </div>
            </header>

            <main className="flex-1">{children}</main>

            <footer className="border-t border-border mt-auto">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid gap-10 md:grid-cols-4">
                    <div className="md:col-span-2">
                        <BrandMark />
                        <p className="type-body mt-3 text-sm max-w-sm">
                            Invoice chasing for freelancers, agencies, and any team that bills clients —
                            email + accounting, human-approved follow-ups.
                        </p>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Product</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/" className="hover:text-foreground">Home</Link></li>
                            <li><Link href="/invoice-chasing-software" className="hover:text-foreground">Invoice chasing software</Link></li>
                            <li><Link href="/chase-unpaid-invoices" className="hover:text-foreground">Unpaid invoices</Link></li>
                            <li><Link href="/accounts-receivable-automation" className="hover:text-foreground">AR automation</Link></li>
                            <li><Link href="/overdue-invoice-reminder" className="hover:text-foreground">Payment reminders</Link></li>
                            <li><Link href="/guides" className="hover:text-foreground">Guides</Link></li>
                            <li><Link href="/guides/invoice-follow-up-email-templates" className="hover:text-foreground">Invoice follow-up templates</Link></li>
                            <li><Link href="/integrations" className="hover:text-foreground">Integrations</Link></li>
                            <li><Link href="/quickbooks-invoice-chasing" className="hover:text-foreground">QuickBooks invoice chasing</Link></li>
                            <li><Link href="/register" className="hover:text-foreground">Get started</Link></li>
                        </ul>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Legal</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/contact" className="hover:text-foreground">Contact</Link></li>
                            <li><Link href="/terms" className="hover:text-foreground">Terms of Service</Link></li>
                            <li><Link href="/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
                            <li><a href="mailto:contact@scotive.com" className="hover:text-foreground">contact@scotive.com</a></li>
                        </ul>
                    </div>
                </div>
                <div className="border-t border-border">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground">
                        <span>© {new Date().getFullYear()} Scotive. All rights reserved.</span>
                        <span>Get paid faster · You approve every send</span>
                    </div>
                </div>
            </footer>
        </div>
    );
}

export function MarketingHero({ eyebrow, title, description, children }) {
    return (
        <section className="relative overflow-hidden border-b border-border/70">
            <div className="absolute inset-0 dot-grid pointer-events-none" aria-hidden />
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

/** Primary + secondary CTAs for SEO heroes — always point search traffic at signup. */
export function MarketingHeroCtas({
    primaryHref = "/register",
    primaryLabel = "Start free with Scotive",
    secondaryHref = "/integrations",
    secondaryLabel = "See integrations",
}) {
    return (
        <div className="mt-8 flex flex-wrap gap-3">
            <Link
                href={primaryHref}
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90"
            >
                {primaryLabel}
                <ArrowRight className="w-3.5 h-3.5" />
            </Link>
            <Link
                href={secondaryHref}
                className="inline-flex items-center rounded-xl border border-border px-5 py-2.5 text-sm font-medium hover:bg-muted"
            >
                {secondaryLabel}
            </Link>
        </div>
    );
}

/**
 * Mid-page conversion block: problem → Scotive value → signup.
 * Use on keyword landing pages so visitors see how Scotive solves their search intent.
 */
export function MarketingSolveBlock({
    title = "How Scotive solves this",
    problem,
    points = [],
    ctaLabel = "Start free — connect Gmail",
}) {
    return (
        <aside className="rounded-2xl border border-border bg-card px-5 py-6 md:px-8 md:py-8">
            <div className="eyebrow mb-2">Scotive</div>
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
                <Link
                    href="/register"
                    className="inline-flex items-center gap-1.5 rounded-xl bg-primary text-primary-foreground px-5 py-2.5 text-sm font-semibold hover:bg-primary/90"
                >
                    {ctaLabel}
                    <ArrowRight className="w-3.5 h-3.5" />
                </Link>
                <span className="text-xs text-muted-foreground">
                    Free to start · Nothing auto-sends · Disconnect anytime
                </span>
            </div>
        </aside>
    );
}

export function MarketingCta({
    title = "Stop rebuilding who owes you every Monday",
    description = "Scotive tracks unpaid invoices from Gmail and QuickBooks, drafts the next follow-up from real replies, and waits for your approval before anything sends.",
    buttonLabel = "Start free with Scotive",
}) {
    return (
        <section className="py-16 md:py-20">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="rounded-3xl ink-panel px-8 py-12 md:px-14 md:py-16 text-center relative overflow-hidden">
                    <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" aria-hidden />
                    <div className="relative">
                        <h2 className="type-display text-3xl md:text-4xl">{title}</h2>
                        <p className="type-body mt-4 opacity-80 max-w-xl mx-auto">{description}</p>
                        <ul className="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm opacity-80">
                            <li>See what&apos;s unpaid</li>
                            <li>Draft follow-ups in one click</li>
                            <li>You approve every send</li>
                        </ul>
                        <Link
                            href="/register"
                            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-background text-foreground px-7 py-3.5 font-semibold hover:opacity-95 transition-opacity shadow-lg"
                        >
                            {buttonLabel}
                            <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </div>
            </div>
        </section>
    );
}
