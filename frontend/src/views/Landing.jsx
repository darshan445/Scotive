import Link from "next/link";
import {
    AlertTriangle,
    ArrowRight,
    BellRing,
    BookOpen,
    Check,
    CheckCircle2,
    Clock,
    Eye,
    Inbox,
    Link2,
    Lock,
    MailCheck,
    MessageSquareQuote,
    Send,
    ShieldCheck,
    Wallet,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";

function SectionEyebrow({ children }) {
    return <div className="eyebrow mb-3">{children}</div>;
}

function PainCard({ quote, detail }) {
    return (
        <div className="surface-card p-6">
            <MessageSquareQuote className="w-5 h-5 text-accent mb-4" strokeWidth={2} />
            <p className="type-title text-lg leading-snug">{quote}</p>
            <p className="type-body mt-3 text-sm">{detail}</p>
        </div>
    );
}

function FeatureCard({ replaces, title, description, chips, icon: Icon }) {
    return (
        <div className="surface-card p-6 hover:shadow-md transition-shadow flex flex-col gap-4">
            <div className="flex items-center justify-between">
                <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/5 text-primary">
                    <Icon className="w-5 h-5" strokeWidth={2} />
                </span>
                <span className="text-[11px] font-medium text-muted-foreground bg-muted rounded-full px-2.5 py-1">
                    Replaces: {replaces}
                </span>
            </div>
            <div>
                <h3 className="type-title text-lg">{title}</h3>
                <p className="type-body mt-1.5 text-sm">{description}</p>
            </div>
            <div className="mt-auto flex flex-wrap gap-1.5">
                {chips.map((c) => (
                    <span key={c} className="text-[11px] font-medium text-primary/80 bg-primary/5 rounded-full px-2.5 py-1">
                        {c}
                    </span>
                ))}
            </div>
        </div>
    );
}

function OutcomeCard({ quote, metric, name, role }) {
    return (
        <div className="surface-card p-6 flex flex-col gap-4">
            <p className="type-body text-sm text-foreground/90">“{quote}”</p>
            <div className="mt-auto flex items-center justify-between gap-3">
                <div>
                    <div className="text-sm font-semibold text-foreground">{name}</div>
                    <div className="text-xs text-muted-foreground">{role}</div>
                </div>
                <span className="type-title text-sm text-accent bg-accent/10 rounded-full px-3 py-1 whitespace-nowrap">
                    {metric}
                </span>
            </div>
        </div>
    );
}

function HeroMockup() {
    const rows = [
        { icon: AlertTriangle, name: "Acme Studio", ref: "INV-2041", amount: "$2,400", tag: "Broken promise", tone: "red", action: "Firm follow-up" },
        { icon: BellRing, name: "Meraki Co.", ref: "INV-2044", amount: "$1,850", tag: "Promised Friday", tone: "amber", action: "Watching" },
        { icon: MessageSquareQuote, name: "Northwind", ref: "FS-413", amount: "$3,200", tag: "Needs your reply", tone: "slate", action: "Clarifying reply" },
        { icon: CheckCircle2, name: "Juliet Studio", ref: "INV-2038", amount: "$2,200", tag: "Paid yesterday", tone: "green", action: null },
    ];
    const toneText = {
        red: "text-red-600",
        amber: "text-amber-600",
        slate: "text-muted-foreground",
        green: "text-emerald-600",
    };
    return (
        <div
            className="rounded-3xl ink-panel p-3 shadow-2xl shadow-primary/20"
            role="img"
            aria-label="Invoice tracking dashboard showing broken promises and unpaid invoices"
        >
            <div className="rounded-2xl bg-card text-foreground overflow-hidden">
                <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                        <img
                            src="/scotive-mark.png"
                            alt="Scotive invoice tracking mark"
                            className="w-5 h-5 flex-shrink-0"
                            width={20}
                            height={20}
                        />
                        <span className="type-title text-sm truncate">Needs you today</span>
                    </div>
                    <span className="text-[11px] font-medium text-muted-foreground bg-muted rounded-full px-2.5 py-1 flex-shrink-0">
                        Email + accounting
                    </span>
                </div>
                <ul className="divide-y divide-border">
                    {rows.map((row) => (
                        <li key={row.name} className="px-5 py-3.5 flex items-center gap-3">
                            <row.icon className={`w-4 h-4 flex-shrink-0 ${toneText[row.tone]}`} />
                            <div className="min-w-0 flex-1">
                                <div className="flex items-baseline gap-2">
                                    <span className="text-sm font-semibold text-foreground truncate">{row.name}</span>
                                    <span className="text-[11px] font-mono text-muted-foreground">{row.ref}</span>
                                </div>
                                <span className={`text-[11px] ${toneText[row.tone]}`}>{row.tag}</span>
                            </div>
                            <div className="flex flex-col items-end gap-1 flex-shrink-0">
                                <span className="font-mono text-sm tabular-nums font-medium text-foreground">{row.amount}</span>
                                {row.action ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border border-border bg-muted/50 text-muted-foreground">
                                        {row.action}
                                    </span>
                                ) : null}
                            </div>
                        </li>
                    ))}
                </ul>
                <div className="px-5 py-3 bg-muted/40 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>Nothing sends without your approval</span>
                    <span className="font-mono tabular-nums">$7,450 open</span>
                </div>
            </div>
        </div>
    );
}

