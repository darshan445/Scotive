import { Link } from "react-router-dom";
import {
    AlertTriangle,
    ArrowRight,
    BellRing,
    Check,
    CheckCircle2,
    Eye,
    Inbox,
    Lock,
    MailCheck,
    MessageSquareQuote,
    Send,
    ShieldCheck,
    Sparkles,
    Wallet,
} from "lucide-react";
import { FcGoogle } from "react-icons/fc";
import { BrandMark } from "@/components/BrandMark";

/* ---------------------------------------------------------------- */
/* Small building blocks                                            */
/* ---------------------------------------------------------------- */

function SectionEyebrow({ children }) {
    return <div className="eyebrow mb-3">{children}</div>;
}

function PainCard({ quote, detail }) {
    return (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <MessageSquareQuote className="w-5 h-5 text-accent mb-4" strokeWidth={2} />
            <p className="font-heading font-semibold text-lg leading-snug text-foreground">
                “{quote}”
            </p>
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{detail}</p>
        </div>
    );
}

function FeatureCard({ replaces, title, description, chips, icon: Icon }) {
    return (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm hover:shadow-md transition-shadow flex flex-col gap-4">
            <div className="flex items-center justify-between">
                <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/5 text-primary">
                    <Icon className="w-5 h-5" strokeWidth={2} />
                </span>
                <span className="text-[11px] font-medium text-muted-foreground bg-muted rounded-full px-2.5 py-1">
                    Replaces: {replaces}
                </span>
            </div>
            <div>
                <h3 className="font-heading font-semibold text-lg tracking-tight">{title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{description}</p>
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
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm flex flex-col gap-4">
            <p className="text-sm leading-relaxed text-foreground">“{quote}”</p>
            <div className="mt-auto flex items-center justify-between">
                <div>
                    <div className="text-sm font-semibold">{name}</div>
                    <div className="text-xs text-muted-foreground">{role}</div>
                </div>
                <span className="font-heading font-bold text-accent text-sm bg-accent/10 rounded-full px-3 py-1">
                    {metric}
                </span>
            </div>
        </div>
    );
}

/* ---------------------------------------------------------------- */
/* Product mockup used in the hero                                  */
/* ---------------------------------------------------------------- */

function HeroMockup() {
    const rows = [
        { icon: AlertTriangle, name: "Acme Studio", ref: "INV-2041", amount: "$2,400", tag: "4 days past due", tone: "red", action: "Approve follow-up" },
        { icon: BellRing, name: "Meraki Co.", ref: "INV-2044", amount: "$1,850", tag: "Promised Friday", tone: "amber", action: "Watching promise" },
        { icon: Eye, name: "Northwind", ref: "INV-2046", amount: "₹84,700", tag: "Reading replies", tone: "slate", action: null },
        { icon: CheckCircle2, name: "Juliet Studio", ref: "INV-2038", amount: "$2,200", tag: "Paid yesterday", tone: "green", action: null },
    ];
    const toneText = {
        red: "text-red-600",
        amber: "text-amber-600",
        slate: "text-muted-foreground",
        green: "text-emerald-600",
    };
    return (
        <div className="rounded-3xl ink-panel p-3 shadow-2xl shadow-primary/20">
            <div className="rounded-2xl bg-card text-foreground overflow-hidden">
                <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        <span className="text-sm font-semibold font-heading">Needs you today</span>
                    </div>
                    <span className="text-[11px] font-medium text-muted-foreground bg-muted rounded-full px-2.5 py-1">
                        Watching Gmail · live
                    </span>
                </div>
                <ul className="divide-y divide-border">
                    {rows.map((row) => (
                        <li key={row.name} className="px-5 py-3.5 flex items-center gap-3">
                            <row.icon className={`w-4 h-4 flex-shrink-0 ${toneText[row.tone]}`} />
                            <div className="min-w-0 flex-1">
                                <div className="flex items-baseline gap-2">
                                    <span className="text-sm font-semibold truncate">{row.name}</span>
                                    <span className="text-[11px] font-mono text-muted-foreground">{row.ref}</span>
                                </div>
                                <span className={`text-[11px] ${toneText[row.tone]}`}>{row.tag}</span>
                            </div>
                            <div className="flex flex-col items-end gap-1 flex-shrink-0">
                                <span className="font-mono text-sm tabular-nums font-medium">{row.amount}</span>
                                {row.action ? (
                                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent">
                                        <Send className="w-3 h-3" /> {row.action}
                                    </span>
                                ) : null}
                            </div>
                        </li>
                    ))}
                </ul>
                <div className="px-5 py-3 bg-muted/40 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>Nothing sends without your approval</span>
                    <span className="font-mono tabular-nums">$6,450 outstanding</span>
                </div>
            </div>
        </div>
    );
}

/* ---------------------------------------------------------------- */
/* Step mockups for "How it works"                                  */
/* ---------------------------------------------------------------- */

function StepConnectMock() {
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold">Connect your Gmail</span>
                <span className="text-muted-foreground">OAuth 2.0</span>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-2">
                <FcGoogle className="w-4 h-4 flex-shrink-0" />
                <span className="text-xs font-medium truncate min-w-0">you@yourstudio.com</span>
                <span className="ml-auto flex-shrink-0 text-[10px] font-semibold text-emerald-600 bg-emerald-50 rounded-full px-2 py-0.5">Connected</span>
            </div>
            <div className="text-[10px] text-muted-foreground">
                Read + send-with-approval only · revoke anytime
            </div>
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
            <div className="text-xs font-semibold mb-1">Which of these are still unpaid?</div>
            {items.map((it) => (
                <div key={it.name} className="flex items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2">
                    <span className={`w-4 h-4 rounded flex items-center justify-center ${it.on ? "bg-accent text-white" : "border border-border"}`}>
                        {it.on ? <Check className="w-3 h-3" /> : null}
                    </span>
                    <span className="text-xs">{it.name}</span>
                </div>
            ))}
        </div>
    );
}

