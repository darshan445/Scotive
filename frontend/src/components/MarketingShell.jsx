import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";

/**
 * Shared chrome for public SEO / marketing pages (non-auth).
 * Keeps visual language aligned with the main landing.
 */
export function MarketingShell({
    children,
    testId = "marketing-page",
    activePath = "",
}) {
    const nav = [
        { href: "/invoice-chasing-software", label: "Invoice chasing" },
        { href: "/chase-unpaid-invoices", label: "Unpaid invoices" },
        { href: "/accounts-receivable-automation", label: "AR automation" },
        { href: "/integrations", label: "Integrations" },
    ];

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid={testId}>
            <header className="border-b border-border/70 bg-background/80 backdrop-blur-md sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
                    <BrandMark size="md" />
                    <nav className="hidden lg:flex items-center gap-1 text-sm">
                        {nav.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`px-3 py-1.5 rounded-lg transition-colors ${
                                    activePath === item.href
                                        ? "text-foreground bg-muted font-medium"
                                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                                }`}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </nav>
                    <div className="flex items-center gap-2 sm:gap-3">
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
                            Invoice chasing software for freelancers and small teams — email + accounting,
                            human-approved follow-ups.
                        </p>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Product</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/" className="hover:text-foreground">Home</Link></li>
                            <li><Link href="/invoice-chasing-software" className="hover:text-foreground">Invoice chasing software</Link></li>
                            <li><Link href="/chase-unpaid-invoices" className="hover:text-foreground">Chase unpaid invoices</Link></li>
                            <li><Link href="/accounts-receivable-automation" className="hover:text-foreground">AR automation</Link></li>
                            <li><Link href="/overdue-invoice-reminder" className="hover:text-foreground">Overdue invoice reminders</Link></li>
                            <li><Link href="/integrations" className="hover:text-foreground">Integrations</Link></li>
                            <li><Link href="/quickbooks-invoice-chasing" className="hover:text-foreground">QuickBooks invoice chasing</Link></li>
                            <li><Link href="/outlook-invoice-chasing" className="hover:text-foreground">Outlook invoice chasing</Link></li>
                            <li><Link href="/zoho-books-invoice-chasing" className="hover:text-foreground">Zoho Books</Link></li>
                            <li><Link href="/freshbooks-invoice-chasing" className="hover:text-foreground">FreshBooks</Link></li>
                            <li><Link href="/register" className="hover:text-foreground">Get started</Link></li>
                        </ul>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Legal</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/terms" className="hover:text-foreground">Terms of Service</Link></li>
                            <li><Link href="/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
                            <li><a href="mailto:support@scotive.com" className="hover:text-foreground">support@scotive.com</a></li>
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

export function MarketingCta() {
    return (
        <section className="py-16 md:py-20">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="rounded-3xl ink-panel px-8 py-12 md:px-14 md:py-16 text-center relative overflow-hidden">
                    <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" aria-hidden />
                    <div className="relative">
                        <h2 className="type-display text-3xl md:text-4xl">
                            Start chasing unpaid invoices the calm way
                        </h2>
                        <p className="type-body mt-4 opacity-80 max-w-xl mx-auto">
                            Connect email today. Add accounting when you&apos;re ready. Nothing sends without your approval.
                        </p>
                        <Link
                            href="/register"
                            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-background text-foreground px-7 py-3.5 font-semibold hover:opacity-95 transition-opacity shadow-lg"
                        >
                            Start free
                            <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </div>
            </div>
        </section>
    );
}