function StepConnectMock() {
    const rows = [
        { name: "Gmail", status: "Connected", on: true },
        { name: "QuickBooks Online", status: "Optional", on: true },
        { name: "Outlook · Zoho · FreshBooks", status: "Soon", on: false },
    ];
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground">Connect your stack</span>
                <span className="text-muted-foreground">OAuth 2.0</span>
            </div>
            {rows.map((row) => (
                <div key={row.name} className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-2">
                    <Link2 className={`w-3.5 h-3.5 flex-shrink-0 ${row.on ? "text-emerald-600" : "text-muted-foreground"}`} />
                    <span className="text-xs font-medium truncate min-w-0 text-foreground">{row.name}</span>
                    <span
                        className={`ml-auto flex-shrink-0 text-[10px] font-semibold rounded-full px-2 py-0.5 ${
                            row.on
                                ? "text-emerald-600 bg-emerald-50"
                                : "text-muted-foreground bg-muted"
                        }`}
                    >
                        {row.status}
                    </span>
                </div>
            ))}
        </div>
    );
}

function StepPickMock() {
    const items = [
        { name: "Acme Studio — $2,400", on: true },
        { name: "Meraki Co. — $1,850", on: true },
        { name: "Old retainer — $600", on: false },
    ];
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2">
            <div className="text-xs font-semibold mb-1 text-foreground">Which are still unpaid?</div>
            {items.map((it) => (
                <div key={it.name} className="flex items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2">
                    <span className={`w-4 h-4 rounded flex items-center justify-center ${it.on ? "bg-accent text-white" : "border border-border"}`}>
                        {it.on ? <Check className="w-3 h-3" /> : null}
                    </span>
                    <span className="text-xs text-foreground">{it.name}</span>
                </div>
            ))}
        </div>
    );
}

function StepApproveMock() {
    return (
        <div
            className="rounded-xl border border-border bg-background p-4 space-y-2.5"
            role="img"
            aria-label="Follow-up email composer for chasing an unpaid invoice"
        >
            <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-foreground truncate">Follow up with Acme Studio</span>
                <span className="text-[10px] font-medium text-muted-foreground border border-border bg-muted/50 rounded-full px-2 py-0.5 flex-shrink-0">
                    Firm follow-up
                </span>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                Hi Sarah — following up on INV-2041 ($2,400). You mentioned paying by last Friday…
            </div>
            <div className="flex gap-2">
                <span className="flex-1 text-center text-[11px] font-semibold bg-primary text-primary-foreground rounded-lg py-1.5">Approve &amp; send</span>
                <span className="text-[11px] font-medium text-muted-foreground border border-border rounded-lg py-1.5 px-3">Edit</span>
            </div>
        </div>
    );
}

