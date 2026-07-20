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
    Wallet,
} from "lucide-react";
import { FcGoogle } from "react-icons/fc";
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
        <div className="rounded-3xl ink-panel p-3 shadow-2xl shadow-primary/20">
            <div className="rounded-2xl bg-card text-foreground overflow-hidden">
                <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                        <img src="/scotive-mark.png" alt="" className="w-5 h-5 flex-shrink-0" width={20} height={20} />
                        <span className="type-title text-sm truncate">Needs you today</span>
                    </div>
                    <span className="text-[11px] font-medium text-muted-foreground bg-muted rounded-full px-2.5 py-1 flex-shrink-0">
                        Watching Gmail
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
    return (
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground">Connect your Gmail</span>
                <span className="text-muted-foreground">OAuth 2.0</span>
            </div>
            <div className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-2">
                <FcGoogle className="w-4 h-4 flex-shrink-0" />
                <span className="text-xs font-medium truncate min-w-0 text-foreground">you@yourstudio.com</span>
                <span className="ml-auto flex-shrink-0 text-[10px] font-semibold text-emerald-600 bg-emerald-50 rounded-full px-2 py-0.5">Connected</span>
            </div>
            <div className="text-[10px] text-muted-foreground">
                Read + send-with-approval · revoke anytime
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
        <div className="rounded-xl border border-border bg-background p-4 space-y-2.5">
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
                <span className="flex-1 text-center text-[11px] font-semibold bg-primary text-primary-foreground rounded-lg py-1.5">Send from Gmail</span>
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
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <BrandMark size="md" />
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
                <section className="relative overflow-hidden" data-testid="landing-hero">
                    <div className="absolute inset-0 dot-grid pointer-events-none" aria-hidden />
                    <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-14 md:pt-20 pb-16 md:pb-24 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
                        <div className="animate-fade-up">
                            <div className="flex items-center gap-3 mb-6">
                                <img
                                    src="/scotive-mark.png"
                                    alt=""
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
                                Payment ops inside Gmail.
                            </h1>
                            <p className="type-body mt-5 text-base md:text-lg max-w-xl" data-testid="landing-subhead">
                                Track invoices you send, read client replies, and draft follow-ups with the right tone — then send from your own Gmail only when you approve.
                            </p>

                            <div className="mt-8 flex flex-col sm:flex-row items-start sm:items-center gap-4">
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

                            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                                <span className="inline-flex items-center gap-1.5"><Lock className="w-3.5 h-3.5" /> Read + send only</span>
                                <span className="inline-flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> Approval before every send</span>
                                <span className="inline-flex items-center gap-1.5"><MailCheck className="w-3.5 h-3.5" /> Signed with your name</span>
                            </div>
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
                                    Keep invoicing from Gmail. Scotive does the rest.
                                </h2>
                            </div>
                            <span className="pill">3 steps · about a minute</span>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <HowItWorksStep
                                index={1}
                                title="Connect your Gmail"
                                description="One click, two permissions: read mail, and send with your approval. Revoke anytime from Settings or Google."
                                mock={<StepConnectMock />}
                            />
                            <HowItWorksStep
                                index={2}
                                title="Pick what's still unpaid"
                                description="Scotive finds invoices from your last 90 days of sent mail. Confirm what's open — you know your work; we build the ledger."
                                mock={<StepPickMock />}
                            />
                            <HowItWorksStep
                                index={3}
                                title="Approve the follow-ups"
                                description="When something is late or a promise breaks, a draft appears with a state-derived tone label. Edit, regenerate, or send — never auto-sent."
                                mock={<StepApproveMock />}
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-features">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>What you get</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                A collections brain that lives in your inbox.
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
                                description="Send invoices like you always do. Scotive detects them in sent mail and tracks amounts, clients, and due dates."
                                chips={["Live Gmail watching", "Ledger by client", "Multi-currency"]}
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
                                description="Drafts match the invoice state — Friendly reminder, Firm follow-up, Final notice, or Clarifying reply — signed with your Gmail name."
                                chips={["Tone from ledger state", "Same-thread replies", "One-tap approve"]}
                            />
                            <FeatureCard
                                icon={Wallet}
                                replaces="manual reconciliation"
                                title="Payment matching"
                                description="Receipts and “says paid” claims land on the right invoice. Confirm received, or mark not yet — partials tracked."
                                chips={["Receipt matching", "Partial payments", "Confirm prompts"]}
                            />
                            <FeatureCard
                                icon={Eye}
                                replaces="constant checking-in"
                                title="Needs you today"
                                description="One prioritized list: past due, broken promises, replies, and confirmations. Optional daily digest from your Gmail."
                                chips={["Priority-first", "Daily digest", "Review queue"]}
                            />
                            <FeatureCard
                                icon={ShieldCheck}
                                replaces="trust-me automation"
                                title="You stay in control"
                                description="Nothing is ever auto-sent. Two Gmail permissions. Email content isn't used to train Scotive's models. Disconnect anytime."
                                chips={["Approval-only", "OAuth 2.0", "Delete account anytime"]}
                            />
                        </div>
                    </div>
                </section>

                <section className="py-20 md:py-24 border-t border-border/70" data-testid="landing-outcomes">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-2xl mb-12">
                            <SectionEyebrow>Built for people who bill from their inbox</SectionEyebrow>
                            <h2 className="type-title text-3xl md:text-4xl">
                                Freelancers and studios stop leaking revenue.
                            </h2>
                        </div>
                        <div className="grid md:grid-cols-3 gap-4">
                            <OutcomeCard
                                quote="I used to spend Sunday nights going through sent mail to figure out who to nudge. Now it's a short approval pass with coffee."
                                metric="Sundays back"
                                name="Freelance designer"
                                role="Solo · 12 active clients"
                            />
                            <OutcomeCard
                                quote="A client promised payment three times. Scotive caught every date and drafted a firmer follow-up. Paid in full the next week."
                                metric="0 awkward emails"
                                name="Studio founder"
                                role="4-person agency"
                            />
                            <OutcomeCard
                                quote="Seed curation found an invoice I'd completely forgotten. That one recovery covered a year of any tool I could buy."
                                metric="Recovered cash"
                                name="Consultant"
                                role="B2B advisory"
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
                                    <img src="/scotive-icon.png" alt="" width={56} height={56} className="w-14 h-14 rounded-2xl" />
                                </div>
                                <h2 className="type-display text-3xl md:text-5xl">
                                    Get paid without the awkward chase.
                                </h2>
                                <p className="type-body mt-4 text-base md:text-lg opacity-80 max-w-xl mx-auto">
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

            <footer className="border-t border-border mt-auto">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid gap-10 md:grid-cols-4">
                    <div className="md:col-span-2">
                        <BrandMark />
                        <p className="type-body mt-3 text-sm max-w-xs">
                            Payment ops inside Gmail — for everyone who bills from their inbox.
                        </p>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Product</div>
                        <ul className="space-y-2 text-sm text-muted-foreground">
                            <li><Link to="/register" className="hover:text-foreground">Get started</Link></li>
                            <li><Link to="/login" className="hover:text-foreground">Log in</Link></li>
                        </ul>
                    </div>
                    <div>
                        <div className="type-title text-sm mb-3">Legal</div>
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