function StepApproveMock() {
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold">Follow-up draft · Acme Studio</span>
                <span className="text-[10px] font-medium text-amber-700 bg-amber-50 rounded-full px-2 py-0.5">Awaiting you</span>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                Hi Sarah — just a gentle nudge on invoice INV-2041 ($2,400), which was due last Friday…
            </div>
            <div className="flex gap-2">
                <span className="flex-1 text-center text-[11px] font-semibold bg-primary text-primary-foreground rounded-lg py-1.5">Send in thread</span>
                <span className="text-[11px] font-medium text-muted-foreground border border-border rounded-lg py-1.5 px-3">Edit</span>
            </div>
        </div>
    );
}

function HowItWorksStep({ index, title, description, mock }) {
    return (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm flex flex-col gap-5" data-testid={`landing-how-step-${index}`}>
            <div className="flex items-center gap-3">
                <span className="font-heading font-bold text-sm text-accent">Step 0{index}</span>
                <span className="h-px flex-1 bg-border" />
            </div>
            <div>
                <h3 className="font-heading font-semibold text-xl tracking-tight">{title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{description}</p>
            </div>
            <div className="mt-auto">{mock}</div>
        </div>
    );
}

/* ---------------------------------------------------------------- */
/* Page                                                             */
/* ---------------------------------------------------------------- */

export default function LandingPage() {
    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid="landing-page">
            {/* ------------------------------------------------ header */}
            <header className="border-b border-border/70 bg-background/80 backdrop-blur-md sticky top-0 z-30">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <BrandMark />
                    <nav className="flex items-center gap-2 sm:gap-4">
                        <Link
                            to="/login"
                            className="text-sm font-medium px-3 py-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            data-testid="landing-signin"
                        >
                            Log in
                        </Link>
                        <Link
                            to="/register"
                            className="inline-flex items-center gap-1.5 text-sm font-semibold bg-primary text-primary-foreground px-4 py-2 rounded-xl hover:bg-primary/90 transition-colors shadow-sm"
                            data-testid="landing-signup"
                        >
                            Start free
                            <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </nav>
                </div>
            </header>

            <main className="flex-1">
                {/* -------------------------------------------- hero */}
                <section className="relative overflow-hidden" data-testid="landing-hero">
                    <div className="absolute inset-0 dot-grid pointer-events-none" aria-hidden />
                    <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 md:pt-24 pb-16 md:pb-24 grid lg:grid-cols-2 gap-14 items-center">
                        <div className="animate-fade-up">
                            <div className="pill mb-6">
                                <Sparkles className="w-3.5 h-3.5 text-accent" />
                                Invoice chasing on autopilot — inside Gmail
                            </div>
                            <h1
                                className="font-heading font-extrabold text-4xl sm:text-5xl lg:text-[3.6rem] leading-[1.05] tracking-tight"
                                data-testid="landing-headline"
                            >
                                Every unpaid invoice.
                                <br />
                                <span className="text-accent">Found, tracked, chased.</span>
                            </h1>
                            <p className="mt-6 text-lg text-muted-foreground leading-relaxed max-w-xl" data-testid="landing-subhead">
                                Scotive watches the invoices you already send from Gmail, reads client replies,
                                catches promises like “we'll pay Friday”, and drafts the follow-up when they don't.
                                You just approve.
                            </p>

                            <div className="mt-9 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                                <Link
                                    to="/register"
                                    className="group inline-flex items-center gap-3 rounded-xl bg-primary text-primary-foreground pl-2 pr-6 py-2 font-semibold text-base transition-all shadow-md hover:shadow-lg active:scale-[0.98] hover:bg-primary/90"
                                    data-testid="landing-cta-primary"
                                >
                                    <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-background">
                                        <FcGoogle className="w-5 h-5" />
                                    </span>
                                    Connect Gmail — free
                                    <ArrowRight className="w-4 h-4 opacity-70 transition-transform group-hover:translate-x-0.5" />
                                </Link>
                                <Link
                                    to="/login"
                                    className="text-sm font-medium text-muted-foreground hover:text-foreground"
                                    data-testid="landing-cta-secondary"
                                >
                                    I already have an account →
                                </Link>
                            </div>

                            <div className="mt-8 grid grid-cols-3 max-w-md gap-4" data-testid="landing-hero-stats">
                                {[
                                    ["60s", "to set up"],
                                    ["0", "auto-sent emails"],
                                    ["24/7", "reply watching"],
                                ].map(([n, l]) => (
                                    <div key={l}>
                                        <div className="stat-number font-bold text-2xl">{n}</div>
                                        <div className="text-xs text-muted-foreground mt-0.5">{l}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="animate-fade-up lg:pl-6" style={{ animationDelay: "120ms" }} data-testid="landing-preview-card">
                            <HeroMockup />
                            <div className="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
                                <span className="inline-flex items-center gap-1.5"><Lock className="w-3.5 h-3.5" /> Only 2 Gmail permissions</span>
                                <span className="inline-flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> Never trains AI on your email</span>
                                <span className="inline-flex items-center gap-1.5"><MailCheck className="w-3.5 h-3.5" /> Sends from your address</span>
                            </div>
                        </div>
                    </div>
                </section>

                {/* -------------------------------------------- pain points */}
                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-pain">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Sound familiar?</SectionEyebrow>
                            <h2 className="font-heading font-bold text-3xl md:text-4xl tracking-tight">
                                You did the work. Now you're doing collections too.
                            </h2>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <PainCard
                                quote="Did they ever pay that March invoice?"
                                detail="Scrolling months of Gmail threads to reconstruct who owes what — every single week."
                            />
                            <PainCard
                                quote="They said 'paying Friday' two Fridays ago"
                                detail="Client promises get buried in reply chains. No one is tracking whether they were kept."
                            />
                            <PainCard
                                quote="I hate writing the awkward nudge email"
                                detail="Chasing feels rude, so it gets postponed. Postponed invoices become forgotten ones."
                            />
                            <PainCard
                                quote="I found an unpaid invoice from 5 months ago"
                                detail="No system means silent leaks. Every forgotten invoice is money you already earned."
                            />
                        </div>
                    </div>
                </section>

                {/* -------------------------------------------- how it works */}
                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-how-it-works">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex flex-wrap items-end justify-between gap-4 mb-12">
                            <div className="max-w-2xl">
                                <SectionEyebrow>Simple setup, zero new habits</SectionEyebrow>
                                <h2 className="font-heading font-bold text-3xl md:text-4xl tracking-tight">
                                    Keep invoicing from Gmail. Scotive does the rest.
                                </h2>
                            </div>
                            <span className="pill">3 steps · about 60 seconds</span>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <HowItWorksStep
                                index={1}
                                title="Connect your Gmail"
                                description="One click, two permissions: read, and send-with-your-approval. We never see your password, and you can revoke anytime."
                                mock={<StepConnectMock />}
                            />
                            <HowItWorksStep
                                index={2}
                                title="Pick what's still unpaid"
                                description="Scotive finds invoices you sent in the last 90 days and shows you a pick-list. Tap the ones still open — you know your work cold."
                                mock={<StepPickMock />}
                            />
                            <HowItWorksStep
                                index={3}
                                title="Approve the follow-ups"
                                description="When a payment is late or a promise breaks, a draft appears — written in your voice, sent in the same thread. Nothing goes out without you."
                                mock={<StepApproveMock />}
                            />
                        </div>
                    </div>
                </section>

                {/* -------------------------------------------- features */}
                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-features">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>What you get</SectionEyebrow>
                            <h2 className="font-heading font-bold text-3xl md:text-4xl tracking-tight">
                                A collections brain, not another dashboard.
                            </h2>
                            <p className="mt-3 text-muted-foreground">
                                Scotive surfaces the 3 things that need you today — and quietly handles the rest.
                            </p>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <FeatureCard
                                icon={Inbox}
                                replaces="inbox archaeology"
                                title="Automatic invoice tracking"
                                description="Send invoices like you always do. Scotive detects them in sent mail and starts tracking — amounts, due dates, clients."
                                chips={["Live Gmail watching", "Auto due dates", "Multi-currency"]}
                            />
                            <FeatureCard
                                icon={MessageSquareQuote}
                                replaces="memory & sticky notes"
                                title="Reply & promise intelligence"
                                description="Reads client replies, extracts promises like “this Friday”, and flags the moment a promise breaks."
                                chips={["Promise dates", "Broken-promise alerts", "Dispute detection"]}
                            />
                            <FeatureCard
                                icon={Send}
                                replaces="awkward nudge writing"
                                title="Follow-ups in your voice"
                                description="Escalating drafts — gentle nudge to final notice — written for each client and sent in the original thread. You approve every one."
                                chips={["Same-thread replies", "Tone ladder", "One-tap approve"]}
                            />
                            <FeatureCard
                                icon={Wallet}
                                replaces="manual reconciliation"
                                title="Payment matching"
                                description="Stripe and PayPal receipts are matched to open invoices automatically. Partial payments tracked to the cent."
                                chips={["Receipt matching", "Partial payments", "Says-paid confirmations"]}
                            />
                            <FeatureCard
                                icon={Eye}
                                replaces="constant checking-in"
                                title="A daily 'Needs you' list"
                                description="One prioritized list each day: what's past due, who broke a promise, what to confirm. Usually under a minute of your time."
                                chips={["Priority-first", "Daily digest email", "Zero noise"]}
                            />
                            <FeatureCard
                                icon={ShieldCheck}
                                replaces="trust-me automation"
                                title="You stay in control"
                                description="Nothing is ever auto-sent. Two Gmail permissions only. Your emails are never used to train AI models."
                                chips={["Approval-only sending", "OAuth 2.0", "Disconnect anytime"]}
                            />
                        </div>
                    </div>
                </section>

                {/* -------------------------------------------- outcomes */}
                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-outcomes">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Built for people who bill from their inbox</SectionEyebrow>
                            <h2 className="font-heading font-bold text-3xl md:text-4xl tracking-tight">
                                Freelancers and studios stop leaking revenue.
                            </h2>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <OutcomeCard
                                quote="I used to spend Sunday nights going through sent mail to figure out who to nudge. Now it's a 40-second approval pass with coffee."
                                metric="Sundays back"
                                name="Freelance designer"
                                role="Solo · 12 active clients"
                            />
                            <OutcomeCard
                                quote="A client promised payment three times. Scotive caught every date and escalated the tone politely. Paid in full the next week."
                                metric="0 awkward emails"
                                name="Studio founder"
                                role="4-person agency"
                            />
                            <OutcomeCard
                                quote="It found an invoice I'd completely forgotten about. That one recovery covered a year of any tool I could buy."
                                metric="$3,600 recovered"
                                name="Consultant"
                                role="B2B advisory"
                            />
                        </div>
                    </div>
                </section>

                {/* -------------------------------------------- final CTA */}
                <section className="py-20 md:py-28" data-testid="landing-final-cta">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="rounded-3xl ink-panel px-8 py-14 md:px-16 md:py-20 text-center relative overflow-hidden">
                            <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" aria-hidden />
                            <div className="relative">
                                <h2 className="font-heading font-extrabold text-3xl md:text-5xl tracking-tight leading-tight">
                                    Get paid without chasing.
                                </h2>
                                <p className="mt-4 text-base md:text-lg opacity-80 max-w-xl mx-auto">
                                    Connect in under a minute. Approve your first follow-up before your coffee gets cold.
                                </p>
                                <div className="mt-9 flex flex-col sm:flex-row items-center justify-center gap-4">
                                    <Link
                                        to="/register"
                                        className="inline-flex items-center gap-2.5 rounded-xl bg-background text-foreground px-7 py-3.5 font-semibold text-base hover:opacity-95 transition-opacity shadow-lg"
                                        data-testid="landing-cta-final"
                                    >
                                        <FcGoogle className="w-5 h-5" />
                                        Start free with Gmail
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

            {/* ------------------------------------------------ footer */}
            <footer className="border-t border-border mt-auto">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid gap-10 md:grid-cols-4">
                    <div className="md:col-span-2">
                        <BrandMark />
                        <p className="mt-3 text-sm text-muted-foreground max-w-xs leading-relaxed">
                            Invoice chasing on autopilot — for everyone who bills from Gmail.
                        </p>
                    </div>
                    <div>
                        <div className="text-sm font-semibold mb-3">Product</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link to="/register" className="hover:text-foreground">Get started</Link></li>
                            <li><Link to="/login" className="hover:text-foreground">Log in</Link></li>
                        </ul>
                    </div>
                    <div>
                        <div className="text-sm font-semibold mb-3">Legal</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link to="/terms" className="hover:text-foreground">Terms of Service</Link></li>
                            <li><Link to="/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
                            <li>OAuth 2.0 · disconnect anytime</li>
                        </ul>
                    </div>
                </div>
                <div className="border-t border-border">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-wrap justify-between items-center gap-3 text-xs text-muted-foreground">
                        <span>© {new Date().getFullYear()} Scotive. All rights reserved.</span>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                            <Link to="/terms" className="hover:text-foreground">Terms</Link>
                            <Link to="/privacy" className="hover:text-foreground">Privacy</Link>
                            <span>Payment ops · Inside Gmail</span>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}