function HowItWorksStep({ index, title, description, mock }) {
    return (
        <div className="surface-card p-6 flex flex-col gap-5" data-testid={`landing-how-step-${index}`}>
            <div className="flex items-center gap-3">
                <span className="eyebrow mb-0">Step 0{index}</span>
                <span className="h-px flex-1 bg-border" />
            </div>
            <div>
                <h3 className="type-title text-xl">{title}</h3>
                <p className="type-body mt-2 text-sm">{description}</p>
            </div>
            <div className="mt-auto">{mock}</div>
        </div>
    );
}

export default function LandingPage() {
    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid="landing-page">
            <header className="border-b border-border/70 bg-background/80 backdrop-blur-md sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
                    <BrandMark size="md" />
                    <div className="flex items-center gap-2 sm:gap-4">
                        <nav className="hidden md:flex items-center gap-1 text-sm">
                            <Link
                                href="/invoice-chasing-software"
                                className="px-3 py-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            >
                                Product
                            </Link>
                            <Link
                                href="/integrations"
                                className="px-3 py-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            >
                                Integrations
                            </Link>
                        </nav>
                        <Link
                            href="/login"
                            className="text-sm font-medium px-3 py-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            data-testid="landing-signin"
                        >
                            Log in
                        </Link>
                        <Link
                            href="/register"
                            className="inline-flex items-center gap-1.5 text-sm font-semibold bg-primary text-primary-foreground px-4 py-2 rounded-xl hover:bg-primary/90 transition-colors shadow-sm"
                            data-testid="landing-signup"
                        >
                            Start free
                            <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </div>
                </div>
            </header>

            <main className="flex-1">
                <section className="relative overflow-hidden" data-testid="landing-hero">
                    <div className="absolute inset-0 dot-grid pointer-events-none" aria-hidden />
                    <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-14 md:pt-20 pb-16 md:pb-24 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
                        <div className="animate-fade-up">
                            <div className="flex items-center gap-3 mb-6">
                                <img
                                    src="/scotive-mark.png"
                                    alt="Scotive"
                                    width={44}
                                    height={44}
                                    className="w-11 h-11"
                                />
                                <span className="type-display text-3xl sm:text-4xl">
                                    Scotive
                                </span>
                            </div>
                            <h1
                                className="type-display text-4xl sm:text-5xl lg:text-[3.25rem]"
                                data-testid="landing-headline"
                            >
                                Invoice chasing that lives where you work.
                            </h1>
                            <p className="type-body mt-5 text-base md:text-lg max-w-xl" data-testid="landing-subhead">
                                Track unpaid invoices from email and accounting, read client replies for promises and disputes, and approve every follow-up before it sends.
                            </p>

                            <div className="mt-8 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                                <Link
                                    href="/register"
                                    className="group inline-flex items-center gap-2.5 rounded-xl bg-primary text-primary-foreground px-6 py-3 font-semibold text-base transition-all shadow-md hover:shadow-lg active:scale-[0.98] hover:bg-primary/90"
                                    data-testid="landing-cta-primary"
                                >
                                    Start free
                                    <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
                                </Link>
                                <Link
                                    href="/integrations"
                                    className="text-sm font-medium text-muted-foreground hover:text-foreground"
                                    data-testid="landing-cta-secondary"
                                >
                                    See integrations →
                                </Link>
                            </div>

                            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                <span className="inline-flex items-center gap-1.5"><Lock className="w-3.5 h-3.5" /> Approval before every send</span>
                                <span className="inline-flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> Email + accounting</span>
                                <span className="inline-flex items-center gap-1.5"><MailCheck className="w-3.5 h-3.5" /> Signed as you</span>
                            </div>
                            <p className="mt-4 text-xs text-muted-foreground max-w-md">
                                Live today: Gmail &amp; QuickBooks Online. Next: Outlook, Zoho Books, FreshBooks.
                            </p>
                        </div>

                        <div className="animate-fade-up lg:pl-4" style={{ animationDelay: "120ms" }} data-testid="landing-preview-card">
                            <HeroMockup />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-pain">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Sound familiar?</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                You did the work. Now you&apos;re doing collections too.
                            </h2>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <PainCard
                                quote="Did they ever pay that March invoice?"
                                detail="Scrolling months of sent mail to reconstruct who owes what — every single week."
                            />
                            <PainCard
                                quote="They said 'paying Friday' two Fridays ago"
                                detail="Promises get buried in reply chains. Nobody tracks whether they were kept."
                            />
                            <PainCard
                                quote="I hate writing the awkward nudge"
                                detail="Chasing feels rude, so it gets postponed — and postponed invoices become forgotten ones."
                            />
                            <PainCard
                                quote="I found an unpaid invoice from months ago"
                                detail="No system means silent leaks. Every forgotten invoice is money you already earned."
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-how-it-works">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex flex-wrap items-end justify-between gap-4 mb-12">
                            <div className="max-w-2xl">
                                <SectionEyebrow>Simple setup</SectionEyebrow>
                                <h2 className="type-title text-3xl md:text-4xl">
                                    Connect your tools. Scotive runs the chase.
                                </h2>
                            </div>
                            <span className="pill">3 steps · about a minute</span>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <HowItWorksStep
                                index={1}
                                title="Connect email &amp; accounting"
                                description="Start with Gmail today — optionally add QuickBooks Online. Outlook, Zoho Books, and FreshBooks are on the roadmap."
                                mock={<StepConnectMock />}
                            />
                            <HowItWorksStep
                                index={2}
                                title="Pick what's still unpaid"
                                description="Scotive finds open invoices from email and your accounting feed. Confirm what's open — you know your work; we build the ledger."
                                mock={<StepPickMock />}
                            />
                            <HowItWorksStep
                                index={3}
                                title="Approve the follow-ups"
                                description="When something is late or a promise breaks, a draft appears with a state-derived tone. Edit, regenerate, or send — never auto-sent."
                                mock={<StepApproveMock />}
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-integrations">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Not locked to one stack</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Built for the tools you already use.
                            </h2>
                            <p className="type-body mt-3">
                                Invoice chasing across email and accounting — available connectors first, more without changing how you work.
                            </p>
                        </div>
                        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
                            {[
                                { name: "Gmail", status: "Available", on: true },
                                { name: "QuickBooks Online", status: "Available", on: true, href: "/quickbooks-invoice-chasing" },
                                { name: "Outlook", status: "Coming soon", on: false, href: "/outlook-invoice-chasing" },
                                { name: "Zoho Books", status: "Coming soon", on: false, href: "/zoho-books-invoice-chasing" },
                                { name: "FreshBooks", status: "Coming soon", on: false, href: "/freshbooks-invoice-chasing" },
                            ].map((item) => {
                                const card = (
                                    <div className="surface-card p-4 h-full flex flex-col gap-2">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="type-title text-base">{item.name}</span>
                                            {item.on ? (
                                                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                                            ) : (
                                                <Clock className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                                            )}
                                        </div>
                                        <span className="text-xs text-muted-foreground">{item.status}</span>
                                    </div>
                                );
                                return item.href ? (
                                    <Link key={item.name} href={item.href} className="block hover:opacity-95 transition-opacity">
                                        {card}
                                    </Link>
                                ) : (
                                    <div key={item.name}>{card}</div>
                                );
                            })}
                        </div>
                        <div className="mt-6">
                            <Link
                                href="/integrations"
                                className="text-sm font-medium text-primary hover:underline underline-offset-2"
                            >
                                Full integrations roadmap →
                            </Link>
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-features">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>What you get</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                A collections brain for email + accounting.
                            </h2>
                            <p className="type-body mt-3">
                                Scotive surfaces what needs you today — past due, broken promises, replies — and drafts the next move.
                            </p>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <FeatureCard
                                icon={Inbox}
                                replaces="inbox archaeology"
                                title="Automatic invoice tracking"
                                description="Detect invoices from email and optional accounting feeds. Track amounts, clients, and due dates in one ledger."
                                chips={["Email watching", "Accounting import", "Ledger by client"]}
                            />
                            <FeatureCard
                                icon={MessageSquareQuote}
                                replaces="memory & sticky notes"
                                title="Reply & promise intelligence"
                                description="Reads client replies for promises, disputes, and payment claims — and flags when a promise date slips."
                                chips={["Promise dates", "Broken-promise alerts", "Dispute rounds"]}
                            />
                            <FeatureCard
                                icon={Send}
                                replaces="awkward nudge writing"
                                title="State-derived follow-ups"
                                description="Drafts match the invoice state — Friendly reminder, Firm follow-up, Final notice, or Clarifying reply — signed as you."
                                chips={["Tone from ledger state", "Same-thread replies", "One-tap approve"]}
                            />
                            <FeatureCard
                                icon={Wallet}
                                replaces="manual reconciliation"
                                title="Payment matching"
                                description="Receipts and “says paid” claims land on the right invoice. Confirm received, or mark not yet — partials tracked. QBO paid sync when connected."
                                chips={["Receipt matching", "Partial payments", "Paid sync"]}
                            />
                            <FeatureCard
                                icon={Eye}
                                replaces="constant checking-in"
                                title="Needs you today"
                                description="One prioritized list: past due, broken promises, replies, and confirmations. Optional daily digest."
                                chips={["Priority-first", "Daily digest", "Review queue"]}
                            />
                            <FeatureCard
                                icon={ShieldCheck}
                                replaces="trust-me automation"
                                title="You stay in control"
                                description="Nothing is ever auto-sent. OAuth connectors only. Disconnect anytime. Content isn’t used to train Scotive’s models."
                                chips={["Approval-only", "OAuth 2.0", "Delete account anytime"]}
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-seo-links">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-10">
                            <SectionEyebrow>Explore</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Guides for getting paid faster.
                            </h2>
                        </div>
                        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            {[
                                {
                                    href: "/invoice-chasing-software",
                                    icon: BookOpen,
                                    title: "Invoice chasing software",
                                    detail: "How Scotive compares to heavy AR suites.",
                                },
                                {
                                    href: "/chase-unpaid-invoices",
                                    icon: BellRing,
                                    title: "Chase unpaid invoices",
                                    detail: "Human-approved follow-ups that actually get sent.",
                                },
                                {
                                    href: "/accounts-receivable-automation",
                                    icon: Wallet,
                                    title: "AR automation",
                                    detail: "Automation with a human gate — not fire-and-forget.",
                                },
                                {
                                    href: "/overdue-invoice-reminder",
                                    icon: AlertTriangle,
                                    title: "Overdue invoice reminders",
                                    detail: "Tone that matches how late the invoice really is.",
                                },
                            ].map((item) => (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className="surface-card p-5 hover:shadow-md transition-shadow block"
                                >
                                    <item.icon className="w-5 h-5 text-accent mb-3" strokeWidth={2} />
                                    <h3 className="type-title text-base">{item.title}</h3>
                                    <p className="type-body mt-1.5 text-sm">{item.detail}</p>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-who">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-10">
                            <SectionEyebrow>Who it&apos;s for</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Anyone who bills clients and follows up on payment.
                            </h2>
                            <p className="type-body mt-3">
                                Scotive isn&apos;t locked to one job title — if you send invoices and chase unpaid ones, it fits.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {[
                                "Freelancers",
                                "Agencies",
                                "Consultants",
                                "Studios & creative teams",
                                "Professional services",
                                "Small businesses",
                                "Founders & ops",
                                "Finance & AR owners",
                            ].map((label) => (
                                <span
                                    key={label}
                                    className="text-sm font-medium text-foreground/80 bg-muted rounded-full px-3.5 py-1.5"
                                >
                                    {label}
                                </span>
                            ))}
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-outcomes">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Built for people who bill and chase</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Stop leaking revenue to forgotten invoices.
                            </h2>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <OutcomeCard
                                quote="I used to spend Sunday nights going through sent mail to figure out who to nudge. Now it's a short approval pass with coffee."
                                metric="Sundays back"
                                name="Freelance designer"
                                role="Independent · 12 active clients"
                            />
                            <OutcomeCard
                                quote="A client promised payment three times. Scotive caught every date and drafted a firmer follow-up. Paid in full the next week."
                                metric="0 awkward emails"
                                name="Agency ops lead"
                                role="12-person agency"
                            />
                            <OutcomeCard
                                quote="Seed curation found an invoice I'd completely forgotten. That one recovery covered a year of any tool I could buy."
                                metric="Recovered cash"
                                name="Services founder"
                                role="B2B professional services"
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-28" data-testid="landing-final-cta">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="rounded-3xl ink-panel px-8 py-14 md:px-16 md:py-20 text-center relative overflow-hidden">
                            <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" aria-hidden />
                            <div className="relative">
                                <div className="flex justify-center mb-6">
                                    <img src="/scotive-icon.png" alt="Scotive" width={56} height={56} className="w-14 h-14 rounded-2xl" />
                                </div>
                                <h2 className="type-display text-3xl md:text-5xl">
                                    Get paid without the awkward chase.
                                </h2>
                                <p className="type-body mt-4 text-base md:text-lg opacity-80 max-w-xl mx-auto">
                                    Connect email today. Add accounting when you&apos;re ready. Approve your first follow-up before your coffee gets cold.
                                </p>
                                <div className="mt-9 flex flex-col sm:flex-row items-center justify-center gap-4">
                                    <Link
                                        href="/register"
                                        className="inline-flex items-center gap-2.5 rounded-xl bg-background text-foreground px-7 py-3.5 font-semibold text-base hover:opacity-95 transition-opacity shadow-lg"
                                        data-testid="landing-cta-final"
                                    >
                                        Start free
                                        <ArrowRight className="w-4 h-4" />
                                    </Link>
                                </div>
                                <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs opacity-70">
                                    <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5" /> Free to start</span>
                                    <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5" /> No card required</span>
                                    <span className="inline-flex items-center gap-1.5"><Check className="w-3.5 h-3.5" /> Nothing auto-sent, ever</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </main>

            <footer className="border-t border-border mt-auto">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid gap-10 md:grid-cols-4">
                    <div className="md:col-span-2">
                        <BrandMark />
                        <p className="type-body mt-3 text-sm max-w-xs">
                            Invoice chasing for freelancers, agencies, and any team that bills clients — email + accounting, human-approved follow-ups.
                        </p>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Product</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/invoice-chasing-software" className="hover:text-foreground">Invoice chasing software</Link></li>
                            <li><Link href="/chase-unpaid-invoices" className="hover:text-foreground">Chase unpaid invoices</Link></li>
                            <li><Link href="/accounts-receivable-automation" className="hover:text-foreground">AR automation</Link></li>
                            <li><Link href="/integrations" className="hover:text-foreground">Integrations</Link></li>
                            <li><Link href="/register" className="hover:text-foreground">Get started</Link></li>
                        </ul>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Legal</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link href="/terms" className="hover:text-foreground">Terms of Service</Link></li>
                            <li><Link href="/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
                            <li>OAuth 2.0 · disconnect anytime</li>
                        </ul>
                    </div>
                </div>
                <div className="border-t border-border">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground">
                        <span>© {new Date().getFullYear()} Scotive. All rights reserved.</span>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                            <Link href="/terms" className="hover:text-foreground">Terms</Link>
                            <Link href="/privacy" className="hover:text-foreground">Privacy</Link>
                            <span>Get paid faster · You approve every send</span>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}
